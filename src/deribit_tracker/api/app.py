"""Фабрика FastAPI-приложения.

``create_app`` создаёт движок БД и фабрику сессий внутри lifespan: движком владеет
lifespan (закрывает его при завершении), а фабрика сессий передаётся HTTP-зависимостям
через ``app.state``. Глобальных экземпляров нет. Запуск:

``uvicorn deribit_tracker.api.app:create_app --factory``
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from deribit_tracker.api.exception_handlers import register_exception_handlers
from deribit_tracker.api.routes import router
from deribit_tracker.config import Settings
from deribit_tracker.infrastructure.db.session import (
    create_engine_and_session_factory,
    dispose_engine,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Собирает FastAPI-приложение с lifespan-владением ресурсами БД."""
    resolved_settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine, session_factory = create_engine_and_session_factory(resolved_settings.database_url)
        app.state.session_factory = session_factory
        try:
            yield
        finally:
            await dispose_engine(engine)

    app = FastAPI(title="Deribit Price Tracker", version="0.1.0", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(router)
    return app
