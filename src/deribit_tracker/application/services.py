"""Прикладные сценарии: периодический сбор index price и чтение наблюдений."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from deribit_tracker.application.ports import Clock, PriceSource, PriceUnitOfWork
from deribit_tracker.domain.exceptions import PriceNotFoundError, PriceSourceError
from deribit_tracker.domain.models import (
    SUPPORTED_TICKERS,
    PriceObservation,
    Ticker,
    utc_day_bounds,
)


@dataclass(frozen=True, slots=True)
class CollectionFailure:
    """Причина неудачного получения index price одного тикера."""

    ticker: Ticker
    reason: str


@dataclass(frozen=True, slots=True)
class CollectionReport:
    """Итог одного цикла сбора: сохранённые наблюдения и неудачи по тикерам."""

    saved: tuple[PriceObservation, ...] = ()
    failures: tuple[CollectionFailure, ...] = ()


class CollectPricesService:
    """Собирает index price поддерживаемых тикеров и сохраняет наблюдения.

    Сетевой запрос выполняется **вне** транзакции БД, а наблюдение пишется отдельной
    короткой транзакцией. Ошибка одного тикера не мешает сбору второго.
    """

    def __init__(
        self,
        *,
        price_source: PriceSource,
        unit_of_work: PriceUnitOfWork,
        clock: Clock,
        tickers: Sequence[Ticker] = SUPPORTED_TICKERS,
        logger: logging.Logger | None = None,
    ) -> None:
        self._price_source = price_source
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._tickers = tuple(tickers)
        self._logger = logger if logger is not None else logging.getLogger(__name__)

    async def collect_once(self) -> CollectionReport:
        """Один цикл сбора: получает и сохраняет цену каждого тикера."""
        saved: list[PriceObservation] = []
        failures: list[CollectionFailure] = []
        for ticker in self._tickers:
            try:
                price = await self._price_source.fetch_index_price(ticker)
            except PriceSourceError as error:
                self._logger.warning(
                    "failed to fetch index price ticker=%s error=%s reason=%s",
                    ticker.value,
                    type(error).__name__,
                    error,
                )
                failures.append(CollectionFailure(ticker=ticker, reason=str(error)))
                continue
            observation = PriceObservation(
                ticker=ticker,
                price=price,
                timestamp=self._clock.now_unix_seconds(),
            )
            async with self._unit_of_work as repository:
                stored = await repository.add(observation)
            saved.append(stored)
        return CollectionReport(saved=tuple(saved), failures=tuple(failures))


class PriceQueryService:
    """Читает сохранённые наблюдения цены из хранилища.

    Сервис только читает уже собранные данные и не обращается к бирже.
    """

    def __init__(
        self,
        *,
        unit_of_work: PriceUnitOfWork,
        logger: logging.Logger | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._logger = logger if logger is not None else logging.getLogger(__name__)

    async def list_prices(self, ticker: Ticker) -> Sequence[PriceObservation]:
        """Возвращает все наблюдения тикера в порядке ``timestamp ASC, id ASC``."""
        async with self._unit_of_work as repository:
            return await repository.list_by_ticker(ticker)

    async def get_latest_price(self, ticker: Ticker) -> PriceObservation:
        """Возвращает последнее сохранённое наблюдение тикера.

        Если наблюдений нет, выбрасывает ``PriceNotFoundError``.
        """
        async with self._unit_of_work as repository:
            observation = await repository.get_latest(ticker)
        if observation is None:
            raise PriceNotFoundError(f"no price observations stored for {ticker.value}")
        return observation

    async def list_prices_for_date(self, ticker: Ticker, day: date) -> Sequence[PriceObservation]:
        """Возвращает наблюдения тикера за календарный день UTC (``[start, end)``)."""
        start_timestamp, end_timestamp = utc_day_bounds(day)
        async with self._unit_of_work as repository:
            return await repository.list_by_timestamp_range(ticker, start_timestamp, end_timestamp)
