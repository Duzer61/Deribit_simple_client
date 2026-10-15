"""Порты прикладного слоя: часы, источник цен и хранилище наблюдений.

Порты описаны через ``typing.Protocol``: приложению важна только форма объекта,
а не конкретный класс инфраструктуры.
"""

from collections.abc import Sequence
from decimal import Decimal
from types import TracebackType
from typing import TYPE_CHECKING, Protocol

from deribit_tracker.domain.models import PriceObservation, Ticker

if TYPE_CHECKING:
    from deribit_tracker.application.services import CollectionReport


class Clock(Protocol):
    """Источник текущего времени наблюдения в секундах UNIX UTC."""

    def now_unix_seconds(self) -> int:
        """Возвращает момент наблюдения в секундах UNIX UTC."""
        ...


class PriceSource(Protocol):
    """Источник index price по поддерживаемому тикеру."""

    async def fetch_index_price(self, ticker: Ticker) -> Decimal:
        """Возвращает index price тикера или выбрасывает ошибку источника."""
        ...


class PriceRepository(Protocol):
    """Операции хранения и чтения наблюдений цены."""

    async def add(self, observation: PriceObservation) -> PriceObservation:
        """Сохраняет наблюдение и возвращает его с присвоенным идентификатором."""
        ...

    async def list_by_ticker(self, ticker: Ticker) -> Sequence[PriceObservation]:
        """Возвращает все наблюдения тикера с сортировкой ``timestamp ASC, id ASC``."""
        ...

    async def get_latest(self, ticker: Ticker) -> PriceObservation | None:
        """Возвращает последнее наблюдение тикера или ``None``, если данных нет."""
        ...

    async def list_by_timestamp_range(
        self, ticker: Ticker, start_timestamp: int, end_timestamp: int
    ) -> Sequence[PriceObservation]:
        """Возвращает наблюдения в полуинтервале ``[start_timestamp, end_timestamp)``."""
        ...


class PriceUnitOfWork(Protocol):
    """Единица работы: владеет транзакцией и отдаёт репозиторий наблюдений."""

    async def __aenter__(self) -> PriceRepository:
        """Открывает сессию и возвращает репозиторий в её рамках."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        """Фиксирует или откатывает транзакцию и закрывает сессию."""
        ...


class CollectionRunner(Protocol):
    """Асинхронный сценарий сбора, который вызывает периодическая задача.

    Реализация — асинхронный контекстный менеджер, возвращающий себя из ``__aenter__``
    и владеющий собственными ресурсами (engine, HTTP-сессия).
    """

    async def __aenter__(self) -> CollectionRunner:
        """Открывает ресурсы сбора и возвращает раннер."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрывает ресурсы сбора."""
        ...

    async def collect_once(self) -> CollectionReport:
        """Выполняет один цикл сбора и возвращает отчёт."""
        ...
