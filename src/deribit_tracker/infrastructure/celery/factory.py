"""Фабрика Celery-приложения: broker, расписание и регистрация задачи сбора.

Фабрика не создаёт глобальный Celery-объект: экземпляр возвращается вызывающему
и создаётся в точках входа (``worker``, ``beat``, ``bootstrap``).
"""

import logging

from celery import Celery

from deribit_tracker.config import Settings
from deribit_tracker.infrastructure.celery.tasks import (
    COLLECT_PRICES_SCHEDULE_KEY,
    COLLECT_PRICES_TASK_NAME,
    COLLECT_SCHEDULE_SECONDS,
    RunnerFactory,
    register_collect_prices_task,
)

__all__ = [
    "COLLECT_PRICES_TASK_NAME",
    "COLLECT_SCHEDULE_SECONDS",
    "create_celery_app",
]


def create_celery_app(
    settings: Settings,
    runner_factory: RunnerFactory,
    logger: logging.Logger | None = None,
) -> Celery:
    """Создаёт Celery-приложение с Redis-broker и расписанием раз в минуту.

    Result backend не настраивается: результаты задач не используются.
    """
    celery_app = Celery("deribit_tracker", broker=settings.celery_broker_url)
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        task_ignore_result=True,
        enable_utc=True,
        timezone="UTC",
        beat_schedule={
            COLLECT_PRICES_SCHEDULE_KEY: {
                "task": COLLECT_PRICES_TASK_NAME,
                "schedule": COLLECT_SCHEDULE_SECONDS,
            }
        },
    )
    register_collect_prices_task(celery_app, runner_factory, logger=logger)
    return celery_app
