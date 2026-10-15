"""Composition root: сборка зависимостей приложения без глобальных экземпляров.

Здесь создаются настройки, логирование, движок БД, HTTP-клиент Deribit, сервисы и
Celery-приложение. Каждая точка входа (API, worker, beat, CLI) создаёт нужные объекты
сама и владеет их жизненным циклом.
"""

import logging
import time
from collections.abc import Sequence
from types import TracebackType

from celery import Celery
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from deribit_tracker.application.services import CollectionReport, CollectPricesService
from deribit_tracker.config import Settings
from deribit_tracker.domain.models import SUPPORTED_TICKERS, Ticker
from deribit_tracker.infrastructure.celery import factory as celery_factory
from deribit_tracker.infrastructure.db.repository import SqlAlchemyPriceUnitOfWork
from deribit_tracker.infrastructure.db.session import (
    create_engine_and_session_factory,
    dispose_engine,
)
from deribit_tracker.infrastructure.deribit.client import DeribitClient

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class SystemClock:
    """Часы процесса: момент наблюдения в секундах UNIX UTC."""

    def now_unix_seconds(self) -> int:
        return int(time.time())


class CollectionRunner:
    """Асинхронный сценарий сбора, владеющий движком БД и HTTP-клиентом.

    Используется как асинхронный контекстный менеджер: вход открывает HTTP-сессию,
    выход закрывает её и освобождает движок БД. Это важно, потому что Celery-задача
    выполняет сценарий через ``asyncio.run`` и не должна переиспользовать ресурсы
    между разными event loop.
    """

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
        price_source: DeribitClient,
        clock: SystemClock,
        tickers: Sequence[Ticker] = SUPPORTED_TICKERS,
        logger: logging.Logger | None = None,
    ) -> None:
        self._engine = engine
        self._price_source = price_source
        self._service = CollectPricesService(
            price_source=price_source,
            unit_of_work=SqlAlchemyPriceUnitOfWork(session_factory),
            clock=clock,
            tickers=tickers,
            logger=logger,
        )

    async def __aenter__(self) -> CollectionRunner:
        await self._price_source.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            await self._price_source.__aexit__(exc_type, exc, traceback)
        finally:
            await dispose_engine(self._engine)

    async def collect_once(self) -> CollectionReport:
        """Выполняет один цикл сбора index price."""
        return await self._service.collect_once()


def setup_logging(level: str) -> None:
    """Настраивает стандартное логирование процесса."""
    logging.basicConfig(level=level, format=_LOG_FORMAT)


def create_collect_runner(settings: Settings) -> CollectionRunner:
    """Создаёт раннер сбора с собственным движком БД и HTTP-клиентом."""
    engine, session_factory = create_engine_and_session_factory(settings.database_url)
    price_source = DeribitClient(
        base_url=settings.deribit_base_url,
        timeout_seconds=settings.http_timeout_seconds,
        retry_attempts=settings.http_retry_attempts,
        retry_backoff_seconds=settings.http_retry_backoff_seconds,
        retry_max_after_seconds=settings.http_retry_max_after_seconds,
    )
    return CollectionRunner(
        engine=engine,
        session_factory=session_factory,
        price_source=price_source,
        clock=SystemClock(),
    )


def create_celery_app(settings: Settings) -> Celery:
    """Создаёт Celery-приложение с задачей сбора и расписанием раз в минуту."""
    return celery_factory.create_celery_app(
        settings,
        runner_factory=lambda: create_collect_runner(settings),
    )
