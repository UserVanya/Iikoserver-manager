"""Общие фикстуры для тестов iikoserver.

Содержит фикстуры, используемые в различных тестовых модулях.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from iikoserver import (
    IikoServerApiClientManager,
    get_iikoserver_config,
)


# ========== Интеграционные фикстуры ==========


@pytest.fixture
async def manager() -> AsyncGenerator[IikoServerApiClientManager, None]:
    """Создать менеджер из реальной конфигурации."""
    config = get_iikoserver_config()
    mgr = await IikoServerApiClientManager.from_config(config)
    yield mgr
    # Cleanup после каждого теста
    await IikoServerApiClientManager.close_all()


@pytest.fixture
async def fresh_manager() -> AsyncGenerator[IikoServerApiClientManager, None]:
    """Создать свежий менеджер (сбросив все предыдущие экземпляры).
    
    Используется для тестов, где нужен чистый старт.
    """
    # Сначала закрываем все существующие
    await IikoServerApiClientManager.close_all()
    
    config = get_iikoserver_config()
    mgr = await IikoServerApiClientManager.from_config(config)
    yield mgr
    
    # Cleanup
    await IikoServerApiClientManager.close_all()

@pytest.fixture
async def get_or_create_test_group(
    manager: IikoServerApiClientManager,
    test_group_name: str = "Test|Группа для API",
) -> str:
    """Получить или создать тестовую группу в корне номенклатуры.

    Args:
        manager: Менеджер API
        test_group_name: Название тестовой группы

    Returns:
        UUID тестовой группы
    """
    # Ищем группу в корневых группах
    root_groups = await manager.get_root_product_groups()
    for group in root_groups:
        if group.name == test_group_name:
            return str(group.id)

    # Группа не найдена — создаём
    result = await manager.create_product_group(
        name=test_group_name,
        parent_id=None,
        description="Тестовая группа для API тестов",
    )
    assert result.response is not None
    return str(result.response.id)

@pytest.fixture
async def measurement_unit_id(manager: IikoServerApiClientManager) -> str:
    """Фикстура: получить ID единицы измерения из существующего блюда."""
    from iikoserver_client.models.product_type import ProductType

    # Берём единицу измерения из существующего блюда
    dishes = await manager.get_products_by_type(ProductType.DISH)
    if dishes:
        return str(dishes[0].main_unit)
    # Fallback — из любого продукта
    products = await manager.get_all_products()
    if products:
        return str(products[0].main_unit)
    pytest.skip("Нет продуктов в системе для получения единицы измерения")

@pytest.fixture
async def goods_unit_id(manager: IikoServerApiClientManager) -> str:
    """Фикстура: получить ID единицы измерения из существующего товара."""
    from iikoserver_client.models.product_type import ProductType

    # Берём единицу измерения из существующего товара
    goods = await manager.get_products_by_type(ProductType.GOODS)
    if goods:
        return str(goods[0].main_unit)
    # Fallback — из любого продукта
    products = await manager.get_all_products()
    if products:
        return str(products[0].main_unit)
    pytest.skip("Нет продуктов в системе для получения единицы измерения")