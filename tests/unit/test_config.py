"""Тесты конфигурации приложения."""

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from deribit_tracker.config import Settings

REQUIRED_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://deribit:deribit@localhost:55432/deribit_tracker",
    "CELERY_BROKER_URL": "redis://localhost:56379/0",
}

MANAGED_ENV_KEYS = (
    "DATABASE_URL",
    "CELERY_BROKER_URL",
    "DERIBIT_BASE_URL",
    "HTTP_TIMEOUT_SECONDS",
    "HTTP_RETRY_ATTEMPTS",
    "HTTP_RETRY_BACKOFF_SECONDS",
    "HTTP_RETRY_MAX_AFTER_SECONDS",
    "COLLECT_INTERVAL_SECONDS",
    "LOG_LEVEL",
)


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    """Изолирует переменные окружения, которыми управляет Settings."""
    for key in MANAGED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    env = dict(REQUIRED_ENV)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    yield env


def test_reads_required_values_from_env(
    settings_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")

    settings = Settings(_env_file=None)

    assert settings.database_url == settings_env["DATABASE_URL"]
    assert settings.celery_broker_url == settings_env["CELERY_BROKER_URL"]
    assert settings.log_level == "DEBUG"


def test_applies_defaults(settings_env: dict[str, str]) -> None:
    settings = Settings(_env_file=None)

    assert settings.deribit_base_url == "https://www.deribit.com/api/v2"
    assert settings.http_timeout_seconds == 10.0
    assert settings.http_retry_attempts == 3
    assert settings.http_retry_backoff_seconds == 0.5
    assert settings.http_retry_max_after_seconds == 5.0
    assert settings.collect_interval_seconds == 60
    assert settings.log_level == "INFO"


def test_rejects_non_asyncpg_database_url(
    settings_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://deribit:deribit@localhost:5432/deribit_tracker"
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_requires_database_url(
    settings_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_rejects_invalid_broker_scheme(
    settings_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_rejects_unknown_log_level(
    settings_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "TRACE")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("env_name", "value"),
    [
        ("HTTP_TIMEOUT_SECONDS", "0"),
        ("HTTP_RETRY_BACKOFF_SECONDS", "-1"),
        ("COLLECT_INTERVAL_SECONDS", "0"),
        ("HTTP_RETRY_ATTEMPTS", "0"),
    ],
)
def test_rejects_non_positive_numbers(
    settings_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    value: str,
) -> None:
    monkeypatch.setenv(env_name, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
