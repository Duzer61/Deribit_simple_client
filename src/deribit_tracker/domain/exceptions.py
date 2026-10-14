"""Исключения предметной области.

Домен и приложение не зависят от конкретных библиотек (aiohttp, SQLAlchemy),
поэтому ошибки источника цен и хранилища объявлены здесь и не наследуются
от исключений инфраструктуры.
"""


class DomainError(Exception):
    """Базовая ошибка предметной области."""


class InvalidPriceError(DomainError):
    """Цена наблюдения отсутствует, имеет неверный тип или не положительна."""


class InvalidObservationError(DomainError):
    """Наблюдение цены некорректно (тикер или время наблюдения)."""


class PriceNotFoundError(DomainError):
    """В хранилище нет наблюдений для запрошенного тикера."""


class StorageUnavailableError(DomainError):
    """Хранилище цен недоступно: соединение, транзакция или запрос не выполнены."""


class PriceSourceError(DomainError):
    """Базовая ошибка источника цен."""


class PriceSourceTimeoutError(PriceSourceError):
    """Источник цен не ответил в отведённое время."""


class PriceSourceRateLimitedError(PriceSourceError):
    """Источник цен ограничил частоту запросов."""

    def __init__(self, retry_after_seconds: float | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        message = "price source rate limit exceeded"
        if retry_after_seconds is not None:
            message = f"{message} (retry after {retry_after_seconds:g}s)"
        super().__init__(message)


class PriceSourceUnavailableError(PriceSourceError):
    """Источник цен недоступен: сетевая или транспортная ошибка."""


class PriceSourceHttpError(PriceSourceError):
    """Источник цен ответил HTTP-ошибкой."""

    def __init__(self, status_code: int, message: str | None = None) -> None:
        self.status_code = status_code
        super().__init__(message or f"price source responded with HTTP {status_code}")


class PriceSourceInvalidResponseError(PriceSourceError):
    """Ответ источника цен не соответствует ожидаемому контракту."""
