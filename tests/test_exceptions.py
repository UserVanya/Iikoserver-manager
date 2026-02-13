"""Тесты для exceptions модуля."""

import pytest

from iikoserver.exceptions import (
    IikoServerAuthException,
    IikoServerException,
)

# Маркируем все тесты в этом модуле как unit-тесты
pytestmark = pytest.mark.unit


class TestIikoServerException:
    """Тесты для базового исключения."""

    def test_message(self) -> None:
        """Сообщение сохраняется корректно."""
        exc = IikoServerException("Test error")

        assert str(exc) == "Test error"

    def test_original_error(self) -> None:
        """Оригинальная ошибка сохраняется."""
        original = ValueError("Original error")
        exc = IikoServerException("Wrapped error", original_error=original)

        assert exc.original_error is original

    def test_original_error_default_none(self) -> None:
        """По умолчанию original_error = None."""
        exc = IikoServerException("Error")

        assert exc.original_error is None


class TestIikoServerAuthException:
    """Тесты для исключения аутентификации."""

    def test_inherits_from_base(self) -> None:
        """IikoServerAuthException наследуется от IikoServerException."""
        exc = IikoServerAuthException("Auth failed")

        assert isinstance(exc, IikoServerException)
        assert isinstance(exc, Exception)

    def test_catch_by_base_class(self) -> None:
        """IikoServerAuthException ловится базовым классом."""
        with pytest.raises(IikoServerException):
            raise IikoServerAuthException("Auth failed")

    def test_catch_specific(self) -> None:
        """IikoServerAuthException можно поймать отдельно."""
        with pytest.raises(IikoServerAuthException):
            raise IikoServerAuthException("Auth failed")

    def test_with_original_error(self) -> None:
        """IikoServerAuthException сохраняет оригинальную ошибку."""
        original = ConnectionError("Connection refused")
        exc = IikoServerAuthException("Auth failed", original_error=original)

        assert exc.original_error is original
        assert str(exc) == "Auth failed"
