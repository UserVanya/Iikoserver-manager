"""Тесты для token_manager модуля."""

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from iikoserver.exceptions import IikoServerAuthException
from iikoserver.token_manager import TokenManager, hash_password

# Маркируем все тесты в этом модуле как unit-тесты
pytestmark = pytest.mark.unit


class TestHashPassword:
    """Тесты для функции hash_password."""

    def test_hash_password_returns_sha1(self) -> None:
        """hash_password возвращает SHA1 хеш."""
        result = hash_password("test")
        # SHA1 хеш "test" = a94a8fe5ccb19ba61c4c0873d391e987982fbbd3
        assert result == "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"

    def test_hash_password_different_inputs(self) -> None:
        """Разные пароли дают разные хеши."""
        hash1 = hash_password("password1")
        hash2 = hash_password("password2")
        assert hash1 != hash2

    def test_hash_password_consistent(self) -> None:
        """Один и тот же пароль всегда даёт один хеш."""
        hash1 = hash_password("mypassword")
        hash2 = hash_password("mypassword")
        assert hash1 == hash2


@pytest.fixture
def mock_api_client() -> MagicMock:
    """Создать мок ApiClient."""
    client = MagicMock()
    client.configuration = MagicMock()
    client.configuration.api_key = {}
    return client



@pytest.fixture
async def token_manager(
    mock_api_client: MagicMock,
) -> AsyncGenerator[TokenManager, None]:
    """Создать экземпляр TokenManager для тестов."""
    # Сбрасываем состояние
    await TokenManager.close_all()

    manager = await TokenManager.get_instance(
        api_client=mock_api_client,
        login="test-login",
        password="test-password",
        key_id="test-key",
    )
    yield manager

    # Очистка
    await TokenManager.close_all()


class TestTokenManagerCreation:
    """Тесты создания TokenManager."""

    async def test_get_instance_returns_singleton_for_same_key(
        self, mock_api_client: MagicMock
    ) -> None:
        """get_instance возвращает тот же экземпляр для одного key_id."""
        await TokenManager.close_all()

        manager1 = await TokenManager.get_instance(
            mock_api_client, "login", "password", "key1"
        )
        manager2 = await TokenManager.get_instance(
            mock_api_client, "login", "password", "key1"
        )

        assert manager1 is manager2

        await TokenManager.close_all()

    async def test_get_instance_creates_different_for_different_keys(
        self, mock_api_client: MagicMock
    ) -> None:
        """get_instance создаёт разные экземпляры для разных key_id."""
        await TokenManager.close_all()

        manager1 = await TokenManager.get_instance(
            mock_api_client, "login", "password", "key1"
        )
        manager2 = await TokenManager.get_instance(
            mock_api_client, "login", "password", "key2"
        )

        assert manager1 is not manager2

        await TokenManager.close_all()

    async def test_password_is_hashed(
        self, mock_api_client: MagicMock
    ) -> None:
        """Пароль хешируется при создании."""
        await TokenManager.close_all()

        manager = await TokenManager.get_instance(
            mock_api_client, "login", "password123", "key1"
        )

        # Проверяем что хранится хеш, а не открытый пароль
        assert manager._password_hash == hash_password("password123")
        assert manager._password_hash != "password123"

        await TokenManager.close_all()


class TestEnsureToken:
    """Тесты ensure_token."""

    async def test_fetches_token_when_none(
        self, token_manager: TokenManager, mock_api_client: MagicMock
    ) -> None:
        """Получает токен, если его нет."""
        with patch.object(
            token_manager._session_api,
            "auth_get",
            new_callable=AsyncMock,
            return_value="new-session-token",
        ):
            await token_manager.ensure_token()

            # Токен установлен в api_key
            assert mock_api_client.configuration.api_key == {
                "iikoCookieAuth": "new-session-token"
            }
            assert token_manager._token == "new-session-token"
            assert token_manager._token_version == 1

    async def test_skips_fetch_when_token_exists(
        self, token_manager: TokenManager, mock_api_client: MagicMock
    ) -> None:
        """Пропускает получение, если токен уже есть."""
        token_manager._token = "existing-token"
        mock_api_client.configuration.api_key = {"iikoCookieAuth": "existing-token"}

        with patch.object(
            token_manager._session_api,
            "auth_get",
            new_callable=AsyncMock,
        ) as mock_auth:
            await token_manager.ensure_token()

            # Не должен был вызывать auth_get
            mock_auth.assert_not_awaited()

    async def test_raises_on_api_error(
        self, token_manager: TokenManager
    ) -> None:
        """Выбрасывает IikoServerAuthException при ошибке API."""
        with patch.object(
            token_manager._session_api,
            "auth_get",
            new_callable=AsyncMock,
            side_effect=Exception("API Error"),
        ):
            with pytest.raises(IikoServerAuthException, match="API Error"):
                await token_manager.ensure_token()


