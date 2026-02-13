"""Менеджер токенов для iikoserver API.

Управляет получением и обновлением токенов авторизации.
Токен обновляется только при получении 401 ошибки.
"""

import asyncio
import hashlib
import logging

from iikoserver_client import ApiClient, SessionManagementApi
from iikoserver_client.exceptions import UnauthorizedException

from iikoserver.exceptions import IikoServerAuthException

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)

def hash_password(password: str) -> str:
    """Хеширует пароль SHA1 для iikoserver API.

    Args:
        password: Пароль в открытом виде

    Returns:
        SHA1 хеш пароля в hex формате
    """
    return hashlib.sha1(password.encode("utf-8")).hexdigest()


class TokenManager:
    """Менеджер токенов для конкретного ApiClient.

    Токен запрашивается/обновляется только при 401 ошибке.
    Если обновление уже идёт — другие корутины ждут через Event.
    """

    _instances: dict[str, "TokenManager"] = {}
    _global_lock: asyncio.Lock | None = None

    def __init__(
        self,
        api_client: ApiClient,
        login: str,
        password: str,
        key_id: str,
    ) -> None:
        """Инициализация менеджера токенов.

        Args:
            api_client: Клиент API для установки токена
            login: Логин для получения токена
            password: Пароль в открытом виде (будет хеширован SHA1)
            key_id: Уникальный идентификатор ключа
        """
        self._api_client = api_client
        self._login = login
        self._password_hash = hash_password(password)
        self._key_id = key_id
        self._token: str | None = None
        self._token_version: int = 0
        self._session_api = SessionManagementApi(api_client=self._api_client)
        self._lock = asyncio.Lock()
        self._refresh_event = asyncio.Event()
        self._refresh_event.set()

    @classmethod
    async def get_instance(
        cls,
        api_client: ApiClient,
        login: str,
        password: str,
        key_id: str,
    ) -> "TokenManager":
        """Получить или создать экземпляр для данного key_id.

        Args:
            api_client: Клиент API
            login: Логин для получения токена
            password: Пароль в открытом виде
            key_id: Уникальный идентификатор ключа

        Returns:
            Экземпляр TokenManager
        """
        if cls._global_lock is None:
            cls._global_lock = asyncio.Lock()

        async with cls._global_lock:
            if key_id not in cls._instances:
                cls._instances[key_id] = cls(api_client, login, password, key_id)
            return cls._instances[key_id]

    async def _fetch_token(self) -> str:
        """Получить новый токен от API.

        Returns:
            Новый токен (строка ключа сессии)

        Raises:
            IikoServerAuthException: При ошибке получения токена
        """
        # Очищаем текущий токен перед запросом нового
        self._api_client.configuration.api_key = {}

        try:
            logger.debug("Запрос токена для key_id=%s", self._key_id)
            # Используем auth_get с login и SHA1 хешем пароля
            token = await self._session_api.auth_get(
                login=self._login,
                var_pass=self._password_hash,
            )
            return token
        except UnauthorizedException as exc:
            # 401 на auth запрос = некорректные учетные данные
            logger.error(
                "Некорректные учетные данные для key_id=%s: получен 401",
                self._key_id,
            )
            raise IikoServerAuthException(
                "Некорректные учетные данные: получен 401 на запрос авторизации",
                original_error=exc,
            ) from exc
        except Exception as exc:
            logger.error(
                "Ошибка при получении токена для key_id=%s: %s",
                self._key_id,
                exc,
            )
            raise IikoServerAuthException(
                f"Ошибка при получении токена: {exc}", original_error=exc
            ) from exc

    def _set_token(self, token: str) -> None:
        """Установить токен в конфигурацию клиента.

        Args:
            token: Токен авторизации
        """
        self._token = token
        # Для iikoserver токен устанавливается как cookie iikoCookieAuth
        self._api_client.configuration.api_key = {"iikoCookieAuth": token}

    async def ensure_token(self) -> None:
        """Получить токен, если его ещё нет."""
        if self._token is not None:
            return

        async with self._lock:
            # Double-check после получения lock
            if self._token is not None:
                return

            self._refresh_event.clear()
            try:
                token = await self._fetch_token()
                self._set_token(token)
                self._token_version += 1
                logger.info(
                    "Токен получен успешно для key_id=%s (версия: %d)",
                    self._key_id,
                    self._token_version,
                )
            finally:
                self._refresh_event.set()

    async def refresh_token_if_401(self, error: Exception) -> bool:
        """Обновить токен при 401 ошибке.

        Args:
            error: Исключение, которое может быть 401

        Returns:
            True если токен был обновлён, False если ошибка не 401

        Raises:
            IikoServerAuthException: При ошибке обновления токена
        """
        # Проверяем, что это действительно 401
        error_status = getattr(error, "status", None)
        is_401 = isinstance(error, UnauthorizedException) or error_status == 401
        if not is_401:
            logger.debug("Не 401 ошибка, пропускаем обновление токена")
            return False

        version_before = self._token_version
        logger.debug("Получена 401 ошибка, версия токена: %d", version_before)

        # Если кто-то уже обновляет — ждём
        if not self._refresh_event.is_set():
            logger.debug("Другая корутина обновляет токен, ожидаем...")
            await self._refresh_event.wait()
            return True

        async with self._lock:
            # Проверяем, не обновил ли кто-то токен пока мы ждали lock
            if self._token_version != version_before:
                logger.debug(
                    "Токен уже обновлён другой корутиной: %d -> %d",
                    version_before,
                    self._token_version,
                )
                return True

            self._refresh_event.clear()
            try:
                token = await self._fetch_token()
                self._set_token(token)
                self._token_version += 1
                logger.info(
                    "Токен обновлён после 401 для key_id=%s (версия: %d)",
                    self._key_id,
                    self._token_version,
                )
            except Exception as exc:
                logger.error(
                    "Ошибка при обновлении токена для key_id=%s: %s",
                    self._key_id,
                    exc,
                )
                self._token = None
                self._api_client.configuration.api_key = {}
                raise
            finally:
                self._refresh_event.set()

        return True

    async def logout(self) -> None:
        """Выйти из системы и освободить лицензию."""
        if self._token is None:
            return

        try:
            await self._session_api.logout_get(key=self._token)
            logger.info("Выход из системы для key_id=%s", self._key_id)
        except Exception as exc:
            logger.warning(
                "Ошибка при выходе из системы для key_id=%s: %s",
                self._key_id,
                exc,
            )
        finally:
            self._token = None
            self._api_client.configuration.api_key = {}

    @classmethod
    async def close_all(cls) -> None:
        """Закрыть все сессии и сбросить экземпляры."""
        for manager in cls._instances.values():
            await manager.logout()
        cls._instances.clear()
        cls._global_lock = None
