"""Конфигурация для iikoserver API клиента.

Читает настройки из YAML-файла, путь к которому указывается
в переменной окружения IIKOSERVER_CONFIG.

Переменные окружения автоматически загружаются из .env файла.
"""

from functools import lru_cache
from os import getenv
from typing import Any, TypeVar, cast

from dotenv import load_dotenv
from pydantic import BaseModel, SecretStr
from yaml import CSafeLoader as SafeLoader
from yaml import load

# Автоматически загружаем переменные из .env файла
load_dotenv()

ConfigType = TypeVar("ConfigType", bound=BaseModel)


class IikoServerConfig(BaseModel):
    """Конфигурация для подключения к iikoserver API."""

    # Хост сервера (например: stary-oskol-co.iiko.it)
    host: str

    # Логин аккаунта для входа на сервер
    login: SecretStr

    # Пароль аккаунта для входа на сервер
    password: SecretStr


@lru_cache
def parse_config_file() -> dict[str, Any]:
    """Прочитать и распарсить YAML-файл конфигурации.

    Путь к файлу берётся из переменной окружения IIKOSERVER_CONFIG.

    Returns:
        Словарь с конфигурацией

    Raises:
        ValueError: Если переменная окружения не задана
        FileNotFoundError: Если файл не найден
    """
    file_path = getenv("IIKOSERVER_CONFIG")
    if file_path is None:
        raise ValueError(
            "Переменная окружения IIKOSERVER_CONFIG не задана. "
            "Укажите путь к файлу конфигурации."
        )

    with open(file_path, "rb") as file:
        config_data = load(file, Loader=SafeLoader)

    if not isinstance(config_data, dict):
        raise ValueError("Конфигурация должна быть словарём")
    return config_data


@lru_cache
def get_config(model: type[ConfigType], root_key: str) -> ConfigType:  # noqa: UP047
    """Получить конфигурацию определённого типа из файла.

    Args:
        model: Pydantic-модель для валидации
        root_key: Корневой ключ в YAML-файле

    Returns:
        Экземпляр модели с заполненными значениями

    Raises:
        ValueError: Если ключ не найден в конфигурации
    """
    config_dict = parse_config_file()
    if root_key not in config_dict:
        raise ValueError(f"Ключ '{root_key}' не найден в конфигурации")
    return model.model_validate(config_dict[root_key])


def get_iikoserver_config() -> IikoServerConfig:
    """Получить конфигурацию iikoserver.

    Удобная обёртка для получения IikoServerConfig.

    Returns:
        Экземпляр IikoServerConfig
    """
    return cast(IikoServerConfig, get_config(IikoServerConfig, "iikoserver"))
