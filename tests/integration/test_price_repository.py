"""Integration-тесты репозитория цен на реальном PostgreSQL."""

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deribit_tracker.domain.models import PriceObservation, Ticker
from deribit_tracker.infrastructure.db.models import PriceObservationRow
from deribit_tracker.infrastructure.db.repository import SqlAlchemyPriceUnitOfWork

pytestmark = pytest.mark.integration

DAY_START = 1791936000


def observation(ticker: Ticker, price: str, timestamp: int) -> PriceObservation:
    return PriceObservation(ticker=ticker, price=Decimal(price), timestamp=timestamp)


async def test_saves_and_reads_decimal_without_precision_loss(
    session_factory: async_sessionmaker[AsyncSession],
    clean_table: None,
) -> None:
    unit_of_work = SqlAlchemyPriceUnitOfWork(session_factory)
    precise = "81634.110000000001"

    async with unit_of_work as repository:
        stored = await repository.add(observation(Ticker.BTC_USD, precise, DAY_START))

    assert stored.id is not None
    assert stored.price == Decimal(precise)

    async with unit_of_work as repository:
        loaded = await repository.list_by_ticker(Ticker.BTC_USD)

    assert [item.price for item in loaded] == [Decimal(precise)]
    assert str(loaded[0].price) == precise


async def test_filters_by_ticker(
    session_factory: async_sessionmaker[AsyncSession],
    clean_table: None,
) -> None:
    unit_of_work = SqlAlchemyPriceUnitOfWork(session_factory)

    async with unit_of_work as repository:
        await repository.add(observation(Ticker.BTC_USD, "81634.11", DAY_START))
        await repository.add(observation(Ticker.ETH_USD, "2427.98", DAY_START + 60))

    async with unit_of_work as repository:
        btc = await repository.list_by_ticker(Ticker.BTC_USD)
        eth = await repository.list_by_ticker(Ticker.ETH_USD)

    assert [item.ticker for item in btc] == [Ticker.BTC_USD]
    assert [item.ticker for item in eth] == [Ticker.ETH_USD]


async def test_latest_is_deterministic_for_equal_timestamps(
    session_factory: async_sessionmaker[AsyncSession],
    clean_table: None,
) -> None:
    unit_of_work = SqlAlchemyPriceUnitOfWork(session_factory)
    same_timestamp = DAY_START + 30

    async with unit_of_work as repository:
        await repository.add(observation(Ticker.BTC_USD, "100.00", same_timestamp))
        second = await repository.add(observation(Ticker.BTC_USD, "200.00", same_timestamp))

    async with unit_of_work as repository:
        latest = await repository.get_latest(Ticker.BTC_USD)

    assert latest is not None
    assert latest.id == second.id
    assert latest.price == Decimal("200.00")


async def test_returns_all_observations_sorted_by_timestamp_then_id(
    session_factory: async_sessionmaker[AsyncSession],
    clean_table: None,
) -> None:
    unit_of_work = SqlAlchemyPriceUnitOfWork(session_factory)

    async with unit_of_work as repository:
        later = await repository.add(observation(Ticker.BTC_USD, "300.00", DAY_START + 120))
        earlier_first = await repository.add(observation(Ticker.BTC_USD, "100.00", DAY_START))
        earlier_second = await repository.add(observation(Ticker.BTC_USD, "200.00", DAY_START))

    async with unit_of_work as repository:
        items = await repository.list_by_ticker(Ticker.BTC_USD)

    assert [item.id for item in items] == [earlier_first.id, earlier_second.id, later.id]


async def test_lists_observations_in_timestamp_range_inclusive_start_exclusive_end(
    session_factory: async_sessionmaker[AsyncSession],
    clean_table: None,
) -> None:
    unit_of_work = SqlAlchemyPriceUnitOfWork(session_factory)
    start = DAY_START
    end = DAY_START + 100

    async with unit_of_work as repository:
        before = await repository.add(observation(Ticker.BTC_USD, "50.00", start - 1))
        at_start = await repository.add(observation(Ticker.BTC_USD, "100.00", start))
        inside = await repository.add(observation(Ticker.BTC_USD, "150.00", end - 1))
        at_end = await repository.add(observation(Ticker.BTC_USD, "200.00", end))

    async with unit_of_work as repository:
        items = await repository.list_by_timestamp_range(Ticker.BTC_USD, start, end)

    returned_ids = [item.id for item in items]
    assert returned_ids == [at_start.id, inside.id]
    assert before.id not in returned_ids
    assert at_end.id not in returned_ids


async def test_returns_none_for_latest_when_ticker_empty(
    session_factory: async_sessionmaker[AsyncSession],
    clean_table: None,
) -> None:
    unit_of_work = SqlAlchemyPriceUnitOfWork(session_factory)

    async with unit_of_work as repository:
        latest = await repository.get_latest(Ticker.ETH_USD)

    assert latest is None


async def test_rejects_non_positive_price_by_check_constraint(
    session_factory: async_sessionmaker[AsyncSession],
    clean_table: None,
) -> None:
    async with session_factory() as session:
        session.add(PriceObservationRow(ticker="btc_usd", price=Decimal("0"), timestamp=DAY_START))
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


async def test_rejects_unsupported_ticker_by_check_constraint(
    session_factory: async_sessionmaker[AsyncSession],
    clean_table: None,
) -> None:
    async with session_factory() as session:
        session.add(PriceObservationRow(ticker="doge_usd", price=Decimal("1"), timestamp=DAY_START))
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
