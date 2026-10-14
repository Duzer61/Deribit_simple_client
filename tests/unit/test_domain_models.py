"""Тесты доменных моделей и UTC-границ дня."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from deribit_tracker.domain.exceptions import InvalidObservationError, InvalidPriceError
from deribit_tracker.domain.models import (
    SUPPORTED_TICKERS,
    PriceObservation,
    Ticker,
    utc_day_bounds,
)


def build_observation(
    price: object = Decimal("81634.11"),
    timestamp: object = 1791990570,
    ticker: Ticker = Ticker.BTC_USD,
) -> PriceObservation:
    return PriceObservation(ticker=ticker, price=price, timestamp=timestamp)  # type: ignore[arg-type]


def test_ticker_values_are_lower_case_index_names() -> None:
    assert Ticker.BTC_USD.value == "btc_usd"
    assert Ticker.ETH_USD.value == "eth_usd"
    assert SUPPORTED_TICKERS == (Ticker.BTC_USD, Ticker.ETH_USD)


def test_accepts_valid_observation() -> None:
    observation = build_observation()

    assert observation.ticker is Ticker.BTC_USD
    assert observation.price == Decimal("81634.11")
    assert observation.timestamp == 1791990570
    assert observation.id is None


def test_keeps_decimal_precision() -> None:
    precise = Decimal("81634.110000000001")

    assert build_observation(price=precise).price == precise


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("-0.000000001"), Decimal("-1")])
def test_rejects_non_positive_price(price: Decimal) -> None:
    with pytest.raises(InvalidPriceError):
        build_observation(price=price)


@pytest.mark.parametrize("price", [True, False])
def test_rejects_bool_price(price: bool) -> None:
    with pytest.raises(InvalidPriceError):
        build_observation(price=price)


def test_rejects_float_price() -> None:
    with pytest.raises(InvalidPriceError):
        build_observation(price=81634.11)


def test_rejects_string_price() -> None:
    with pytest.raises(InvalidPriceError):
        build_observation(price="81634.11")


@pytest.mark.parametrize("price", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_rejects_non_finite_price(price: Decimal) -> None:
    with pytest.raises(InvalidPriceError):
        build_observation(price=price)


@pytest.mark.parametrize("timestamp", [-1, -1791990570])
def test_rejects_negative_timestamp(timestamp: int) -> None:
    with pytest.raises(InvalidObservationError):
        build_observation(timestamp=timestamp)


def test_rejects_non_integer_timestamp() -> None:
    with pytest.raises(InvalidObservationError):
        build_observation(timestamp="1791990570")


def _within_day(bounds: tuple[int, int], timestamp: int) -> bool:
    start, end = bounds
    return start <= timestamp < end


def test_utc_day_bounds_are_utc_midnights() -> None:
    assert utc_day_bounds(date(2026, 10, 14)) == (1791936000, 1792022400)


def test_utc_day_bounds_include_day_start() -> None:
    bounds = utc_day_bounds(date(2026, 10, 14))

    assert _within_day(bounds, 1791936000)


def test_utc_day_bounds_exclude_second_before_day_start() -> None:
    bounds = utc_day_bounds(date(2026, 10, 14))

    assert not _within_day(bounds, 1791936000 - 1)


def test_utc_day_bounds_include_second_before_next_day_start() -> None:
    bounds = utc_day_bounds(date(2026, 10, 14))

    assert _within_day(bounds, 1792022400 - 1)


def test_utc_day_bounds_exclude_next_day_start() -> None:
    bounds = utc_day_bounds(date(2026, 10, 14))

    assert not _within_day(bounds, 1792022400)


def test_utc_day_bounds_span_exactly_one_day() -> None:
    start, end = utc_day_bounds(date(2026, 10, 14))

    assert end - start == int(timedelta(days=1).total_seconds())


def test_utc_day_bounds_handle_month_boundary() -> None:
    last_of_month = date(2026, 10, 31)

    assert utc_day_bounds(last_of_month)[1] == int(datetime(2026, 11, 1, tzinfo=UTC).timestamp())
