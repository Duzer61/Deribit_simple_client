"""Фейки прикладного слоя: источник цен, хранилище, единица работы и часы."""

from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal

from deribit_tracker.domain.models import PriceObservation, Ticker


class FakePriceSource:
    """Источник цен, управляемый тестом."""

    def __init__(self) -> None:
        self.prices: dict[Ticker, Decimal] = {}
        self.errors: dict[Ticker, Exception] = {}
        self.requested: list[Ticker] = []

    def set_price(self, ticker: Ticker, price: str) -> None:
        self.prices[ticker] = Decimal(price)

    def set_error(self, ticker: Ticker, error: Exception) -> None:
        self.errors[ticker] = error

    async def fetch_index_price(self, ticker: Ticker) -> Decimal:
        self.requested.append(ticker)
        error = self.errors.get(ticker)
        if error is not None:
            raise error
        return self.prices[ticker]


class FakePriceRepository:
    """Хранилище наблюдений в памяти с детерминированными сортировками."""

    def __init__(self, storage: list[PriceObservation], add_log: list[PriceObservation]) -> None:
        self._storage = storage
        self._add_log = add_log

    async def add(self, observation: PriceObservation) -> PriceObservation:
        stored = replace(observation, id=len(self._storage) + 1)
        self._storage.append(stored)
        self._add_log.append(stored)
        return stored

    async def list_by_ticker(self, ticker: Ticker) -> Sequence[PriceObservation]:
        matches = [item for item in self._storage if item.ticker is ticker]
        return sorted(matches, key=lambda item: (item.timestamp, item.id or 0))

    async def get_latest(self, ticker: Ticker) -> PriceObservation | None:
        matches = [item for item in self._storage if item.ticker is ticker]
        if not matches:
            return None
        return max(matches, key=lambda item: (item.timestamp, item.id or 0))

    async def list_by_timestamp_range(
        self, ticker: Ticker, start_timestamp: int, end_timestamp: int
    ) -> Sequence[PriceObservation]:
        matches = [
            item
            for item in self._storage
            if item.ticker is ticker and start_timestamp <= item.timestamp < end_timestamp
        ]
        return sorted(matches, key=lambda item: (item.timestamp, item.id or 0))


class FakePriceUnitOfWork:
    """Единица работы: отдаёт фейковый репозиторий и считает входы/выходы."""

    def __init__(self) -> None:
        self.storage: list[PriceObservation] = []
        self.added: list[PriceObservation] = []
        self.entered = 0
        self.exited = 0
        self.exceptions: list[BaseException | None] = []

    async def __aenter__(self) -> FakePriceRepository:
        self.entered += 1
        return FakePriceRepository(self.storage, self.added)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        self.exited += 1
        self.exceptions.append(exc)


class FixedClock:
    """Часы с фиксированным временем наблюдения."""

    def __init__(self, timestamp: int) -> None:
        self.timestamp = timestamp

    def now_unix_seconds(self) -> int:
        return self.timestamp
