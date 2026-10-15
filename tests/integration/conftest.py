"""Фикстуры integration-тестов: реальный PostgreSQL, миграции и очистка таблицы.

Тесты помечены маркером ``integration`` и требуют переменную окружения
``TEST_DATABASE_URL`` с отдельной (не рабочей) базой. SQLite не используется.
"""

import os
from collections.abc import AsyncIterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from deribit_tracker.infrastructure.db.models import TABLE_NAME
from deribit_tracker.infrastructure.db.session import create_engine_and_session_factory

TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"
_FALLBACK_BROKER_URL = "redis://localhost:6379/0"


def _test_database_url() -> str:
    url = os.environ.get(TEST_DATABASE_URL_ENV)
    if not url:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is not set; integration tests need a real PostgreSQL")
    return url


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Применяет миграции Alembic к тестовой базе перед прогоном."""
    url = _test_database_url()
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("CELERY_BROKER_URL", _FALLBACK_BROKER_URL)
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
async def integration_engine() -> AsyncIterator[AsyncEngine]:
    """Асинхронный движок к тестовой базе, закрывается после теста."""
    engine, _ = create_engine_and_session_factory(_test_database_url())
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def session_factory(
    integration_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий к тестовой базе."""
    return async_sessionmaker(integration_engine, expire_on_commit=False)


@pytest.fixture
async def clean_table(integration_engine: AsyncEngine) -> AsyncIterator[None]:
    """Очищает таблицу наблюдений перед каждым тестом."""
    async with integration_engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE TABLE {TABLE_NAME} RESTART IDENTITY"))
    yield
