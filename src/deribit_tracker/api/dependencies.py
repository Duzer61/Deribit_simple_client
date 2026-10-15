"""FastAPI-зависимости: берут ресурсы из ``app.state``.

Никаких глобальных экземпляров: настройки, движок и фабрика сессий создаются в
``create_app`` и передаются через состояние приложения.
"""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from deribit_tracker.application.services import PriceQueryService
from deribit_tracker.config import Settings
from deribit_tracker.infrastructure.db.repository import SqlAlchemyPriceUnitOfWork


def get_settings(request: Request) -> Settings:
    """Возвращает настройки приложения."""
    return request.app.state.settings  # type: ignore[no-any-return]


def get_engine(request: Request) -> AsyncEngine:
    """Возвращает асинхронный движок БД."""
    return request.app.state.engine  # type: ignore[no-any-return]


def get_price_query_service(request: Request) -> PriceQueryService:
    """Строит сервис чтения цен на одну HTTP-обработку."""
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return PriceQueryService(unit_of_work=SqlAlchemyPriceUnitOfWork(session_factory))
