"""Репозиторий наблюдений цены на SQLAlchemy (async) и единица работы.

Репозиторий отдаёт доменные ``PriceObservation`` и не выпускает ORM-строки наружу.
Транзакцией владеет ``SqlAlchemyPriceUnitOfWork``: ``commit`` при успехе, ``rollback``
при исключении, ``close`` в любом случае.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deribit_tracker.domain.exceptions import StorageUnavailableError
from deribit_tracker.domain.models import PriceObservation, Ticker
from deribit_tracker.infrastructure.db.models import PriceObservationRow


def _to_domain(row: PriceObservationRow) -> PriceObservation:
    """Преобразует ORM-строку в доменное наблюдение."""
    return PriceObservation(
        id=row.id,
        ticker=Ticker(row.ticker),
        price=row.price,
        timestamp=row.timestamp,
    )


class SqlAlchemyPriceRepository:
    """Операции чтения и записи наблюдений в рамках одной сессии."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, observation: PriceObservation) -> PriceObservation:
        """Сохраняет наблюдение и возвращает его с присвоенным идентификатором."""
        row = PriceObservationRow(
            ticker=observation.ticker.value,
            price=observation.price,
            timestamp=observation.timestamp,
        )
        try:
            self._session.add(row)
            await self._session.flush()
        except (SQLAlchemyError, OSError) as error:
            msg = "failed to store price observation"
            raise StorageUnavailableError(msg) from error
        return _to_domain(row)

    async def list_by_ticker(self, ticker: Ticker) -> Sequence[PriceObservation]:
        """Возвращает все наблюдения тикера с сортировкой ``timestamp ASC, id ASC``."""
        statement = (
            select(PriceObservationRow)
            .where(PriceObservationRow.ticker == ticker.value)
            .order_by(PriceObservationRow.timestamp.asc(), PriceObservationRow.id.asc())
        )
        rows = await self._fetch(statement)
        return [_to_domain(row) for row in rows]

    async def get_latest(self, ticker: Ticker) -> PriceObservation | None:
        """Возвращает последнее наблюдение тикера или ``None``, если данных нет."""
        statement = (
            select(PriceObservationRow)
            .where(PriceObservationRow.ticker == ticker.value)
            .order_by(PriceObservationRow.timestamp.desc(), PriceObservationRow.id.desc())
            .limit(1)
        )
        rows = await self._fetch(statement)
        return _to_domain(rows[0]) if rows else None

    async def list_by_timestamp_range(
        self, ticker: Ticker, start_timestamp: int, end_timestamp: int
    ) -> Sequence[PriceObservation]:
        """Возвращает наблюдения в полуинтервале ``[start_timestamp, end_timestamp)``."""
        statement = (
            select(PriceObservationRow)
            .where(
                PriceObservationRow.ticker == ticker.value,
                PriceObservationRow.timestamp >= start_timestamp,
                PriceObservationRow.timestamp < end_timestamp,
            )
            .order_by(PriceObservationRow.timestamp.asc(), PriceObservationRow.id.asc())
        )
        rows = await self._fetch(statement)
        return [_to_domain(row) for row in rows]

    async def _fetch(self, statement: Select[Any]) -> list[PriceObservationRow]:
        try:
            result = await self._session.execute(statement)
        except (SQLAlchemyError, OSError) as error:
            msg = "failed to read price observations"
            raise StorageUnavailableError(msg) from error
        return list(result.scalars().all())


class SqlAlchemyPriceUnitOfWork:
    """Единица работы: открывает сессию, владеет транзакцией и закрывает её."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> SqlAlchemyPriceRepository:
        if self._session is not None:
            msg = "SqlAlchemyPriceUnitOfWork is already opened"
            raise RuntimeError(msg)
        self._session = self._session_factory()
        return SqlAlchemyPriceRepository(self._session)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        session = self._session
        self._session = None
        if session is None:
            return
        try:
            if exc_type is None:
                await session.commit()
            else:
                await session.rollback()
        except (SQLAlchemyError, OSError) as error:
            msg = "failed to finalize price storage transaction"
            raise StorageUnavailableError(msg) from error
        finally:
            await session.close()
