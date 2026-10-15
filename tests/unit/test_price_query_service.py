"""Тесты сценария чтения сохранённых цен."""

from datetime import date
from decimal import Decimal

import fakes
import pytest

from deribit_tracker.application.services import PriceQueryService
from deribit_tracker.domain.exceptions import PriceNotFoundError
from deribit_tracker.domain.models import PriceObservation, Ticker, utc_day_bounds

DAY = date(2026, 10, 14)
DAY_START = 1791936000
NEXT_DAY_START = 1792022400


def observation(
    ticker: Ticker,
    price: str,
    timestamp: int,
    observation_id: int | None = None,
) -> PriceObservation:
    return PriceObservation(
        ticker=ticker, price=Decimal(price), timestamp=timestamp, id=observation_id
    )


def build_service(
    storage: list[PriceObservation] | None = None,
) -> tuple[PriceQueryService, fakes.FakePriceUnitOfWork]:
    unit_of_work = fakes.FakePriceUnitOfWork(storage)
    return PriceQueryService(unit_of_work=unit_of_work), unit_of_work


async def test_lists_all_observations_for_ticker() -> None:
    btc_early = observation(Ticker.BTC_USD, "81634.11", DAY_START, 1)
    eth = observation(Ticker.ETH_USD, "2427.98", DAY_START + 60, 2)
    btc_late = observation(Ticker.BTC_USD, "81640.00", DAY_START + 120, 3)
    service, _ = build_service([btc_early, eth, btc_late])

    result = await service.list_prices(Ticker.BTC_USD)

    assert list(result) == [btc_early, btc_late]


async def test_lists_all_observations_returns_empty_for_unknown_data() -> None:
    service, _ = build_service()

    result = await service.list_prices(Ticker.ETH_USD)

    assert list(result) == []


async def test_latest_returns_repository_result() -> None:
    older = observation(Ticker.BTC_USD, "81634.11", DAY_START, 1)
    newer = observation(Ticker.BTC_USD, "81640.00", DAY_START + 60, 2)
    service, _ = build_service([older, newer])

    result = await service.get_latest_price(Ticker.BTC_USD)

    assert result == newer


async def test_latest_raises_price_not_found_when_empty() -> None:
    service, _ = build_service()

    with pytest.raises(PriceNotFoundError):
        await service.get_latest_price(Ticker.BTC_USD)


async def test_by_date_uses_utc_day_bounds() -> None:
    service, unit_of_work = build_service()

    await service.list_prices_for_date(Ticker.BTC_USD, DAY)

    assert unit_of_work.range_calls == [(Ticker.BTC_USD, DAY_START, NEXT_DAY_START)]
    assert utc_day_bounds(DAY) == (DAY_START, NEXT_DAY_START)


async def test_by_date_returns_matching_observations() -> None:
    inside = observation(Ticker.BTC_USD, "81634.11", DAY_START + 10, 1)
    next_day = observation(Ticker.BTC_USD, "81640.00", NEXT_DAY_START, 2)
    service, _ = build_service([inside, next_day])

    result = await service.list_prices_for_date(Ticker.BTC_USD, DAY)

    assert list(result) == [inside]


async def test_by_date_returns_empty_sequence_when_no_data() -> None:
    service, _ = build_service()

    result = await service.list_prices_for_date(Ticker.ETH_USD, DAY)

    assert list(result) == []
