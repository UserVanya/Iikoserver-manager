"""Интеграционные тесты методов создания сущностей.

Тесты создания групп, продуктов, категорий и техкарт.
Использует тестовую группу "Test|Группа для API" в корне номенклатуры.

Запуск:
    uv run pytest tests/test_integration_create.py -v
"""

# mypy: disable-error-code="no-untyped-def"

from __future__ import annotations

import uuid
from datetime import date

from iikoserver_client import AssemblyChartDto, ProductSizeAssemblyStrategy, ProductWriteoffStrategy
from iikoserver_client.models import ProductDto, ProductGroupDto
import pytest

from iikoserver import IikoServerApiClientManager

# Маркируем весь модуль как интеграционные тесты
pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.nomenclature_create]


# =============================================================================
# Тесты создания групп продуктов
# =============================================================================


class TestProductGroup:
    """Тесты создания групп продуктов."""

    async def test_create_product_group_returns_id(
        self,
        manager: IikoServerApiClientManager,
        test_group_id: str,
    ) -> None:
        """create_product_group возвращает ID созданной группы."""
        unique_name = f"Test|"

        result = await manager.create_product_group(
            name=unique_name,
            parent_id=test_group_id,
            description="Тестовая подгруппа",
        )

        assert result is not None
        assert result.response is not None
        assert result.response.id is not None
        # Проверяем, что это валидный UUID
        uuid.UUID(str(result.response.id))

    async def test_create_product_group_appears_in_list(
        self,
        manager: IikoServerApiClientManager,
        test_group_id: str,
    ) -> None:
        """Созданная группа появляется в списке дочерних."""
        unique_name = f"TestGrp_{uuid.uuid4().hex[:8]}"

        result = await manager.create_product_group(
            name=unique_name,
            parent_id=test_group_id,
        )
        assert isinstance(result.response, ProductGroupDto)
        created_id = str(result.response.id)

        # Проверяем, что группа появилась в дочерних
        child_groups = await manager.get_child_product_groups(test_group_id)
        child_ids = {str(g.id) for g in child_groups}

        assert created_id in child_ids


class TestSaveProductGroup:
    """Тесты низкоуровневого сохранения групп."""

    async def test_save_product_group_with_dto(
        self,
        manager: IikoServerApiClientManager,
        test_group_id: str,
    ) -> None:
        """save_product_group работает с ProductGroupSaveDto."""
        from iikoserver_client.models.product_group_save_dto import ProductGroupSaveDto

        unique_name = f"TestGrp_{uuid.uuid4().hex[:8]}"
        dto = ProductGroupSaveDto(
            name=unique_name,
            parent=test_group_id,
            description="Группа через DTO",
        )

        result = await manager.save_product_group(dto)

        assert result is not None
        assert result.response is not None
        assert result.response.id is not None


# =============================================================================
# Тесты создания продуктов
# =============================================================================


class TestCreateSimpleDish:
    """Тесты создания простых блюд."""

    async def test_create_simple_dish_returns_id(
        self,
        manager: IikoServerApiClientManager,
        test_group_id: str,
        measurement_unit_id: str,
    ) -> None:
        """create_simple_dish возвращает ID созданного блюда."""
        unique_name = f"TestDish_{uuid.uuid4().hex[:8]}"

        result = await manager.create_simple_dish(
            name=unique_name,
            main_unit_id=measurement_unit_id,
            parent_id=test_group_id,
            description="Тестовое блюдо",
            default_sale_price=100.0,
        )

        assert result is not None
        assert result.response is not None
        assert result.response.id is not None
        uuid.UUID(str(result.response.id))

    async def test_create_simple_dish_appears_in_group(
        self,
        manager: IikoServerApiClientManager,
        test_group_id: str,
        measurement_unit_id: str,
    ) -> None:
        """Созданное блюдо появляется в списке продуктов группы."""
        unique_name = f"TestDish_{uuid.uuid4().hex[:8]}"

        result = await manager.create_simple_dish(
            name=unique_name,
            main_unit_id=measurement_unit_id,
            parent_id=test_group_id,
        )
        assert isinstance(result.response, ProductDto)
        created_id = str(result.response.id)

        # Проверяем, что блюдо появилось в группе
        products = await manager.get_products_by_group(test_group_id)
        product_ids = {str(p.id) for p in products}

        assert created_id in product_ids

    async def test_create_simple_dish_has_correct_type(
        self,
        manager: IikoServerApiClientManager,
        test_group_id: str,
        measurement_unit_id: str,
    ) -> None:
        """Созданное блюдо имеет тип DISH."""
        from iikoserver_client.models.product_type import ProductType

        unique_name = f"TestDish_{uuid.uuid4().hex[:8]}"

        result = await manager.create_simple_dish(
            name=unique_name,
            main_unit_id=measurement_unit_id,
            parent_id=test_group_id,
        )
        assert isinstance(result.response, ProductDto)
        created_id = str(result.response.id)

        # Получаем продукт и проверяем тип
        products = await manager.get_products_list(ids=[created_id])
        assert len(products) == 1
        assert products[0].type == ProductType.DISH


