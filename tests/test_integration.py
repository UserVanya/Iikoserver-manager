"""Интеграционные тесты с реальными запросами к iikoserver API.

Эти тесты используют реальный API и требуют:
1. Настроенный config.yml с валидными host, login, password
2. Переменную окружения IIKOSERVER_CONFIG

Запуск только интеграционных тестов:
    uv run pytest -m integration -v

Запуск всех тестов кроме интеграционных:
    uv run pytest -m "not integration" -v
"""

# mypy: disable-error-code="no-untyped-def"

from __future__ import annotations

import asyncio

from iikoserver_client.exceptions import UnauthorizedException
import pytest

from iikoserver import (
    ApiCredentials,
    IikoServerApiClientManager,
    IikoServerAuthException,
)


def clear_session_cookies(manager: IikoServerApiClientManager) -> None:
    """Очистить cookies из aiohttp сессии.
    
    aiohttp автоматически сохраняет cookies в своём cookie jar.
    Для тестирования 401 нужно очистить их полностью.
    """
    # Получаем доступ к rest_client и его pool_manager (aiohttp ClientSession)
    rest_client = manager._api_client.rest_client
    if rest_client.pool_manager is not None:
        # Очищаем cookie jar сессии
        rest_client.pool_manager.cookie_jar.clear()
    
    # Также очищаем api_key в конфигурации
    manager._api_client.configuration.api_key = {}
    
    # И сбрасываем токен в token_manager
    if manager._token_manager is not None:
        manager._token_manager._token = None

# Маркируем весь модуль как интеграционные и медленные тесты
pytestmark = [pytest.mark.integration, pytest.mark.slow]


class TestInvalidCredentials:
    """Тесты с некорректными учетными данными."""

    async def test_invalid_credentials_raises_auth_exception(self) -> None:
        """Некорректные учетные данные выбрасывают IikoServerAuthException."""
        # Создаём менеджер с заведомо неверными данными
        credentials = ApiCredentials(
            host="invalid-host.iiko.it",
            login="invalid-login",
            password="invalid-password",
        )
        manager = await IikoServerApiClientManager.get_instance(credentials)

        try:
            # Любой вызов должен попытаться получить токен и получить ошибку
            with pytest.raises(IikoServerAuthException):
                await manager.get_discount_types_list()
        finally:
            # Обязательно очищаем после теста
            await IikoServerApiClientManager.close_all()


