"""Регистрация периодической задачи сбора index price.

Задача синхронная: Celery не умеет await-ить корутины, поэтому асинхронный сценарий
выполняется через ``asyncio.run``. Все асинхронные ресурсы (aiohttp-сессия, engine)
создаются и закрываются внутри этого вызова.
"""

import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from celery import Celery

from deribit_tracker.application.ports import CollectionRunner
from deribit_tracker.application.services import CollectionReport

COLLECT_PRICES_TASK_NAME = "deribit_tracker.collect_prices"
COLLECT_SCHEDULE_SECONDS = 60.0
COLLECT_PRICES_SCHEDULE_KEY = "collect-prices-every-minute"

RunnerFactory = Callable[[], AbstractAsyncContextManager[CollectionRunner]]


async def collect_once_with(runner_factory: RunnerFactory) -> CollectionReport:
    """Открывает раннер сбора как контекстный менеджер и выполняет один цикл."""
    async with runner_factory() as runner:
        return await runner.collect_once()


def register_collect_prices_task(
    celery_app: Celery,
    runner_factory: RunnerFactory,
    logger: logging.Logger | None = None,
) -> None:
    """Регистрирует синхронную задачу сбора в переданном Celery-приложении."""
    task_logger = logger if logger is not None else logging.getLogger(__name__)

    @celery_app.task(name=COLLECT_PRICES_TASK_NAME)  # type: ignore[untyped-decorator]
    def collect_prices() -> CollectionReport:
        report = asyncio.run(collect_once_with(runner_factory))
        task_logger.info(
            "collect prices finished saved=%d failures=%d",
            len(report.saved),
            len(report.failures),
        )
        return report