class TestRefreshToken:
    """Тесты refresh_token_if_401."""

    async def test_returns_false_for_non_401(
        self, token_manager: TokenManager
    ) -> None:
        """Возвращает False для не-401 ошибок."""
        error = Exception("Some error")

        result = await token_manager.refresh_token_if_401(error)

        assert result is False

    async def test_refreshes_on_401(
        self, token_manager: TokenManager, mock_api_client: MagicMock
    ) -> None:
        """Обновляет токен при 401 ошибке."""
        token_manager._token = "old-token"
        token_manager._token_version = 1
        mock_api_client.configuration.api_key = {"iikoCookieAuth": "old-token"}

        error = MagicMock()
        error.status = 401

        with patch.object(
            token_manager._session_api,
            "auth_get",
            new_callable=AsyncMock,
            return_value="refreshed-token",
        ):
            result = await token_manager.refresh_token_if_401(error)

            assert result is True
            assert token_manager._token == "refreshed-token"
            assert token_manager._token_version == 2
            assert mock_api_client.configuration.api_key == {
                "iikoCookieAuth": "refreshed-token"
            }

    async def test_concurrent_refresh_waits(
        self, token_manager: TokenManager, mock_api_client: MagicMock
    ) -> None:
        """Конкурентные обновления ждут завершения первого."""
        token_manager._token = "old-token"
        token_manager._token_version = 1

        call_count = 0

        async def slow_auth(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            return "new-token"

        error = MagicMock()
        error.status = 401

        with patch.object(
            token_manager._session_api,
            "auth_get",
            side_effect=slow_auth,
        ):
            # Запускаем несколько конкурентных обновлений
            results = await asyncio.gather(
                token_manager.refresh_token_if_401(error),
                token_manager.refresh_token_if_401(error),
            )

            # Оба должны вернуть True
            assert all(results)
            # Но API должен быть вызван только один раз
            assert call_count == 1


class TestLogout:
    """Тесты logout."""

    async def test_logout_clears_token(
        self, token_manager: TokenManager, mock_api_client: MagicMock
    ) -> None:
        """logout очищает токен и api_key."""
        token_manager._token = "session-token"
        mock_api_client.configuration.api_key = {"iikoCookieAuth": "session-token"}

        with patch.object(
            token_manager._session_api,
            "logout_get",
            new_callable=AsyncMock,
        ):
            await token_manager.logout()

            assert token_manager._token is None
            assert mock_api_client.configuration.api_key == {}

    async def test_logout_does_nothing_when_no_token(
        self, token_manager: TokenManager
    ) -> None:
        """logout ничего не делает, если токена нет."""
        token_manager._token = None

        with patch.object(
            token_manager._session_api,
            "logout_get",
            new_callable=AsyncMock,
        ) as mock_logout:
            await token_manager.logout()

            mock_logout.assert_not_awaited()

    async def test_logout_handles_errors_gracefully(
        self, token_manager: TokenManager, mock_api_client: MagicMock
    ) -> None:
        """logout обрабатывает ошибки gracefully."""
        token_manager._token = "session-token"
        mock_api_client.configuration.api_key = {"iikoCookieAuth": "session-token"}

        with patch.object(
            token_manager._session_api,
            "logout_get",
            new_callable=AsyncMock,
            side_effect=Exception("Logout failed"),
        ):
            # Не должно выбросить исключение
            await token_manager.logout()

            # Токен всё равно очищен
            assert token_manager._token is None
            assert mock_api_client.configuration.api_key == {}


class TestCloseAll:
    """Тесты close_all."""

    async def test_clears_instances(self, mock_api_client: MagicMock) -> None:
        """close_all очищает все экземпляры."""
        await TokenManager.close_all()

        await TokenManager.get_instance(mock_api_client, "login", "pass", "key1")
        await TokenManager.get_instance(mock_api_client, "login", "pass", "key2")

        assert len(TokenManager._instances) == 2

        await TokenManager.close_all()

        assert len(TokenManager._instances) == 0

    async def test_close_all_calls_logout(self, mock_api_client: MagicMock) -> None:
        """close_all вызывает logout для каждого экземпляра."""
        await TokenManager.close_all()

        manager1 = await TokenManager.get_instance(
            mock_api_client, "login", "pass", "key1"
        )
        manager2 = await TokenManager.get_instance(
            mock_api_client, "login", "pass", "key2"
        )

        # Устанавливаем токены
        manager1._token = "token1"
        manager2._token = "token2"

        with patch.object(
            manager1._session_api,
            "logout_get",
            new_callable=AsyncMock,
        ) as mock_logout1, patch.object(
            manager2._session_api,
            "logout_get",
            new_callable=AsyncMock,
        ) as mock_logout2:
            await TokenManager.close_all()

            # logout вызван для обоих
            mock_logout1.assert_awaited_once()
            mock_logout2.assert_awaited_once()