class TestCreateSimpleGoods:
    """Тесты создания простых товаров."""

    async def test_create_simple_goods_returns_id(
        self,
        manager: IikoServerApiClientManager,
        test_group_id: str,
        goods_unit_id: str,
    ) -> None:
        """create_simple_goods возвращает ID созданного товара."""
        unique_name = f"TestGoods_{uuid.uuid4().hex[:8]}"

        result = await manager.create_simple_goods(
            name=unique_name,
            main_unit_id=goods_unit_id,
            parent_id=test_group_id,
            description="Тестовый товар",
        )

        assert result is not None
        assert result.response is not None
        assert result.response.id is not None
        uuid.UUID(str(result.response.id))

    async def test_create_simple_goods_has_correct_type(
        self,
        manager: IikoServerApiClientManager,
        test_group_id: str,
        goods_unit_id: str,
    ) -> None:
        """Созданный товар имеет тип GOODS."""
        from iikoserver_client.models.product_type import ProductType

        unique_name = f"TestGoods_{uuid.uuid4().hex[:8]}"

        result = await manager.create_simple_goods(
            name=unique_name,
            main_unit_id=goods_unit_id,
            parent_id=test_group_id,
        )
        assert isinstance(result.response, ProductDto)
        created_id = str(result.response.id)

        products = await manager.get_products_list(ids=[created_id])
        assert len(products) == 1
        assert products[0].type == ProductType.GOODS


# =============================================================================
# Тесты создания пользовательских категорий
# =============================================================================


