"""Настройки приложения.

Значения читаются из переменных окружения (и из ``.env`` при локальном запуске)
и валидируются при старте процесса. Экземпляр ``Settings`` создаётся в точках входа
(``bootstrap``, ``worker``, ``beat``, ``cli``) и передаётся явно — глобального экземпляра нет.
"""

from typing import Final

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DATABASE_URL_PREFIX: Final = "postgresql+asyncpg://"
_BROKER_URL_SCHEMES: Final = ("redis://", "rediss://")
_LOG_LEVELS: Final = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class Settings(BaseSettings):
    """Параметры окружения сервиса."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    celery_broker_url: str
    deribit_base_url: str = "https://www.deribit.com/api/v2"
    http_timeout_seconds: float = Field(default=10.0, gt=0)
    http_retry_attempts: int = Field(default=3, ge=1)
    http_retry_backoff_seconds: float = Field(default=0.5, ge=0)
    http_retry_max_after_seconds: float = Field(default=5.0, ge=0)
    collect_interval_seconds: int = Field(default=60, gt=0)
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        if not value.startswith(_DATABASE_URL_PREFIX):
            msg = f"database_url must start with {_DATABASE_URL_PREFIX!r}"
            raise ValueError(msg)
        return value

    @field_validator("celery_broker_url")
    @classmethod
    def _validate_celery_broker_url(cls, value: str) -> str:
        if not value.startswith(_BROKER_URL_SCHEMES):
            msg = "celery_broker_url must use redis:// or rediss:// scheme"
            raise ValueError(msg)
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in _LOG_LEVELS:
            msg = f"log_level must be one of {sorted(_LOG_LEVELS)}"
            raise ValueError(msg)
        return normalized
