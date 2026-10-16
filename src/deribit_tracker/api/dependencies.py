"""FastAPI-зависимости: берут ресурсы из ``app.state``.

Никаких глобальных экземпляров: фабрика сессий создаётся в ``create_app`` внутри
lifespan и передаётся через состояние приложения.
"""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deribit_tracker.application.services import PriceQueryService
from deribit_tracker.infrastructure.db.repository import SqlAlchemyPriceUnitOfWork


def get_price_query_service(request: Request) -> PriceQueryService:
    """Строит сервис чтения цен на одну HTTP-обработку."""
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return PriceQueryService(unit_of_work=SqlAlchemyPriceUnitOfWork(session_factory))
