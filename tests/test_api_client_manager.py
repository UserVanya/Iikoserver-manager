"""Тесты для api_client_manager модуля."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from iikoserver.api_client_manager import (
    ApiCredentials,
    IikoServerApiClientManager,
)
from iikoserver.token_manager import TokenManager

# Маркируем все тесты в этом модуле как unit-тесты
pytestmark = pytest.mark.unit


class TestApiCredentials:
    """Тесты для ApiCredentials."""

    def test_key_id_format(self) -> None:
        """key_id формируется как host:login."""
        creds = ApiCredentials(
            host="example.iiko.it",
            login="user",
            password="pass",
        )
        assert creds.key_id == "example.iiko.it:user"

    def test_different_hosts_different_key_id(self) -> None:
        """Разные хосты дают разные key_id."""
        creds1 = ApiCredentials(host="host1.iiko.it", login="user", password="pass")
        creds2 = ApiCredentials(host="host2.iiko.it", login="user", password="pass")
        
        assert creds1.key_id != creds2.key_id

    def test_different_logins_different_key_id(self) -> None:
        """Разные логины дают разные key_id."""
        creds1 = ApiCredentials(host="host.iiko.it", login="user1", password="pass")
        creds2 = ApiCredentials(host="host.iiko.it", login="user2", password="pass")
        
        assert creds1.key_id != creds2.key_id


class TestIikoServerApiClientManagerCreation:
    """Тесты создания IikoServerApiClientManager."""

    async def test_get_instance_returns_singleton_for_same_credentials(self) -> None:
        """get_instance возвращает тот же экземпляр для одинаковых credentials."""
        await IikoServerApiClientManager.close_all()

        creds = ApiCredentials(host="test.iiko.it", login="user", password="pass")

        manager1 = await IikoServerApiClientManager.get_instance(creds)
        manager2 = await IikoServerApiClientManager.get_instance(creds)

        assert manager1 is manager2

        await IikoServerApiClientManager.close_all()

    async def test_get_instance_creates_different_for_different_credentials(
        self,
    ) -> None:
        """get_instance создаёт разные экземпляры для разных credentials."""
        await IikoServerApiClientManager.close_all()

        creds1 = ApiCredentials(host="host1.iiko.it", login="user", password="pass")
        creds2 = ApiCredentials(host="host2.iiko.it", login="user", password="pass")

        manager1 = await IikoServerApiClientManager.get_instance(creds1)
        manager2 = await IikoServerApiClientManager.get_instance(creds2)

        assert manager1 is not manager2

        await IikoServerApiClientManager.close_all()


class TestCloseAll:
    """Тесты close_all."""

    async def test_close_all_clears_instances(self) -> None:
        """close_all очищает все экземпляры."""
        creds = ApiCredentials(host="test.iiko.it", login="user", password="pass")
        
        await IikoServerApiClientManager.get_instance(creds)
        
        assert len(IikoServerApiClientManager._instances) == 1
        
        await IikoServerApiClientManager.close_all()
        
        assert len(IikoServerApiClientManager._instances) == 0

    async def test_close_all_calls_token_manager_close_all(self) -> None:
        """close_all вызывает TokenManager.close_all."""
        creds = ApiCredentials(host="test.iiko.it", login="user", password="pass")
        
        await IikoServerApiClientManager.get_instance(creds)
        
        with patch.object(
            TokenManager,
            "close_all",
            new_callable=AsyncMock,
        ) as mock_close:
            await IikoServerApiClientManager.close_all()
            mock_close.assert_awaited_once()


class TestExecuteWithRetry:
    """Тесты execute_with_retry."""

    async def test_executes_api_call_successfully(self) -> None:
        """Успешный API вызов выполняется без retry."""
        await IikoServerApiClientManager.close_all()

        creds = ApiCredentials(host="test.iiko.it", login="user", password="pass")
        manager = await IikoServerApiClientManager.get_instance(creds)

        # Мокаем _ensure_token_manager
        mock_token_manager = MagicMock()
        manager._token_manager = mock_token_manager

        with patch.object(
            manager,
            "_ensure_token_manager",
            new_callable=AsyncMock,
            return_value=mock_token_manager,
        ):
            api_call = AsyncMock(return_value="success")
            
            result = await manager.execute_with_retry(api_call)
            
            assert result == "success"
            api_call.assert_awaited_once()

        await IikoServerApiClientManager.close_all()

    async def test_retries_on_401_exception(self) -> None:
        """При 401 ошибке происходит retry после обновления токена."""
        await IikoServerApiClientManager.close_all()

        creds = ApiCredentials(host="test.iiko.it", login="user", password="pass")
        manager = await IikoServerApiClientManager.get_instance(creds)

        # Мокаем token_manager
        mock_token_manager = MagicMock()
        mock_token_manager.refresh_token_if_401 = AsyncMock(return_value=True)
        manager._token_manager = mock_token_manager

        with patch.object(
            manager,
            "_ensure_token_manager",
            new_callable=AsyncMock,
            return_value=mock_token_manager,
        ):
            # Первый вызов выбрасывает 401, второй успешен
            from iikoserver_client.exceptions import UnauthorizedException
            
            call_count = 0
            
            async def api_call():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise UnauthorizedException(status=401, reason="Unauthorized")
                return "success after retry"
            
            result = await manager.execute_with_retry(api_call)
            
            assert result == "success after retry"
            assert call_count == 2
            mock_token_manager.refresh_token_if_401.assert_awaited_once()

        await IikoServerApiClientManager.close_all()

    async def test_raises_non_401_exceptions(self) -> None:
        """Не-401 ошибки пробрасываются без retry."""
        await IikoServerApiClientManager.close_all()

        creds = ApiCredentials(host="test.iiko.it", login="user", password="pass")
        manager = await IikoServerApiClientManager.get_instance(creds)

        mock_token_manager = MagicMock()
        manager._token_manager = mock_token_manager

        with patch.object(
            manager,
            "_ensure_token_manager",
            new_callable=AsyncMock,
            return_value=mock_token_manager,
        ):
            api_call = AsyncMock(side_effect=ValueError("Some error"))
            
            with pytest.raises(ValueError, match="Some error"):
                await manager.execute_with_retry(api_call)

        await IikoServerApiClientManager.close_all()
