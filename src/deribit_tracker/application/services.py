"""Прикладные сценарии: периодический сбор index price и чтение наблюдений."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from deribit_tracker.application.ports import Clock, PriceSource, PriceUnitOfWork
from deribit_tracker.domain.exceptions import PriceSourceError
from deribit_tracker.domain.models import SUPPORTED_TICKERS, PriceObservation, Ticker


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
