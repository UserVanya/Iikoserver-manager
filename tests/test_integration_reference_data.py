"""Интеграционные тесты Reference Data API.

Тесты вспомогательных методов для работы со справочными данными.

Запуск:
    uv run pytest tests/test_integration_reference_data.py -v
"""

# mypy: disable-error-code="no-untyped-def"

from __future__ import annotations

import pytest

from iikoserver import IikoServerApiClientManager

# Маркируем весь модуль как интеграционные тесты
pytestmark = [pytest.mark.integration, pytest.mark.slow]


class TestDiscountTypes:
    """Тесты получения типов скидок."""

    async def test_get_discount_types_list_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_discount_types_list возвращает список."""
        response = await manager.get_discount_types_list()

        assert response is not None
        assert isinstance(response, list)

    async def test_get_discount_types_list_with_deleted(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_discount_types_list с include_deleted работает."""
        response = await manager.get_discount_types_list(include_deleted=True)

        assert response is not None
        assert isinstance(response, list)


class TestPaymentTypes:
    """Тесты получения типов оплат."""

    async def test_get_payment_types_list_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_payment_types_list возвращает список."""
        response = await manager.get_payment_types_list()

        assert response is not None
        assert isinstance(response, list)

    async def test_get_payment_types_list_with_deleted(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_payment_types_list с include_deleted работает."""
        response = await manager.get_payment_types_list(include_deleted=True)

        assert response is not None
        assert isinstance(response, list)


class TestOrderTypes:
    """Тесты получения типов заказов."""

    async def test_get_order_types_list_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_order_types_list возвращает список."""
        response = await manager.get_order_types_list()

        assert response is not None
        assert isinstance(response, list)


class TestMeasurementUnits:
    """Тесты получения единиц измерения."""

    @pytest.mark.skip(reason="API не поддерживает тип MeasurementUnit")
    async def test_get_measurement_units_list_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_measurement_units_list возвращает список."""
        response = await manager.get_measurement_units_list()

        assert response is not None
        assert isinstance(response, list)


class TestCookingPlaceTypes:
    """Тесты получения типов мест приготовления."""

    async def test_get_cooking_place_types_list_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_cooking_place_types_list возвращает список."""
        response = await manager.get_cooking_place_types_list()

        assert response is not None
        assert isinstance(response, list)


class TestConceptions:
    """Тесты получения концепций."""

    async def test_get_conceptions_list_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_conceptions_list возвращает список."""
        response = await manager.get_conceptions_list()

        assert response is not None
        assert isinstance(response, list)


class TestProductCategories:
    """Тесты получения категорий продуктов."""

    async def test_get_product_categories_list_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_product_categories_list возвращает список."""
        response = await manager.get_product_categories_list()

        assert response is not None
        assert isinstance(response, list)


class TestProductScales:
    """Тесты получения шкал продуктов."""

    async def test_get_product_scales_list_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_product_scales_list возвращает список."""
        response = await manager.get_product_scales_list()

        assert response is not None
        assert isinstance(response, list)


class TestProductSizes:
    """Тесты получения размеров продуктов."""

    async def test_get_product_sizes_list_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_product_sizes_list возвращает список."""
        response = await manager.get_product_sizes_list()

        assert response is not None
        assert isinstance(response, list)


class TestTaxCategories:
    """Тесты получения категорий налогов."""

    async def test_get_tax_categories_list_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_tax_categories_list возвращает список."""
        response = await manager.get_tax_categories_list()

        assert response is not None
        assert isinstance(response, list)


class TestScheduleTypes:
    """Тесты получения типов расписания."""

    async def test_get_schedule_types_list_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_schedule_types_list возвращает список."""
        response = await manager.get_schedule_types_list()

        assert response is not None
        assert isinstance(response, list)


class TestAttendanceTypes:
    """Тесты получения типов посещения."""

    async def test_get_attendance_types_list_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_attendance_types_list возвращает список."""
        response = await manager.get_attendance_types_list()

        assert response is not None
        assert isinstance(response, list)


class TestAlcoholClasses:
    """Тесты получения классов алкогольной продукции."""

    async def test_get_alcohol_classes_list_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_alcohol_classes_list возвращает список."""
        response = await manager.get_alcohol_classes_list()

        assert response is not None
        assert isinstance(response, list)


class TestEntitiesList:
    """Тесты базового метода get_entities_list."""

    async def test_get_entities_list_discount_type(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_entities_list работает для DiscountType."""
        response = await manager.get_entities_list(root_type="DiscountType")

        assert response is not None
        assert isinstance(response, list)

    async def test_get_entities_list_payment_type(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_entities_list работает для PaymentType."""
        response = await manager.get_entities_list(root_type="PaymentType")

        assert response is not None
        assert isinstance(response, list)

    async def test_get_entities_list_order_type(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_entities_list работает для OrderType."""
        response = await manager.get_entities_list(root_type="OrderType")

        assert response is not None
        assert isinstance(response, list)

    async def test_get_entities_list_with_include_deleted(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_entities_list с include_deleted=True работает."""
        response = await manager.get_entities_list(
            root_type="DiscountType",
            include_deleted=True,
        )

        assert response is not None
        assert isinstance(response, list)