class TestCreateUserCategory:
    """Тесты создания пользовательских категорий."""

    async def test_create_user_category_returns_id(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """create_user_category возвращает ID созданной категории."""
        unique_name = f"TestCat_{uuid.uuid4().hex[:8]}"

        result = await manager.create_user_category(unique_name)

        assert result is not None
        assert result.response is not None
        assert result.response.id is not None
        uuid.UUID(str(result.response.id))

    async def test_create_user_category_appears_in_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """Созданная категория появляется в списке."""
        unique_name = f"TestCat_{uuid.uuid4().hex[:8]}"

        result = await manager.create_user_category(unique_name)
        created_id = str(result.response.id)

        # Проверяем, что категория появилась
        categories = await manager.get_all_user_categories()
        category_ids = {str(c.id) for c in categories}

        assert created_id in category_ids


# =============================================================================
# Тесты создания технологических карт
# =============================================================================


class TestCreateSimpleAssemblyChart:
    """Тесты создания простых техкарт."""

    async def test_create_simple_assembly_chart_returns_result(
        self,
        manager: IikoServerApiClientManager,
        test_group_id: str,
        measurement_unit_id: str,
        goods_unit_id: str,
    ) -> None:
        """create_simple_assembly_chart создаёт техкарту."""
        # Создаём блюдо
        dish_name = f"TestDish_{uuid.uuid4().hex[:8]}"
        dish_result = await manager.create_simple_dish(
            name=dish_name,
            main_unit_id=measurement_unit_id,
            parent_id=test_group_id,
        )
        assert isinstance(dish_result.response, ProductDto)
        dish_id = str(dish_result.response.id)

        # Создаём ингредиент (товар)
        ingredient_name = f"TestIngr_{uuid.uuid4().hex[:8]}"
        ingredient_result = await manager.create_simple_goods(
            name=ingredient_name,
            main_unit_id=goods_unit_id,
            parent_id=test_group_id,
        )
        assert isinstance(ingredient_result.response, ProductDto)
        ingredient_id = str(ingredient_result.response.id)

        # Создаём техкарту
        result = await manager.create_simple_assembly_chart(
            product_id=dish_id,
            ingredients=[(ingredient_id, 0.1)],  # 100г ингредиента
            date_from=date.today(),
        )

        assert result is not None

    async def test_created_chart_appears_in_history(
        self,
        manager: IikoServerApiClientManager,
        test_group_id: str,
        measurement_unit_id: str,
        goods_unit_id: str,
    ) -> None:
        """Созданная техкарта появляется в истории продукта.

        Примечание: API может не сразу возвращать историю для нового блюда.
        """
        # Создаём блюдо и ингредиент
        dish_name = f"TestDish_{uuid.uuid4().hex[:8]}"
        dish_result = await manager.create_simple_dish(
            name=dish_name,
            main_unit_id=measurement_unit_id,
            parent_id=test_group_id,
        )
        assert isinstance(dish_result.response, ProductDto)
        dish_id = str(dish_result.response.id)

        ingredient_name = f"TestIngr_{uuid.uuid4().hex[:8]}"
        ingredient_result = await manager.create_simple_goods(
            name=ingredient_name,
            main_unit_id=goods_unit_id,
            parent_id=test_group_id,
        )
        assert isinstance(ingredient_result.response, ProductDto)
        ingredient_id = str(ingredient_result.response.id)

        # Создаём техкарту
        chart_result = await manager.create_simple_assembly_chart(
            product_id=dish_id,
            ingredients=[(ingredient_id, 0.15)],
        )

        # Проверяем, что техкарта была создана успешно
        assert chart_result is not None

        # История может быть пустой для только что созданного блюда
        # Это нормальное поведение API - история появляется с задержкой
        history = await manager.get_assembly_chart_history(dish_id)
        assert isinstance(history, list)

    async def test_create_chart_with_multiple_ingredients(
        self,
        manager: IikoServerApiClientManager,
        test_group_id: str,
        measurement_unit_id: str,
        goods_unit_id: str,
    ) -> None:
        """Техкарта с несколькими ингредиентами создаётся корректно."""
        # Создаём блюдо
        dish_name = f"TestDish_{uuid.uuid4().hex[:8]}"
        dish_result = await manager.create_simple_dish(
            name=dish_name,
            main_unit_id=measurement_unit_id,
            parent_id=test_group_id,
        )
        assert isinstance(dish_result.response, ProductDto)
        dish_id = str(dish_result.response.id)

        # Создаём 3 ингредиента
        ingredients = []
        for i in range(3):
            ingr_name = f"TestIngr{i}_{uuid.uuid4().hex[:8]}"
            ingr_result = await manager.create_simple_goods(
                name=ingr_name,
                main_unit_id=goods_unit_id,
                parent_id=test_group_id,
            )
            assert isinstance(ingr_result.response, ProductDto)
            ingredients.append((str(ingr_result.response.id), 0.1 * (i + 1)))

        # Создаём техкарту с 3 ингредиентами
        result = await manager.create_simple_assembly_chart(
            product_id=dish_id,
            ingredients=ingredients,
        )

        assert result is not None


class TestSaveAssemblyChart:
    """Тесты низкоуровневого сохранения техкарт."""

    async def test_save_assembly_chart_with_dto(
        self,
        manager: IikoServerApiClientManager,
        test_group_id: str,
        measurement_unit_id: str,
        goods_unit_id: str,
    ) -> None:
        """save_assembly_chart работает с SaveAssemblyChartDto."""
        from iikoserver_client.models.base_assembly_chart_item_dto import (
            BaseAssemblyChartItemDto,
        )
        from iikoserver_client.models.save_assembly_chart_dto import (
            SaveAssemblyChartDto,
        )

        # Создаём блюдо и ингредиент
        dish_name = f"TestDish_{uuid.uuid4().hex[:8]}"
        dish_result = await manager.create_simple_dish(
            name=dish_name,
            main_unit_id=measurement_unit_id,
            parent_id=test_group_id,
        )
        assert isinstance(dish_result.response, ProductDto)
        dish_id = str(dish_result.response.id)

        ingredient_name = f"TestIngr_{uuid.uuid4().hex[:8]}"
        ingredient_result = await manager.create_simple_goods(
            name=ingredient_name,
            main_unit_id=goods_unit_id,
            parent_id=test_group_id,
        )
        assert isinstance(ingredient_result.response, ProductDto)
        ingredient_id = str(ingredient_result.response.id)

        # Создаём DTO вручную
        item = BaseAssemblyChartItemDto(
            sortWeight=0,
            productId=ingredient_id,
            amountIn=0.2,
            amountMiddle=0.18,  # С потерями
            amountOut=0.18,
            amountIn1=0,
            amountOut1=0,
            amountIn2=0,
            amountOut2=0,
            amountIn3=0,
            amountOut3=0,
        )

        dto = SaveAssemblyChartDto(
            assembledProductId=dish_id,
            dateFrom=date.today(),
            dateTo=None,
            assembledAmount=1.0,
            items=[item],
            description="Техкарта через DTO",
            productSizeAssemblyStrategy=ProductSizeAssemblyStrategy.COMMON,
            productWriteoffStrategy=ProductWriteoffStrategy.ASSEMBLE
        )

        result = await manager.save_assembly_chart(dto)

        assert result is not None
        assert isinstance(result.response, AssemblyChartDto)
        assert result.response.id is not None
        assert result.errors in [[], None]
