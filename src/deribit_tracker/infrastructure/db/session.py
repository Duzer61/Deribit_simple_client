"""Создание и закрытие асинхронного движка и фабрики сессий SQLAlchemy.

Движок и фабрика создаются в composition root (bootstrap/lifespan) и передаются явно —
глобальных экземпляров нет.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine_and_session_factory(
    database_url: str,
    *,
    echo: bool = False,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Создаёт асинхронный движок и фабрику сессий для указанной БД."""
    engine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


async def dispose_engine(engine: AsyncEngine) -> None:
    """Закрывает пул соединений движка при завершении приложения."""
    await engine.dispose()