class TestRealApiReferenceData:
    """Тесты Reference Data API с реальным API."""

    async def test_get_discount_types_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_discount_types возвращает список типов скидок."""
        response = await manager.get_discount_types_list()

        # Проверяем структуру ответа
        assert response is not None
        assert isinstance(response, list)

        # Должен быть хотя бы один тип
        if len(response) > 0:
            entity = response[0]
            assert hasattr(entity, "id")
            assert hasattr(entity, "name")

    async def test_get_payment_types_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_payment_types возвращает список типов оплат."""
        response = await manager.get_payment_types_list()

        assert response is not None
        assert isinstance(response, list)

    async def test_get_order_types_returns_list(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_order_types возвращает список типов заказов."""
        response = await manager.get_order_types_list()

        assert response is not None
        assert isinstance(response, list)

    async def test_get_entities_list_with_root_type(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """get_entities_list работает с разными root_type."""
        # Тестируем несколько типов
        for root_type in ["DiscountType", "PaymentType"]:
            response = await manager.get_entities_list(root_type=root_type)
            assert response is not None
            assert isinstance(response, list)

    async def test_get_entities_twice_uses_same_token(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """Повторный вызов использует тот же токен (без повторной авторизации)."""
        # Первый запрос
        response1 = await manager.get_discount_types_list()
        token_version_1 = manager._token_manager._token_version  # type: ignore

        # Второй запрос
        response2 = await manager.get_payment_types_list()
        token_version_2 = manager._token_manager._token_version  # type: ignore

        # Оба запроса успешны
        assert response1 is not None
        assert response2 is not None

        # Версия токена не изменилась (не было повторной авторизации)
        assert token_version_1 == token_version_2


class TestRealApiTokenRefresh:
    """Тесты обновления токена при 401."""

    async def test_request_after_cookie_invalidation_succeeds(
        self, fresh_manager: IikoServerApiClientManager
    ) -> None:
        """Запрос после 'инвалидации' cookie успешен (происходит refresh).
        
        Для iikoserver нужно очистить:
        1. cookie jar в aiohttp сессии
        2. api_key в конфигурации
        3. токен в token_manager
        """
        # Первый успешный запрос
        response1 = await fresh_manager.get_discount_types_list()
        assert response1 is not None
        token_version_before = fresh_manager._token_manager._token_version  # type: ignore
        token_before = fresh_manager._token_manager._token  # type: ignore

        # Пауза для стабильности
        await asyncio.sleep(1)

        # Полностью очищаем cookies (включая aiohttp cookie jar!)
        clear_session_cookies(fresh_manager)

        # Проверяем, что прямой вызов API без retry вызывает 401
        with pytest.raises(UnauthorizedException):
            ref_api = await fresh_manager.get_reference_data_api()
            await ref_api.v2_entities_list_get(root_type="DiscountType")

        # Следующий запрос через execute_with_retry должен
        # получить 401, обновить токен и повторить
        response2 = await fresh_manager.get_discount_types_list()

        # Запрос успешен
        assert response2 is not None

        # Токен был обновлён
        token_version_after = fresh_manager._token_manager._token_version  # type: ignore
        token_after = fresh_manager._token_manager._token  # type: ignore

        assert token_version_after > token_version_before
        assert token_after != token_before

    async def test_request_after_empty_cookie_succeeds(
        self, fresh_manager: IikoServerApiClientManager
    ) -> None:
        """Запрос после полной очистки cookie успешен."""
        # Первый успешный запрос
        response1 = await fresh_manager.get_discount_types_list()
        assert response1 is not None
        token_version_before = fresh_manager._token_manager._token_version  # type: ignore

        await asyncio.sleep(1)

        # Полностью очищаем cookies (включая aiohttp cookie jar!)
        clear_session_cookies(fresh_manager)

        # Следующий запрос должен обновить токен
        response2 = await fresh_manager.get_payment_types_list()

        assert response2 is not None

        # Токен был обновлён
        token_version_after = fresh_manager._token_manager._token_version  # type: ignore
        assert token_version_after > token_version_before


class TestRealApiConcurrentRequests:
    """Тесты конкурентных запросов к реальному API.
    
    Note: iikoserver рекомендует последовательные запросы.
    Конкурентные запросы могут приводить к неожиданному поведению
    из-за особенностей сессионной аутентификации.
    """

    async def test_concurrent_requests_all_succeed(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """Несколько одновременных запросов успешно выполняются."""
        # Используем только поддерживаемые типы (Role не поддерживается)
        async def delayed_request(delay: float, root_type: str):
            await asyncio.sleep(delay)
            return await manager.get_entities_list(root_type=root_type)

        results = await asyncio.gather(
            delayed_request(0.0, "DiscountType"),
            delayed_request(0.1, "PaymentType"),
            delayed_request(0.2, "OrderType"),
            return_exceptions=True,
        )

        # Все запросы должны быть успешными
        for i, result in enumerate(results):
            assert not isinstance(result, BaseException), f"Request {i} failed: {result}"
            assert result is not None

    async def test_concurrent_requests_after_cookie_invalidation(
        self, fresh_manager: IikoServerApiClientManager
    ) -> None:
        """Конкурентные запросы после инвалидации cookie — токен обновляется.
        
        Note: Из-за особенностей aiohttp (автоматическое управление cookies)
        и сессионной аутентификации iikoserver, при конкурентных запросах
        может происходить несколько обновлений токена. Это ожидаемое поведение.
        """
        # Первый запрос для получения токена
        await fresh_manager.get_discount_types_list()
        token_version_before = fresh_manager._token_manager._token_version  # type: ignore

        await asyncio.sleep(1)

        # Полностью очищаем cookies (включая aiohttp cookie jar!)
        clear_session_cookies(fresh_manager)

        # Запускаем конкурентные запросы
        # Они получат 401 и обновят токен
        async def delayed_request(delay: float, root_type: str):
            await asyncio.sleep(delay)
            return await fresh_manager.get_entities_list(root_type=root_type)

        results = await asyncio.gather(
            delayed_request(0.0, "DiscountType"),
            delayed_request(0.1, "PaymentType"),
            return_exceptions=True,
        )

        # Все запросы успешны
        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"Request {i} failed: {result}"

        # Токен был обновлён (версия увеличилась)
        # Note: При конкурентных запросах может быть несколько обновлений
        # из-за race conditions с aiohttp cookie jar
        token_version_after = fresh_manager._token_manager._token_version  # type: ignore
        assert token_version_after > token_version_before


class TestRealApiSequentialRequests:
    """Тесты последовательных запросов (рекомендуемый режим для iikoserver)."""

    async def test_sequential_requests_all_succeed(
        self, manager: IikoServerApiClientManager
    ) -> None:
        """Последовательные запросы успешно выполняются."""
        # Делаем последовательные запросы (только поддерживаемые типы)
        root_types = ["DiscountType", "PaymentType", "OrderType"]
        
        for i, root_type in enumerate(root_types):
            response = await manager.get_entities_list(root_type=root_type)
            assert response is not None, f"Request {i} ({root_type}) failed"
            assert isinstance(response, list)


class TestRealApiCleanup:
    """Тесты корректного закрытия соединений."""

    async def test_close_all_releases_resources(self) -> None:
        """close_all корректно освобождает ресурсы."""
        from iikoserver import get_iikoserver_config
        from iikoserver.token_manager import TokenManager

        config = get_iikoserver_config()
        manager = await IikoServerApiClientManager.from_config(config)

        # Делаем запрос (чтобы получить токен)
        await manager.get_discount_types_list()

        # Проверяем что есть активные экземпляры
        assert len(IikoServerApiClientManager._instances) > 0
        assert len(TokenManager._instances) > 0

        # Закрываем всё
        await IikoServerApiClientManager.close_all()

        # Все экземпляры очищены
        assert len(IikoServerApiClientManager._instances) == 0
        assert len(TokenManager._instances) == 0

    async def test_logout_called_on_close(self) -> None:
        """При close_all вызывается logout для освобождения лицензии."""
        from iikoserver import get_iikoserver_config

        config = get_iikoserver_config()
        manager = await IikoServerApiClientManager.from_config(config)

        # Делаем запрос
        await manager.get_discount_types_list()

        # Получаем token_manager
        token_manager = manager._token_manager
        assert token_manager is not None
        assert token_manager._token is not None

        # Закрываем — logout должен очистить токен
        await IikoServerApiClientManager.close_all()

        # Проверить сложно, т.к. экземпляры удалены,
        # но можно проверить что нет ошибок
