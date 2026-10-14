"""Доменные модели: поддерживаемые тикеры, наблюдение цены и UTC-границы дня."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Final

from deribit_tracker.domain.exceptions import InvalidObservationError, InvalidPriceError


class Ticker(StrEnum):
    """Поддерживаемые index price валюты Deribit."""

    BTC_USD = "btc_usd"
    ETH_USD = "eth_usd"


SUPPORTED_TICKERS: Final[tuple[Ticker, ...]] = (Ticker.BTC_USD, Ticker.ETH_USD)


def _validate_ticker(ticker: object) -> None:
    if not isinstance(ticker, Ticker):
        msg = f"ticker must be a Ticker, got {type(ticker).__name__}"
        raise InvalidObservationError(msg)


def _validate_price(price: object) -> None:
    if isinstance(price, bool) or not isinstance(price, Decimal):
        msg = f"price must be a Decimal, got {type(price).__name__}"
        raise InvalidPriceError(msg)
    if not price.is_finite():
        msg = "price must be a finite number"
        raise InvalidPriceError(msg)
    if price <= 0:
        msg = "price must be greater than zero"
        raise InvalidPriceError(msg)


def _validate_timestamp(timestamp: object) -> None:
    if isinstance(timestamp, bool) or not isinstance(timestamp, int):
        msg = f"timestamp must be an int, got {type(timestamp).__name__}"
        raise InvalidObservationError(msg)
    if timestamp < 0:
        msg = "timestamp must be a non-negative UNIX timestamp in seconds"
        raise InvalidObservationError(msg)


@dataclass(frozen=True, slots=True)
class PriceObservation:
    """Наблюдение index price.

    Время наблюдения — момент получения корректной цены клиентом, в секундах UNIX UTC.
    Цена хранится как ``Decimal``, чтобы не терять точность.
    """

    ticker: Ticker
    price: Decimal
    timestamp: int
    id: int | None = None

    def __post_init__(self) -> None:
        _validate_ticker(self.ticker)
        _validate_price(self.price)
        _validate_timestamp(self.timestamp)


def utc_day_bounds(day: date) -> tuple[int, int]:
    """Возвращает календарный день UTC как полуинтервал секунд UNIX ``[start, end)``."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())
