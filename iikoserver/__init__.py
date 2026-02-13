"""Модуль для работы с iikoserver API.

Предоставляет клиента с автоматическим управлением токенами
и retry при 401 ошибках.

Пример использования:
    from iikoserver import get_iikoserver_config, IikoServerApiClientManager

    config = get_iikoserver_config()
    manager = await IikoServerApiClientManager.from_config(config)
    
    # Reference Data API
    discount_types = await manager.get_discount_types_list()
    
    # Nomenclature Management API
    products = await manager.get_all_products()
    groups = await manager.get_all_product_groups()
"""

from iikoserver.api_client_manager import (
    ApiCredentials,
    IikoServerApiClientManager,
)
from iikoserver.config_reader import (
    IikoServerConfig,
    get_config,
    get_iikoserver_config,
    parse_config_file,
)
from iikoserver.exceptions import (
    IikoServerAuthException,
    IikoServerException,
)
from iikoserver.token_manager import TokenManager

__all__ = [
    # API Client Manager
    "ApiCredentials",
    "IikoServerApiClientManager",
    # Configuration
    "IikoServerConfig",
    "get_config",
    "get_iikoserver_config",
    "parse_config_file",
    # Exceptions
    "IikoServerAuthException",
    "IikoServerException",
    # Token Management
    "TokenManager",
]
