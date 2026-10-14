"""Тесты сценария сбора index price."""

from decimal import Decimal

import fakes
import pytest
from deribit_tracker.application.services import CollectPricesService

from deribit_tracker.domain.exceptions import PriceSourceTimeoutError
from deribit_tracker.domain.models import Ticker

OBSERVATION_TIME = 1791990570


def build_service(
    source: fakes.FakePriceSource,
    unit_of_work: fakes.FakePriceUnitOfWork,
    clock: fakes.FixedClock,
) -> CollectPricesService:
    return CollectPricesService(price_source=source, unit_of_work=unit_of_work, clock=clock)


async def test_saves_both_tickers() -> None:
    source = fakes.FakePriceSource()
    source.set_price(Ticker.BTC_USD, "81634.11")
    source.set_price(Ticker.ETH_USD, "2427.98")
    unit_of_work = fakes.FakePriceUnitOfWork()
    service = build_service(source, unit_of_work, fakes.FixedClock(OBSERVATION_TIME))

    report = await service.collect_once()

    assert [item.ticker for item in report.saved] == [Ticker.BTC_USD, Ticker.ETH_USD]
    assert report.failures == ()
    assert [item.ticker for item in unit_of_work.added] == [Ticker.BTC_USD, Ticker.ETH_USD]


async def test_passes_ticker_price_and_clock_timestamp() -> None:
    source = fakes.FakePriceSource()
    source.set_price(Ticker.BTC_USD, "81634.110000000001")
    source.set_price(Ticker.ETH_USD, "2427.98")
    unit_of_work = fakes.FakePriceUnitOfWork()
    service = build_service(source, unit_of_work, fakes.FixedClock(OBSERVATION_TIME))

    await service.collect_once()

    assert source.requested == [Ticker.BTC_USD, Ticker.ETH_USD]
    btc, eth = unit_of_work.added
    assert btc.price == Decimal("81634.110000000001")
    assert btc.timestamp == OBSERVATION_TIME
    assert eth.price == Decimal("2427.98")
    assert eth.timestamp == OBSERVATION_TIME


async def test_uses_its_own_unit_of_work_per_observation() -> None:
    source = fakes.FakePriceSource()
    source.set_price(Ticker.BTC_USD, "81634.11")
    source.set_price(Ticker.ETH_USD, "2427.98")
    unit_of_work = fakes.FakePriceUnitOfWork()
    service = build_service(source, unit_of_work, fakes.FixedClock(OBSERVATION_TIME))

    await service.collect_once()

    assert unit_of_work.entered == 2
    assert unit_of_work.exited == 2
    assert unit_of_work.exceptions == [None, None]


async def test_btc_failure_does_not_prevent_eth_saving() -> None:
    source = fakes.FakePriceSource()
    source.set_error(Ticker.BTC_USD, PriceSourceTimeoutError("timeout"))
    source.set_price(Ticker.ETH_USD, "2427.98")
    unit_of_work = fakes.FakePriceUnitOfWork()
    service = build_service(source, unit_of_work, fakes.FixedClock(OBSERVATION_TIME))

    report = await service.collect_once()

    assert [item.ticker for item in report.saved] == [Ticker.ETH_USD]
    assert [failure.ticker for failure in report.failures] == [Ticker.BTC_USD]
    assert [item.ticker for item in unit_of_work.added] == [Ticker.ETH_USD]


async def test_eth_failure_does_not_discard_btc_saving() -> None:
    source = fakes.FakePriceSource()
    source.set_price(Ticker.BTC_USD, "81634.11")
    source.set_error(Ticker.ETH_USD, PriceSourceTimeoutError("timeout"))
    unit_of_work = fakes.FakePriceUnitOfWork()
    service = build_service(source, unit_of_work, fakes.FixedClock(OBSERVATION_TIME))

    report = await service.collect_once()

    assert [item.ticker for item in report.saved] == [Ticker.BTC_USD]
    assert [failure.ticker for failure in report.failures] == [Ticker.ETH_USD]


async def test_unsuccessful_fetch_creates_no_record() -> None:
    source = fakes.FakePriceSource()
    source.set_error(Ticker.BTC_USD, PriceSourceTimeoutError("timeout"))
    source.set_error(Ticker.ETH_USD, PriceSourceTimeoutError("timeout"))
    unit_of_work = fakes.FakePriceUnitOfWork()
    service = build_service(source, unit_of_work, fakes.FixedClock(OBSERVATION_TIME))

    report = await service.collect_once()

    assert report.saved == ()
    assert unit_of_work.added == []
    assert unit_of_work.entered == 0
    assert len(report.failures) == 2


async def test_source_error_is_logged_and_reported(caplog: pytest.LogCaptureFixture) -> None:
    source = fakes.FakePriceSource()
    source.set_error(Ticker.BTC_USD, PriceSourceTimeoutError("timeout"))
    source.set_price(Ticker.ETH_USD, "2427.98")
    unit_of_work = fakes.FakePriceUnitOfWork()
    service = build_service(source, unit_of_work, fakes.FixedClock(OBSERVATION_TIME))

    with caplog.at_level("WARNING"):
        report = await service.collect_once()

    assert "btc_usd" in caplog.text
    assert "PriceSourceTimeoutError" in caplog.text
    assert report.failures[0].reason == "timeout"


async def test_report_contains_saved_observations_with_identifiers() -> None:
    source = fakes.FakePriceSource()
    source.set_price(Ticker.BTC_USD, "81634.11")
    source.set_price(Ticker.ETH_USD, "2427.98")
    unit_of_work = fakes.FakePriceUnitOfWork()
    service = build_service(source, unit_of_work, fakes.FixedClock(OBSERVATION_TIME))

    report = await service.collect_once()

    assert [item.id for item in report.saved] == [1, 2]
