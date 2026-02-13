"""Фасад iikoserver API с retry при 401.

Реализует Multitone паттерн — один экземпляр на уникальную комбинацию
host + login.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from datetime import date

from iikoserver_client import (
    ApiClient,
    Configuration,
    NomenclatureManagementApi,
    ProductSizeAssemblyStrategy,
    ProductWriteoffStrategy,
    ReferenceDataApi,
)
from iikoserver_client.exceptions import UnauthorizedException
from iikoserver_client.models.assembly_chart_dto import AssemblyChartDto
from iikoserver_client.models.assembly_chart_save_response_scheme import (
    AssemblyChartSaveResponseScheme,
)
from iikoserver_client.models.base_assembly_chart_item_dto import (
    BaseAssemblyChartItemDto,
)
from iikoserver_client.models.base_entity_dto import BaseEntityDto
from iikoserver_client.models.chart_result_dto import ChartResultDto
from iikoserver_client.models.entity_dto import EntityDto
from iikoserver_client.models.entity_info import EntityInfo
from iikoserver_client.models.product_category_unit_response_scheme import (
    ProductCategoryUnitResponseScheme,
)
from iikoserver_client.models.product_dto import ProductDto
from iikoserver_client.models.product_group_dto import ProductGroupDto
from iikoserver_client.models.product_group_save_dto import ProductGroupSaveDto
from iikoserver_client.models.product_group_unit_operation_response_scheme import (
    ProductGroupUnitOperationResponseScheme,
)
from iikoserver_client.models.product_save_dto import ProductSaveDto
from iikoserver_client.models.product_type import ProductType
from iikoserver_client.models.product_unit_operation_response_scheme import (
    ProductUnitOperationResponseScheme,
)
from iikoserver_client.models.save_assembly_chart_dto import SaveAssemblyChartDto

from iikoserver.config_reader import IikoServerConfig
from iikoserver.token_manager import TokenManager

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)

T = TypeVar("T")


@dataclass
class ApiCredentials:
    """Учетные данные для iikoserver.

    Attributes:
        host: Хост сервера (например: stary-oskol-co.iiko.it)
        login: Логин пользователя
        password: Пароль пользователя
    """

    host: str
    login: str
    password: str

    @property
    def key_id(self) -> str:
        """Уникальный идентификатор для multitone паттерна."""
        return f"{self.host}:{self.login}"


class IikoServerApiClientManager:
    """Multitone-фасад для работы с iikoserver API.

    Содержит: ApiClient, TokenManager.
    Предоставляет типизированные методы для работы с API.

    Использование:
        manager = await IikoServerApiClientManager.get_instance(credentials)
        entities = await manager.get_reference_data("DiscountType")
    """

    _instances: dict[str, "IikoServerApiClientManager"] = {}
    _lock: asyncio.Lock | None = None

    def __init__(self, credentials: ApiCredentials) -> None:
        """Инициализация менеджера (внутренний метод).

        Используйте get_instance() для получения экземпляра.
        """
        self._credentials = credentials
        # Создаём конфигурацию с указанным хостом
        self._config = Configuration(host=credentials.host)
        self._api_client = ApiClient(configuration=self._config)

        self._token_manager: TokenManager | None = None
        logger.debug(
            "Создан экземпляр IikoServerApiClientManager для key_id=%s",
            credentials.key_id,
        )

        # Кэш API клиентов
        self._reference_data_api: ReferenceDataApi | None = None
        self._nomenclature_api: NomenclatureManagementApi | None = None

    @classmethod
    async def get_instance(
        cls,
        credentials: ApiCredentials,
    ) -> "IikoServerApiClientManager":
        """Получить или создать экземпляр менеджера для key_id.

        Args:
            credentials: Учетные данные API

        Returns:
            Экземпляр IikoServerApiClientManager
        """
        if cls._lock is None:
            cls._lock = asyncio.Lock()

        async with cls._lock:
            key = credentials.key_id
            if key not in cls._instances:
                cls._instances[key] = cls(credentials=credentials)
            return cls._instances[key]

    @classmethod
    async def from_config(
        cls, config: IikoServerConfig
    ) -> "IikoServerApiClientManager":
        """Создать экземпляр из конфигурации iikoserver.

        Args:
            config: Конфигурация iikoserver из YAML-файла

        Returns:
            Экземпляр IikoServerApiClientManager
        """
        credentials = ApiCredentials(
            host=config.host,
            login=config.login.get_secret_value(),
            password=config.password.get_secret_value(),
        )
        return await cls.get_instance(credentials=credentials)

    @classmethod
    async def close_all(cls) -> None:
        """Закрыть все соединения и сбросить экземпляры."""
        instance_count = len(cls._instances)

        # Сначала logout (освобождаем лицензии) — требует открытую сессию
        await TokenManager.close_all()

        # Потом закрываем HTTP сессии
        for manager in cls._instances.values():
            await manager._api_client.close()  # type: ignore[no-untyped-call]

        cls._instances.clear()
        cls._lock = None
        logger.debug("Закрыты все соединения (%d экземпляров)", instance_count)

    async def _ensure_token_manager(self) -> TokenManager:
        """Обеспечить наличие token manager с токеном."""
        if self._token_manager is None:
            self._token_manager = await TokenManager.get_instance(
                api_client=self._api_client,
                login=self._credentials.login,
                password=self._credentials.password,
                key_id=self._credentials.key_id,
            )
            await self._token_manager.ensure_token()
        return self._token_manager

    async def execute_with_retry(self, api_call: Callable[[], Awaitable[T]]) -> T:
        """Выполнить API-вызов с retry при 401.

        Args:
            api_call: Асинхронная функция вызова API

        Returns:
            Результат вызова

        Raises:
            Exception: Любые ошибки кроме 401 (они обрабатываются retry)
        """
        token_manager = await self._ensure_token_manager()

        try:
            return await api_call()
        except UnauthorizedException as exc:
            logger.debug("Токен истёк, обновляем")
            await token_manager.refresh_token_if_401(exc)
            return await api_call()
        except Exception as exc:
            # Проверяем на 401 в других типах исключений
            if getattr(exc, "status", None) == 401:
                logger.debug("Токен истёк, обновляем")
                await token_manager.refresh_token_if_401(exc)
                return await api_call()
            # Логируем ошибку API
            logger.error("Ошибка API: %s", exc)
            raise

    # ========== API Клиенты ==========

    async def get_reference_data_api(self) -> ReferenceDataApi:
        """Получить клиент ReferenceDataApi."""
        await self._ensure_token_manager()
        if self._reference_data_api is None:
            self._reference_data_api = ReferenceDataApi(api_client=self._api_client)
        return self._reference_data_api

    async def get_nomenclature_api(self) -> NomenclatureManagementApi:
        """Получить клиент NomenclatureManagementApi."""
        await self._ensure_token_manager()
        if self._nomenclature_api is None:
            self._nomenclature_api = NomenclatureManagementApi(
                api_client=self._api_client
            )
        return self._nomenclature_api

    # ========== Основные методы: Reference Data ==========

    async def get_entities_list(
        self,
        root_type: str,
        include_deleted: bool | None = False,
        revision_from: int | None = -1,
    ) -> list[EntityInfo]:
        """Получить справочную информацию.

        Возвращает общую справочную информацию без привязки к подразделениям.

        Args:
            root_type: Тип справочных данных (DiscountType, PaymentType и др.)
            include_deleted: Включать ли удаленные элементы
            revision_from: Номер ревизии для фильтрации

        Returns:
            Список сущностей
        """

        async def api_call() -> list[EntityInfo]:
            api = await self.get_reference_data_api()
            return await api.v2_entities_list_get(
                root_type=root_type,
                include_deleted=include_deleted,
                revision_from=revision_from,
            )

        return await self.execute_with_retry(api_call)

    # ========== Вспомогательные методы: Reference Data ==========

    async def get_discount_types_list(
        self, include_deleted: bool = False
    ) -> list[EntityInfo]:
        """Получить список типов скидок.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список типов скидок
        """
        return await self.get_entities_list(
            root_type="DiscountType",
            include_deleted=include_deleted,
        )

    async def get_payment_types_list(
        self, include_deleted: bool = False
    ) -> list[EntityInfo]:
        """Получить список типов оплат.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список типов оплат
        """
        return await self.get_entities_list(
            root_type="PaymentType",
            include_deleted=include_deleted,
        )

    async def get_order_types_list(self, include_deleted: bool = False) -> list[EntityInfo]:
        """Получить список типов заказов.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список типов заказов
        """
        return await self.get_entities_list(
            root_type="OrderType",
            include_deleted=include_deleted,
        )

    async def get_alcohol_classes_list(self, include_deleted: bool = False) -> list[EntityInfo]:
        """Получить список класов алкогольной продукции.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список типов класов алкогольной продукции
        """
        return await self.get_entities_list(
            root_type="AlcoholClass",
            include_deleted=include_deleted,
        )

    async def get_attendance_types_list(self, include_deleted: bool = False):
        """Получить список типов посещения.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список типов посещения
        """
        return await self.get_entities_list(
            root_type="AttendanceType",
            include_deleted=include_deleted,
        )

    async def get_conceptions_list(self, include_deleted: bool = False):
        """Получить список типов концепций.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список типов концепций
        """
        return await self.get_entities_list(
            root_type="Conception",
            include_deleted=include_deleted,
        )
        
        
    async def get_cooking_place_types_list(self, include_deleted: bool = False):
        """Получить список типов мест приготовления.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список типов мест приготовления
        """
        return await self.get_entities_list(
            root_type="CookingPlaceType",
            include_deleted=include_deleted,
        )

    async def get_measurement_units_list(self, include_deleted: bool = False):
        """Получить список единиц измерения.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список единиц измерения
        """
        return await self.get_entities_list(
            root_type="MeasurementUnit",
            include_deleted=include_deleted,
        )
        
    async def get_product_categories_list(self, include_deleted: bool = False):
        """Получить список категорий продуктов.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список категорий продуктов
        """
        return await self.get_entities_list(
            root_type="ProductCategory",
            include_deleted=include_deleted,
        )

    async def get_product_scales_list(self, include_deleted: bool = False):
        """Получить список шкал измерения продуктов.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список шкал измерения продуктов
        """
        return await self.get_entities_list(
            root_type="ProductScale",
            include_deleted=include_deleted,
        )

    async def get_product_sizes_list(self, include_deleted: bool = False):
        """Получить список размеров продуктов.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список размеров продуктов
        """
        return await self.get_entities_list(
            root_type="ProductSize",
            include_deleted=include_deleted,
        )
    
    async def get_schedule_types_list(self, include_deleted: bool = False):
        """Получить список типов расписания.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список типов расписания
        """
        return await self.get_entities_list(
            root_type="ScheduleType",
            include_deleted=include_deleted,
        )
    
    async def get_tax_categories_list(self, include_deleted: bool = False):
        """Получить список категорий налогов.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список категорий налогов
        """
        return await self.get_entities_list(
            root_type="TaxCategory",
            include_deleted=include_deleted,
        )

    # ========== Основные методы: Nomenclature Management ==========
    #
    # Важно: API имеет два типа запросов - GET и POST с разным поведением:
    # - POST: работает с пустыми списками и одним ID, но ломается при нескольких ID
    # - GET: работает с несколькими ID, но не поддерживает пустые списки
    #
    # Методы ниже автоматически выбирают правильный тип запроса.

    async def get_products_list(
        self,
        include_deleted: bool | None = None,
        ids: list[str] | None = None,
        nums: list[str] | None = None,
        types: list[ProductType] | None = None,
        category_ids: list[str] | None = None,
        parent_ids: list[str] | None = None,
    ) -> list[ProductDto]:
        """Получить список продуктов.

        Автоматически выбирает GET или POST запрос в зависимости от параметров.
        - POST: если нужны пустые списки или один элемент в фильтрах
        - GET: если несколько элементов в фильтрах

        Args:
            include_deleted: Включать ли удаленные элементы
            ids: Фильтр по ID продуктов
            nums: Фильтр по артикулам
            types: Фильтр по типам продуктов
            category_ids: Фильтр по ID категорий
            parent_ids: Фильтр по ID родительских групп

        Returns:
            Список продуктов
        """
        # Проверяем, нужен ли GET (несколько элементов в любом списке)
        use_get = any(
            lst is not None and len(lst) > 1
            for lst in [ids, nums, category_ids, parent_ids]
        ) or (types is not None and len(types) > 1)

        if use_get:
            return await self._get_products_via_get(
                include_deleted=include_deleted,
                ids=ids,
                nums=nums,
                types=types,
                category_ids=category_ids,
                parent_ids=parent_ids,
            )
        else:
            return await self._get_products_via_post(
                include_deleted=include_deleted,
                id=ids[0] if ids and len(ids) == 1 else None,
                num=nums[0] if nums and len(nums) == 1 else None,
                product_type=types[0] if types and len(types) == 1 else None,
                category_id=category_ids[0] if category_ids and len(category_ids) == 1 else None,
                parent_id=parent_ids[0] if parent_ids and len(parent_ids) == 1 else None,
                parent_ids_empty=parent_ids is not None and len(parent_ids) == 0,
            )

    async def _get_products_via_get(
        self,
        include_deleted: bool | None = None,
        ids: list[str] | None = None,
        nums: list[str] | None = None,
        types: list[ProductType] | None = None,
        category_ids: list[str] | None = None,
        parent_ids: list[str] | None = None,
    ) -> list[ProductDto]:
        """Получить продукты через GET запрос (для нескольких ID)."""

        async def api_call() -> list[ProductDto]:
            api = await self.get_nomenclature_api()
            return await api.v2_entities_products_list_get(
                include_deleted=include_deleted,
                ids=ids,
                nums=nums,
                types=types,
                category_ids=category_ids,
                parent_ids=parent_ids, # type: ignore
            )

        return await self.execute_with_retry(api_call)

    async def _get_products_via_post(
        self,
        include_deleted: bool | None = None,
        id: str | None = None,
        num: str | None = None,
        product_type: ProductType | None = None,
        category_id: str | None = None,
        parent_id: str | None = None,
        parent_ids_empty: bool = False,
    ) -> list[ProductDto]:
        """Получить продукты через POST запрос (для пустых списков или одного ID)."""

        async def api_call() -> list[ProductDto]:
            api = await self.get_nomenclature_api()
            return await api.v2_entities_products_list_post(
                include_deleted=include_deleted,
                ids=[id] if id else None,
                nums=[num] if num else None,
                types=[product_type] if product_type else None,
                category_ids=[category_id] if category_id else None,
                parent_ids=[] if parent_ids_empty else ([parent_id] if parent_id else None),
            )

        return await self.execute_with_retry(api_call)

    async def get_product_groups_list(
        self,
        include_deleted: bool | None = None,
        ids: list[str] | None = None,
        parent_ids: list[str] | None = None,
        revision_from: int | None = None,
        nums: list[str] | None = None,
        codes: list[str] | None = None,
    ) -> list[ProductGroupDto]:
        """Получить список групп продуктов.

        Автоматически выбирает GET или POST запрос в зависимости от параметров.

        Args:
            include_deleted: Включать ли удаленные элементы
            ids: Фильтр по ID групп
            parent_ids: Фильтр по ID родительских групп
            revision_from: Номер ревизии для фильтрации
            nums: Фильтр по артикулам
            codes: Фильтр по кодам

        Returns:
            Список групп продуктов
        """
        # Проверяем, нужен ли GET (несколько элементов в любом списке)
        use_get = any(
            lst is not None and len(lst) > 1
            for lst in [ids, parent_ids, nums, codes]
        )

        if use_get:
            return await self._get_product_groups_via_get(
                include_deleted=include_deleted,
                ids=ids,
                parent_ids=parent_ids,
                revision_from=revision_from,
                nums=nums,
                codes=codes,
            )
        else:
            return await self._get_product_groups_via_post(
                include_deleted=include_deleted,
                id=ids[0] if ids and len(ids) == 1 else None,
                parent_id=parent_ids[0] if parent_ids and len(parent_ids) == 1 else None,
                parent_ids_empty=parent_ids is not None and len(parent_ids) == 0,
                revision_from=revision_from,
                num=nums[0] if nums and len(nums) == 1 else None,
                code=codes[0] if codes and len(codes) == 1 else None,
            )

    async def _get_product_groups_via_get(
        self,
        include_deleted: bool | None = None,
        ids: list[str] | None = None,
        parent_ids: list[str] | None = None,
        revision_from: int | None = None,
        nums: list[str] | None = None,
        codes: list[str] | None = None,
    ) -> list[ProductGroupDto]:
        """Получить группы продуктов через GET запрос (для нескольких ID)."""

        async def api_call() -> list[ProductGroupDto]:
            api = await self.get_nomenclature_api()
            return await api.v2_entities_products_group_list_get(
                include_deleted=include_deleted,
                ids=ids,
                parent_ids=parent_ids, # type: ignore
                revision_from=revision_from,
                nums=nums,
                codes=codes,
            )

        return await self.execute_with_retry(api_call)

    async def _get_product_groups_via_post(
        self,
        include_deleted: bool | None = None,
        id: str | None = None,
        parent_id: str | None = None,
        parent_ids_empty: bool = False,
        revision_from: int | None = None,
        num: str | None = None,
        code: str | None = None,
    ) -> list[ProductGroupDto]:
        """Получить группы продуктов через POST запрос (для пустых списков или одного ID)."""

        async def api_call() -> list[ProductGroupDto]:
            api = await self.get_nomenclature_api()
            return await api.v2_entities_products_group_list_post(
                include_deleted=include_deleted,
                ids=[id] if id else None,
                parent_ids=[] if parent_ids_empty else ([parent_id] if parent_id else None),
                revision_from=revision_from,
                nums=[num] if num else None,
                codes=[code] if code else None,
            )

        return await self.execute_with_retry(api_call)

    async def search_products(
        self,
        include_deleted: bool | None = None,
        name: str | None = None,
        code: str | None = None,
        main_unit: str | None = None,
        num: str | None = None,
        cooking_place_type: str | None = None,
        product_group_type: str | None = None,
        product_type: str | None = None,
    ):
        """Поиск продуктов по различным параметрам.

        Args:
            include_deleted: Включать ли удаленные элементы
            name: Название продукта
            code: Код быстрого набора в IikoFront
            main_unit: Базовая единица измерения
            num: Артикул
            cooking_place_type: Тип места приготовления
            product_group_type: Тип родительской группы
            product_type: Тип номенклатуры

        Returns:
            Результат поиска продуктов (XML формат)
        """

        async def api_call():
            api = await self.get_nomenclature_api()
            return await api.products_search_get(
                include_deleted=include_deleted,
                name=name,
                code=code,
                main_unit=main_unit,
                num=num,
                cooking_place_type=cooking_place_type,
                product_group_type=product_group_type,
                product_type=product_type,
            )

        return await self.execute_with_retry(api_call)

    # ========== Вспомогательные методы: Nomenclature ==========

    async def get_all_products(
        self, include_deleted: bool = False
    ) -> list[ProductDto]:
        """Получить все продукты.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список всех продуктов
        """
        return await self.get_products_list(include_deleted=include_deleted)

    async def get_all_product_groups(
        self, include_deleted: bool = False
    ) -> list[ProductGroupDto]:
        """Получить все группы продуктов.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список всех групп продуктов
        """
        return await self.get_product_groups_list(include_deleted=include_deleted)

    async def get_products_by_ids(
        self, ids: list[str], include_deleted: bool = False
    ) -> list[ProductDto]:
        """Получить продукты по списку ID.

        Args:
            ids: Список ID продуктов
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список продуктов
        """
        return await self.get_products_list(ids=ids, include_deleted=include_deleted)

    async def get_products_by_category(
        self, category_id: str, include_deleted: bool = False
    ) -> list[ProductDto]:
        """Получить продукты по категории.

        Args:
            category_id: ID категории
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список продуктов в категории
        """
        return await self.get_products_list(
            category_ids=[category_id], include_deleted=include_deleted
        )

    async def get_products_by_group(
        self, group_id: str, include_deleted: bool = False
    ) -> list[ProductDto]:
        """Получить продукты в группе.

        Args:
            group_id: ID родительской группы
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список продуктов в группе
        """
        return await self.get_products_list(
            parent_ids=[group_id], include_deleted=include_deleted
        )

    async def get_products_by_type(
        self, product_type: ProductType, include_deleted: bool = False
    ) -> list[ProductDto]:
        """Получить продукты определённого типа.

        Args:
            product_type: Тип продукта (DISH, GOOD, MODIFIER и т.д.)
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список продуктов заданного типа
        """
        return await self.get_products_list(
            types=[product_type], include_deleted=include_deleted
        )

    async def get_root_product_groups(
        self, include_deleted: bool = False
    ) -> list[ProductGroupDto]:
        """Получить корневые группы продуктов (без родителя).

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список корневых групп
        """
        return await self.get_product_groups_list(
            parent_ids=[], include_deleted=include_deleted
        )

    async def get_child_product_groups(
        self, parent_id: str, include_deleted: bool = False
    ) -> list[ProductGroupDto]:
        """Получить дочерние группы продуктов.

        Args:
            parent_id: ID родительской группы
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список дочерних групп
        """
        return await self.get_product_groups_list(
            parent_ids=[parent_id], include_deleted=include_deleted
        )

    async def find_products_by_name(
        self, name: str, include_deleted: bool = False
    ):
        """Найти продукты по названию.

        Args:
            name: Название для поиска
            include_deleted: Включать ли удаленные элементы

        Returns:
            Результат поиска продуктов
        """
        return await self.search_products(name=name, include_deleted=include_deleted)

    async def find_products_by_num(
        self, num: str, include_deleted: bool = False
    ):
        """Найти продукты по артикулу.

        Args:
            num: Артикул для поиска
            include_deleted: Включать ли удаленные элементы

        Returns:
            Результат поиска продуктов
        """
        return await self.search_products(num=num, include_deleted=include_deleted)

    # ========== Основные методы: Пользовательские категории ==========

    async def get_user_categories_list(
        self,
        include_deleted: bool | None = None,
        ids: list[str] | None = None,
        revision_from: int | None = None,
    ) -> list[EntityDto]:
        """Получить список пользовательских категорий.

        Автоматически выбирает GET или POST запрос в зависимости от параметров.

        Args:
            include_deleted: Включать ли удаленные элементы
            ids: Фильтр по ID категорий
            revision_from: Номер ревизии для фильтрации

        Returns:
            Список пользовательских категорий
        """
        # Проверяем, нужен ли GET (несколько ID)
        use_get = ids is not None and len(ids) > 1

        if use_get:
            return await self._get_user_categories_via_get(
                include_deleted=include_deleted,
                ids=ids,
                revision_from=revision_from,
            )
        else:
            return await self._get_user_categories_via_post(
                include_deleted=include_deleted,
                id=ids[0] if ids and len(ids) == 1 else None,
                revision_from=revision_from,
            )

    async def _get_user_categories_via_get(
        self,
        include_deleted: bool | None = None,
        ids: list[str] | None = None,
        revision_from: int | None = None,
    ) -> list[EntityDto]:
        """Получить пользовательские категории через GET (для нескольких ID)."""

        async def api_call() -> list[EntityDto]:
            api = await self.get_nomenclature_api()
            return await api.v2_entities_products_category_list_get(
                include_deleted=include_deleted,
                ids=ids,
                revision_from=revision_from,
            )

        return await self.execute_with_retry(api_call)

    async def _get_user_categories_via_post(
        self,
        include_deleted: bool | None = None,
        id: str | None = None,
        revision_from: int | None = None,
    ) -> list[EntityDto]:
        """Получить пользовательские категории через POST (пустой список или один ID)."""

        async def api_call() -> list[EntityDto]:
            api = await self.get_nomenclature_api()
            return await api.v2_entities_products_category_list_post(
                include_deleted=include_deleted,
                ids=[id] if id else None,
                revision_from=revision_from,
            )

        return await self.execute_with_retry(api_call)

    # ========== Вспомогательные методы: Пользовательские категории ==========

    async def get_all_user_categories(
        self, include_deleted: bool = False
    ) -> list[EntityDto]:
        """Получить все пользовательские категории.

        Args:
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список всех пользовательских категорий
        """
        return await self.get_user_categories_list(include_deleted=include_deleted)

    async def get_user_categories_by_ids(
        self, ids: list[str], include_deleted: bool = False
    ) -> list[EntityDto]:
        """Получить пользовательские категории по списку ID.

        Args:
            ids: Список ID категорий
            include_deleted: Включать ли удаленные элементы

        Returns:
            Список категорий
        """
        return await self.get_user_categories_list(
            ids=ids, include_deleted=include_deleted
        )

    # ========== Основные методы: Технологические карты ==========

    async def get_assembly_chart_by_id(self, chart_id: str) -> AssemblyChartDto:
        """Получить технологическую карту по ID.

        Args:
            chart_id: UUID технологической карты

        Returns:
            Технологическая карта
        """

        async def api_call() -> AssemblyChartDto:
            api = await self.get_nomenclature_api()
            return await api.v2_assembly_charts_by_id_get(id=chart_id)

        return await self.execute_with_retry(api_call)

    async def get_all_assembly_charts(
        self,
        date_from: date,
        date_to: date | None = None,
        include_deleted_products: bool | None = None,
        include_prepared_charts: bool | None = None,
    ) -> ChartResultDto:
        """Получить все технологические карты за период.

        Args:
            date_from: Учетный день, начиная с которого требуются техкарты
            date_to: Учетный день, до которого требуются техкарты (если не указан,
                     возвращаются все будущие техкарты)
            include_deleted_products: Включать ли техкарты для удаленных блюд
            include_prepared_charts: Включать ли разложенные до конечных ингредиентов

        Returns:
            Результат с техкартами
        """

        async def api_call() -> ChartResultDto:
            api = await self.get_nomenclature_api()
            return await api.v2_assembly_charts_get_all_get(
                date_from=date_from,
                date_to=date_to,
                include_deleted_products=include_deleted_products,
                include_prepared_charts=include_prepared_charts,
            )

        return await self.execute_with_retry(api_call)

    async def get_assembly_chart_assembled(
        self,
        product_id: str,
        var_date: date,
        department_id: str | None = None,
    ) -> ChartResultDto:
        """Получить исходную технологическую карту для продукта (первый уровень).

        Args:
            product_id: UUID продукта (блюда, модификатора, заготовки)
            var_date: Учетный день
            department_id: UUID подразделения (опционально)

        Returns:
            Результат с техкартой первого уровня
        """

        async def api_call() -> ChartResultDto:
            api = await self.get_nomenclature_api()
            return await api.v2_assembly_charts_get_assembled_get(
                var_date=var_date,
                product_id=product_id,
                department_id=department_id,
            )

        return await self.execute_with_retry(api_call)

    async def get_assembly_chart_prepared(
        self,
        product_id: str,
        var_date: date,
        department_id: str | None = None,
    ) -> ChartResultDto:
        """Получить техкарту, разложенную до конечных ингредиентов.

        Args:
            product_id: UUID продукта (блюда, модификатора, заготовки)
            var_date: Учетный день
            department_id: UUID подразделения (опционально)

        Returns:
            Результат с разложенной техкартой
        """

        async def api_call() -> ChartResultDto:
            api = await self.get_nomenclature_api()
            return await api.v2_assembly_charts_get_prepared_get(
                var_date=var_date,
                product_id=product_id,
                department_id=department_id,
            )

        return await self.execute_with_retry(api_call)

    async def get_assembly_chart_tree(
        self,
        product_id: str,
        var_date: date,
        department_id: str | None = None,
    ) -> ChartResultDto:
        """Получить дерево технологических карт для продукта.

        Включает дерево актуальных техкарт и разложенную до конечных ингредиентов
        техкарту с учетом "раздельных тех.карт по размерам блюда".

        Args:
            product_id: UUID продукта (блюда, модификатора, заготовки)
            var_date: Учетный день
            department_id: UUID подразделения (опционально)

        Returns:
            Результат с деревом техкарт
        """

        async def api_call() -> ChartResultDto:
            api = await self.get_nomenclature_api()
            return await api.v2_assembly_charts_get_tree_get(
                var_date=var_date,
                product_id=product_id,
                department_id=department_id,
            )

        return await self.execute_with_retry(api_call)

    async def get_assembly_chart_history(
        self,
        product_id: str,
        department_id: str | None = None,
    ) -> list[AssemblyChartDto]:
        """Получить историю техкарт для продукта.

        Args:
            product_id: UUID продукта (блюда, модификатора, заготовки)
            department_id: UUID подразделения (опционально)

        Returns:
            Список всех техкарт для данного продукта
        """

        async def api_call() -> list[AssemblyChartDto]:
            api = await self.get_nomenclature_api()
            return await api.v2_assembly_charts_get_history_get(
                product_id=product_id,
                department_id=department_id,
            )

        return await self.execute_with_retry(api_call)

    # ========== Вспомогательные методы: Технологические карты ==========

    async def get_product_assembly_chart(
        self,
        product_id: str,
        var_date: date | None = None,
        department_id: str | None = None,
    ) -> ChartResultDto:
        """Получить техкарту продукта на указанную дату (или сегодня).

        Удобный метод для получения текущей техкарты первого уровня.

        Args:
            product_id: UUID продукта
            var_date: Учетный день (по умолчанию — сегодня)
            department_id: UUID подразделения (опционально)

        Returns:
            Результат с техкартой
        """
        if var_date is None:
            var_date = date.today()
        return await self.get_assembly_chart_assembled(
            product_id=product_id,
            var_date=var_date,
            department_id=department_id,
        )

    async def get_product_ingredients(
        self,
        product_id: str,
        var_date: date | None = None,
        department_id: str | None = None,
    ) -> ChartResultDto:
        """Получить конечные ингредиенты продукта (разложенная техкарта).

        Удобный метод для получения всех ингредиентов блюда.

        Args:
            product_id: UUID продукта
            var_date: Учетный день (по умолчанию — сегодня)
            department_id: UUID подразделения (опционально)

        Returns:
            Результат с разложенной техкартой
        """
        if var_date is None:
            var_date = date.today()
        return await self.get_assembly_chart_prepared(
            product_id=product_id,
            var_date=var_date,
            department_id=department_id,
        )

    async def get_today_assembly_charts(
        self,
        include_deleted_products: bool = False,
        include_prepared_charts: bool = False,
    ) -> ChartResultDto:
        """Получить все техкарты на сегодня.

        Args:
            include_deleted_products: Включать ли техкарты для удаленных блюд
            include_prepared_charts: Включать ли разложенные до ингредиентов

        Returns:
            Результат с техкартами
        """
        today = date.today()
        return await self.get_all_assembly_charts(
            date_from=today,
            date_to=today,
            include_deleted_products=include_deleted_products,
            include_prepared_charts=include_prepared_charts,
        )

    # ========== Методы создания: Группы продуктов ==========

    async def save_product_group(
        self,
        product_group: ProductGroupSaveDto,
        generate_nomenclature_code: bool = True,
        generate_fast_code: bool = True,
    ) -> ProductGroupUnitOperationResponseScheme:
        """Создать группу продуктов.

        Args:
            product_group: Данные группы продуктов
            generate_nomenclature_code: Генерировать ли артикул
            generate_fast_code: Генерировать ли код быстрого поиска

        Returns:
            Результат операции с ID созданной группы
        """

        async def api_call() -> ProductGroupUnitOperationResponseScheme:
            api = await self.get_nomenclature_api()
            return await api.v2_entities_products_group_save_post(
                generate_nomenclature_code=generate_nomenclature_code,
                generate_fast_code=generate_fast_code,
                product_group_save_dto=product_group,
            )

        return await self.execute_with_retry(api_call)

    async def create_product_group(
        self,
        name: str,
        parent_id: str | None = None,
        description: str | None = None,
    ) -> ProductGroupUnitOperationResponseScheme:
        """Создать простую группу продуктов.

        Упрощённый метод для создания группы с минимальными параметрами.

        Args:
            name: Название группы (макс. 30 символов)
            parent_id: UUID родительской группы (None = корневая)
            description: Описание группы

        Returns:
            Результат операции с ID созданной группы
        """
        group_dto = ProductGroupSaveDto(
            name=name,
            parent=parent_id,
            description=description,
        )
        return await self.save_product_group(group_dto)

    # ========== Методы создания: Продукты ==========

    async def save_product(
        self,
        product: ProductSaveDto,
        generate_nomenclature_code: bool = True,
        generate_fast_code: bool = True,
    ) -> ProductUnitOperationResponseScheme:
        """Создать продукт.

        Args:
            product: Данные продукта
            generate_nomenclature_code: Генерировать ли артикул
            generate_fast_code: Генерировать ли код быстрого поиска

        Returns:
            Результат операции с ID созданного продукта
        """

        async def api_call() -> ProductUnitOperationResponseScheme:
            api = await self.get_nomenclature_api()
            return await api.v2_entities_products_save_post(
                generate_nomenclature_code=generate_nomenclature_code,
                generate_fast_code=generate_fast_code,
                product_save_dto=product,
            )

        return await self.execute_with_retry(api_call)

    async def create_simple_dish(
        self,
        name: str,
        main_unit_id: str,
        parent_id: str | None = None,
        description: str | None = None,
        default_sale_price: float | None = None,
    ) -> ProductUnitOperationResponseScheme:
        """Создать простое блюдо.

        Упрощённый метод для создания блюда с минимальными параметрами.

        Args:
            name: Название блюда
            main_unit_id: UUID единицы измерения (порция)
            parent_id: UUID родительской группы
            description: Описание блюда
            default_sale_price: Цена продажи по умолчанию

        Returns:
            Результат операции с ID созданного блюда
        """
        product_dto = ProductSaveDto(
            name=name,
            type=ProductType.DISH,
            mainUnit=main_unit_id,
            parent=parent_id,
            description=description,
            defaultSalePrice=default_sale_price,
        )
        return await self.save_product(product_dto)

    async def create_simple_goods(
        self,
        name: str,
        main_unit_id: str,
        parent_id: str | None = None,
        description: str | None = None,
    ) -> ProductUnitOperationResponseScheme:
        """Создать простой товар.

        Args:
            name: Название товара
            main_unit_id: UUID единицы измерения
            parent_id: UUID родительской группы
            description: Описание товара

        Returns:
            Результат операции с ID созданного товара
        """
        product_dto = ProductSaveDto(
            name=name,
            type=ProductType.GOODS,
            mainUnit=main_unit_id,
            parent=parent_id,
            description=description,
        )
        return await self.save_product(product_dto)

    # ========== Методы создания: Пользовательские категории ==========

    async def create_user_category(
        self, name: str
    ) -> ProductCategoryUnitResponseScheme:
        """Создать пользовательскую категорию.

        Args:
            name: Название категории

        Returns:
            Результат операции с ID созданной категории
        """
        category_dto = BaseEntityDto(name=name)

        async def api_call() -> ProductCategoryUnitResponseScheme:
            api = await self.get_nomenclature_api()
            return await api.v2_entities_products_category_save_post(
                base_entity_dto=category_dto
            )

        return await self.execute_with_retry(api_call)

    # ========== Методы создания: Технологические карты ==========

    async def save_assembly_chart(
        self, chart: SaveAssemblyChartDto
    ) -> AssemblyChartSaveResponseScheme:
        """Создать технологическую карту.

        Args:
            chart: Данные технологической карты

        Returns:
            Результат операции
        """

        async def api_call() -> AssemblyChartSaveResponseScheme:
            api = await self.get_nomenclature_api()
            return await api.v2_assembly_charts_save_post(
                save_assembly_chart_dto=chart
            )

        return await self.execute_with_retry(api_call)

    async def create_simple_assembly_chart(
        self,
        product_id: str,
        ingredients: list[tuple[str, float]],
        date_from: date | None = None,
        assembled_amount: float = 1.0,
    ) -> AssemblyChartSaveResponseScheme:
        """Создать простую технологическую карту для блюда без размерной шкалы.

        Упрощённый метод для создания техкарты с одним размером.
        Поля amountIn1,2,3, amountOut1,2,3 и packageTypeId не используются.

        Args:
            product_id: UUID блюда/заготовки
            ingredients: Список ингредиентов как [(product_id, amount), ...]
                         где amount = брутто в единицах измерения ингредиента
            date_from: Дата начала действия (по умолчанию — сегодня)
            assembled_amount: Норма закладки (по умолчанию 1.0)

        Returns:
            Результат операции

        Example:
            >>> # Создаём техкарту для блюда "Салат" из 2 ингредиентов
            >>> await manager.create_simple_assembly_chart(
            ...     product_id="dish-uuid",
            ...     ingredients=[
            ...         ("tomato-uuid", 0.1),   # 100г помидоров
            ...         ("cucumber-uuid", 0.05) # 50г огурцов
            ...     ]
            ... )
        """
        if date_from is None:
            date_from = date.today()

        # Создаём строки техкарты с минимальными параметрами
        # amountIn1,2,3 и amountOut1,2,3 = 0 (не используются)
        # packageTypeId = None (не используется)
        items: list[BaseAssemblyChartItemDto] = []
        for idx, (ingredient_id, amount) in enumerate(ingredients):
            item = BaseAssemblyChartItemDto(
                sortWeight=idx,
                productId=ingredient_id,
                amountIn=amount,  # Брутто
                amountMiddle=amount,  # Нетто = Брутто (без потерь)
                amountOut=amount,  # Выход = Брутто (без потерь)
                # Акт проработки — не используем (нули)
                amountIn1=0,
                amountOut1=0,
                amountIn2=0,
                amountOut2=0,
                amountIn3=0,
                amountOut3=0,
                # Без фасовки и спецификаций
                packageTypeId=None,
                productSizeSpecification=None,
                storeSpecification=None,
            )
            items.append(item)

        chart_dto = SaveAssemblyChartDto(
            assembledProductId=product_id,
            dateFrom=date_from,
            dateTo=None,  # Бессрочно
            assembledAmount=assembled_amount,
            items=items,
            productWriteoffStrategy=ProductWriteoffStrategy.ASSEMBLE,
            productSizeAssemblyStrategy=ProductSizeAssemblyStrategy.COMMON
        )

        return await self.save_assembly_chart(chart_dto)