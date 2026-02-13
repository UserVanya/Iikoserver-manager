"""Интеграционные тесты Nomenclature Management API.

Тесты методов для работы с номенклатурой (продукты, группы).
Покрывают логику автоматического выбора GET/POST запросов.

Запуск:
    uv run pytest tests/test_integration_nomenclature.py -v
"""

# mypy: disable-error-code="no-untyped-def"

from __future__ import annotations

import pytest

from iikoserver import IikoServerApiClientManager

# Маркируем весь модуль как интеграционные тесты
pytestmark = [pytest.mark.integration, pytest.mark.slow]


# =============================================================================
# Тесты POST запросов (пустые списки, один элемент, без фильтров)
# =============================================================================


class TestPostRequestsNoFilters:
    """Тесты POST запросов без фильтров (получение всех данных)."""

    async def test_get_all_products_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_all_products возвращает список (POST без фильтров)."""
        response = await manager.get_all_products()

        assert response is not None
        assert isinstance(response, list)
        # Должно быть хотя бы несколько продуктов в системе
        assert len(response) > 0

    async def test_get_all_products_with_deleted(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_all_products с include_deleted работает (POST)."""
        response = await manager.get_all_products(include_deleted=True)

        assert response is not None
        assert isinstance(response, list)

    async def test_get_all_product_groups_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_all_product_groups возвращает список (POST без фильтров)."""
        response = await manager.get_all_product_groups()

        assert response is not None
        assert isinstance(response, list)
        assert len(response) > 0

    async def test_products_have_expected_fields(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """Продукты имеют ожидаемые поля."""
        response = await manager.get_all_products()

        assert len(response) > 0
        product = response[0]
        assert hasattr(product, "id")
        assert hasattr(product, "name")
        assert product.id is not None

    async def test_product_groups_have_expected_fields(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """Группы продуктов имеют ожидаемые поля."""
        response = await manager.get_all_product_groups()

        assert len(response) > 0
        group = response[0]
        assert hasattr(group, "id")
        assert hasattr(group, "name")
        assert group.id is not None


class TestPostRequestsEmptyList:
    """Тесты POST запросов с пустыми списками."""

    async def test_get_root_product_groups_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_root_product_groups возвращает корневые группы (POST с parent_ids=[])."""
        response = await manager.get_root_product_groups()

        assert response is not None
        assert isinstance(response, list)
        # Должны быть корневые группы
        assert len(response) > 0, "Должны быть корневые группы продуктов"

    async def test_root_groups_have_no_parent(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """Корневые группы не имеют родителя."""
        response = await manager.get_root_product_groups()

        assert len(response) > 0
        for group in response:
            # Корневые группы должны иметь parent = None
            assert group.parent is None, f"Группа {group.name} имеет parent"


class TestPostRequestsSingleId:
    """Тесты POST запросов с одним ID."""

    async def test_get_products_by_single_id(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_products_list с одним ID работает (POST)."""
        all_products = await manager.get_all_products()
        assert len(all_products) > 0

        product_id = str(all_products[0].id)
        response = await manager.get_products_list(ids=[product_id])

        assert response is not None
        assert isinstance(response, list)
        assert len(response) == 1
        assert str(response[0].id) == product_id

    async def test_get_product_groups_by_single_id(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_product_groups_list с одним ID работает (POST)."""
        all_groups = await manager.get_all_product_groups()
        assert len(all_groups) > 0

        group_id = str(all_groups[0].id)
        response = await manager.get_product_groups_list(ids=[group_id])

        assert response is not None
        assert isinstance(response, list)
        assert len(response) == 1
        assert str(response[0].id) == group_id

    async def test_get_products_by_single_group(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_products_by_group с одним group_id работает (POST)."""
        groups = await manager.get_all_product_groups()
        assert len(groups) > 0

        group_id = str(groups[0].id)
        response = await manager.get_products_by_group(group_id)

        assert response is not None
        assert isinstance(response, list)
        # Все продукты должны принадлежать указанной группе
        for product in response:
            assert str(product.parent) == group_id

    async def test_get_products_by_single_category(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_products_by_category с одним category_id работает (POST)."""
        categories = await manager.get_product_categories_list()

        if len(categories) > 0:
            category_id = str(categories[0].id)
            response = await manager.get_products_by_category(category_id)

            assert response is not None
            assert isinstance(response, list)

    async def test_get_products_by_single_type(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_products_by_type с одним типом работает (POST)."""
        from iikoserver_client.models.product_type import ProductType

        response = await manager.get_products_by_type(ProductType.DISH)

        assert response is not None
        assert isinstance(response, list)
        # Все продукты должны быть указанного типа
        for product in response:
            assert product.type == ProductType.DISH

    async def test_get_child_product_groups(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_child_product_groups возвращает дочерние группы (POST)."""
        root_groups = await manager.get_root_product_groups()
        assert len(root_groups) > 0

        parent_id = str(root_groups[0].id)
        response = await manager.get_child_product_groups(parent_id)

        assert response is not None
        assert isinstance(response, list)
        # Все дочерние группы должны иметь указанного родителя
        for group in response:
            assert str(group.parent) == parent_id


# =============================================================================
# Тесты GET запросов (несколько элементов)
# =============================================================================


class TestGetRequestsMultipleIds:
    """Тесты GET запросов с несколькими ID."""

    async def test_get_products_by_multiple_ids(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_products_by_ids с несколькими ID работает (GET)."""
        all_products = await manager.get_all_products()
        assert len(all_products) >= 2, "Нужно минимум 2 продукта для теста"

        ids = [str(all_products[0].id), str(all_products[1].id)]
        response = await manager.get_products_by_ids(ids)

        assert response is not None
        assert isinstance(response, list)
        assert len(response) == 2
        returned_ids = {str(p.id) for p in response}
        assert set(ids) == returned_ids

    async def test_get_products_by_three_ids(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_products_by_ids с тремя ID работает (GET)."""
        all_products = await manager.get_all_products()
        assert len(all_products) >= 3, "Нужно минимум 3 продукта для теста"

        ids = [str(all_products[i].id) for i in range(3)]
        response = await manager.get_products_by_ids(ids)

        assert response is not None
        assert len(response) == 3
        returned_ids = {str(p.id) for p in response}
        assert set(ids) == returned_ids

    async def test_get_product_groups_by_multiple_ids(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_product_groups_list с несколькими ID работает (GET)."""
        all_groups = await manager.get_all_product_groups()
        assert len(all_groups) >= 2, "Нужно минимум 2 группы для теста"

        ids = [str(all_groups[0].id), str(all_groups[1].id)]
        response = await manager.get_product_groups_list(ids=ids)

        assert response is not None
        assert isinstance(response, list)
        assert len(response) == 2
        returned_ids = {str(g.id) for g in response}
        assert set(ids) == returned_ids

    async def test_get_products_list_multiple_ids_via_list_method(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_products_list с несколькими ID использует GET."""
        all_products = await manager.get_all_products()
        assert len(all_products) >= 2

        ids = [str(all_products[0].id), str(all_products[1].id)]
        response = await manager.get_products_list(ids=ids)

        assert response is not None
        assert len(response) == 2


class TestGetRequestsMultipleTypes:
    """Тесты GET запросов с несколькими типами."""

    async def test_get_products_by_multiple_types(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_products_list с несколькими типами работает (GET)."""
        from iikoserver_client.models.product_type import ProductType

        types = [ProductType.DISH, ProductType.GOODS]
        response = await manager.get_products_list(types=types)

        assert response is not None
        assert isinstance(response, list)
        # Все продукты должны быть одного из указанных типов
        for product in response:
            assert product.type in types


# =============================================================================
# Тесты граничных случаев
# =============================================================================


class TestEdgeCases:
    """Тесты граничных случаев."""

    async def test_get_products_by_empty_ids_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_products_by_ids с пустым списком возвращает все продукты (POST)."""
        response = await manager.get_products_by_ids([])
        all_products = await manager.get_all_products()

        assert response is not None
        assert isinstance(response, list)
        # Пустой список ids должен вернуть все продукты
        assert len(response) == len(all_products)

    async def test_get_products_single_vs_all_consistency(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """Проверка консистентности: один ID через POST vs все через GET."""
        all_products = await manager.get_all_products()
        assert len(all_products) > 0

        product_id = str(all_products[0].id)

        # Получаем через POST (один ID)
        post_result = await manager.get_products_list(ids=[product_id])
        assert len(post_result) == 1

        # Проверяем, что продукт тот же
        assert str(post_result[0].id) == product_id
        assert post_result[0].name == all_products[0].name

    async def test_get_products_multiple_vs_single_consistency(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """Проверка консистентности: несколько ID через GET vs один через POST."""
        all_products = await manager.get_all_products()
        assert len(all_products) >= 2

        ids = [str(all_products[0].id), str(all_products[1].id)]

        # Получаем два через GET
        get_result = await manager.get_products_by_ids(ids)
        assert len(get_result) == 2

        # Получаем каждый отдельно через POST
        post_result_1 = await manager.get_products_list(ids=[ids[0]])
        post_result_2 = await manager.get_products_list(ids=[ids[1]])

        # Данные должны совпадать
        get_ids = {str(p.id) for p in get_result}
        assert ids[0] in get_ids
        assert ids[1] in get_ids
        assert str(post_result_1[0].id) == ids[0]
        assert str(post_result_2[0].id) == ids[1]


# =============================================================================
# Тесты поиска
# =============================================================================


class TestSearchProducts:
    """Тесты поиска продуктов."""

    async def test_search_products_returns_result(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """search_products возвращает результат."""
        response = await manager.search_products()

        assert response is not None

    async def test_find_products_by_name(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """find_products_by_name находит продукт по имени."""
        products = await manager.get_all_products()
        assert len(products) > 0

        # Берём имя существующего продукта
        if products[0].name:
            search_term = products[0].name[:3]
            response = await manager.find_products_by_name(search_term)
            assert response is not None


# =============================================================================
# Тесты API клиента
# =============================================================================


class TestNomenclatureApiClient:
    """Тесты получения API клиента."""

    async def test_get_nomenclature_api_returns_client(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_nomenclature_api возвращает API клиент."""
        from iikoserver_client import NomenclatureManagementApi

        api = await manager.get_nomenclature_api()

        assert api is not None
        assert isinstance(api, NomenclatureManagementApi)

    async def test_get_nomenclature_api_returns_same_instance(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_nomenclature_api возвращает один и тот же экземпляр."""
        api1 = await manager.get_nomenclature_api()
        api2 = await manager.get_nomenclature_api()

        assert api1 is api2


# =============================================================================
# Тесты типов продуктов
# =============================================================================


class TestProductTypes:
    """Тесты получения продуктов по типам."""

    async def test_get_products_type_dish(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """Получение продуктов типа DISH."""
        from iikoserver_client.models.product_type import ProductType

        response = await manager.get_products_by_type(ProductType.DISH)

        assert response is not None
        assert isinstance(response, list)
        for product in response:
            assert product.type == ProductType.DISH

    async def test_get_products_type_goods(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """Получение продуктов типа GOODS."""
        from iikoserver_client.models.product_type import ProductType

        response = await manager.get_products_by_type(ProductType.GOODS)

        assert response is not None
        assert isinstance(response, list)
        for product in response:
            assert product.type == ProductType.GOODS

    async def test_get_products_type_modifier(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """Получение продуктов типа MODIFIER."""
        from iikoserver_client.models.product_type import ProductType

        response = await manager.get_products_by_type(ProductType.MODIFIER)

        assert response is not None
        assert isinstance(response, list)
        for product in response:
            assert product.type == ProductType.MODIFIER


# =============================================================================
# Тесты пользовательских категорий
# =============================================================================


class TestUserCategories:
    """Тесты получения пользовательских категорий."""

    async def test_get_all_user_categories_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_all_user_categories возвращает список (POST без фильтров)."""
        response = await manager.get_all_user_categories()

        assert response is not None
        assert isinstance(response, list)

    async def test_get_all_user_categories_with_deleted(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_all_user_categories с include_deleted работает."""
        response = await manager.get_all_user_categories(include_deleted=True)

        assert response is not None
        assert isinstance(response, list)

    async def test_get_user_categories_by_single_id(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_user_categories_list с одним ID работает (POST)."""
        all_categories = await manager.get_all_user_categories()

        if len(all_categories) > 0:
            category_id = str(all_categories[0].id)
            response = await manager.get_user_categories_list(ids=[category_id])

            assert response is not None
            assert isinstance(response, list)
            assert len(response) == 1
            assert str(response[0].id) == category_id

    async def test_get_user_categories_by_multiple_ids(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_user_categories_by_ids с несколькими ID работает (GET)."""
        all_categories = await manager.get_all_user_categories()

        if len(all_categories) >= 2:
            ids = [str(all_categories[0].id), str(all_categories[1].id)]
            response = await manager.get_user_categories_by_ids(ids)

            assert response is not None
            assert isinstance(response, list)
            assert len(response) == 2
            returned_ids = {str(c.id) for c in response}
            assert set(ids) == returned_ids

    async def test_user_categories_have_expected_fields(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """Пользовательские категории имеют ожидаемые поля."""
        response = await manager.get_all_user_categories()

        if len(response) > 0:
            category = response[0]
            assert hasattr(category, "id")
            assert hasattr(category, "name")
            assert category.id is not None


# =============================================================================
# Тесты технологических карт
# =============================================================================


class TestAssemblyChartsBasic:
    """Базовые тесты технологических карт."""

    async def test_get_today_assembly_charts_returns_result(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_today_assembly_charts возвращает результат."""
        response = await manager.get_today_assembly_charts()

        assert response is not None

    async def test_get_all_assembly_charts_returns_result(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_all_assembly_charts возвращает результат."""
        from datetime import date

        today = date.today()
        response = await manager.get_all_assembly_charts(date_from=today)

        assert response is not None

    async def test_get_all_assembly_charts_with_date_range(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_all_assembly_charts с диапазоном дат работает."""
        from datetime import date, timedelta

        today = date.today()
        week_later = today + timedelta(days=7)

        response = await manager.get_all_assembly_charts(
            date_from=today,
            date_to=week_later,
        )

        assert response is not None

    async def test_get_all_assembly_charts_with_options(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_all_assembly_charts с опциями работает."""
        from datetime import date

        today = date.today()
        response = await manager.get_all_assembly_charts(
            date_from=today,
            include_deleted_products=True,
            include_prepared_charts=True,
        )

        assert response is not None


class TestAssemblyChartsForProduct:
    """Тесты техкарт для конкретного продукта."""

    async def test_get_product_assembly_chart(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_product_assembly_chart возвращает техкарту для блюда."""
        from iikoserver_client.models.product_type import ProductType

        # Получаем блюда, для которых есть техкарты
        dishes = await manager.get_products_by_type(ProductType.DISH)

        if len(dishes) > 0:
            product_id = str(dishes[0].id)
            response = await manager.get_product_assembly_chart(product_id)

            assert response is not None

    async def test_get_product_ingredients(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_product_ingredients возвращает разложенную техкарту."""
        from iikoserver_client.models.product_type import ProductType

        dishes = await manager.get_products_by_type(ProductType.DISH)

        if len(dishes) > 0:
            product_id = str(dishes[0].id)
            response = await manager.get_product_ingredients(product_id)

            assert response is not None

    async def test_get_assembly_chart_tree(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_assembly_chart_tree возвращает дерево техкарт."""
        from datetime import date

        from iikoserver_client.models.product_type import ProductType

        dishes = await manager.get_products_by_type(ProductType.DISH)

        if len(dishes) > 0:
            product_id = str(dishes[0].id)
            response = await manager.get_assembly_chart_tree(
                product_id=product_id,
                var_date=date.today(),
            )

            assert response is not None

    async def test_get_assembly_chart_history(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_assembly_chart_history возвращает историю техкарт."""
        from iikoserver_client.models.product_type import ProductType

        dishes = await manager.get_products_by_type(ProductType.DISH)

        if len(dishes) > 0:
            product_id = str(dishes[0].id)
            response = await manager.get_assembly_chart_history(product_id)

            assert response is not None
            assert isinstance(response, list)


class TestAssemblyChartById:
    """Тесты получения техкарты по ID."""

    async def test_get_assembly_chart_by_id(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_assembly_chart_by_id возвращает техкарту."""
        from iikoserver_client.models.product_type import ProductType

        # Сначала получаем историю техкарт для блюда
        dishes = await manager.get_products_by_type(ProductType.DISH)

        if len(dishes) > 0:
            product_id = str(dishes[0].id)
            history = await manager.get_assembly_chart_history(product_id)

            if len(history) > 0:
                chart_id = str(history[0].id)
                response = await manager.get_assembly_chart_by_id(chart_id)

                assert response is not None
                assert str(response.id) == chart_id
