"""Тесты конфигурации Celery: регистрация задачи, расписание и вызов сценария.

Тесты не требуют реального брокера: Celery-приложение только конфигурируется,
а зарегистрированная задача вызывается как обычная синхронная функция.

Celery хранит задачу по имени в общем на процесс состоянии: повторная регистрация
одного имени перезаписывает функцию задачи. Поэтому приложение создаётся один раз
на модуль, а каждый тест подменяет раннер через ``RunnerHolder``.
"""

import inspect
from typing import Any

import pytest

from deribit_tracker.application.services import CollectionReport
from deribit_tracker.config import Settings
from deribit_tracker.infrastructure.celery.factory import (
    COLLECT_PRICES_TASK_NAME,
    COLLECT_SCHEDULE_SECONDS,
    create_celery_app,
)


class FakeRunner:
    """Асинхронный раннер, который считает вызовы сценария сбора."""

    def __init__(self) -> None:
        self.entered = 0
        self.collect_calls = 0

    async def __aenter__(self) -> FakeRunner:
        self.entered += 1
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    async def collect_once(self) -> CollectionReport:
        self.collect_calls += 1
        return CollectionReport()


class RunnerHolder:
    """Изменяемый источник раннера: позволяет подменять раннер между тестами."""

    def __init__(self) -> None:
        self.runner = FakeRunner()

    def __call__(self) -> FakeRunner:
        return self.runner


def build_settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/deribit_tracker",
        celery_broker_url="redis://localhost:6379/0",
    )


@pytest.fixture(scope="module")
def celery_app() -> tuple[Any, RunnerHolder]:
    holder = RunnerHolder()
    return create_celery_app(build_settings(), holder), holder


@pytest.fixture
def runner(celery_app: tuple[Any, RunnerHolder]) -> FakeRunner:
    _, holder = celery_app
    holder.runner = FakeRunner()
    return holder.runner


def test_task_is_registered_under_expected_name(celery_app: tuple[Any, RunnerHolder]) -> None:
    app, _ = celery_app

    assert COLLECT_PRICES_TASK_NAME in app.tasks
    assert app.tasks[COLLECT_PRICES_TASK_NAME].name == COLLECT_PRICES_TASK_NAME


def test_beat_schedule_runs_every_60_seconds(celery_app: tuple[Any, RunnerHolder]) -> None:
    app, _ = celery_app

    schedules = [
        entry
        for entry in app.conf.beat_schedule.values()
        if entry["task"] == COLLECT_PRICES_TASK_NAME
    ]

    assert len(schedules) == 1
    assert schedules[0]["schedule"] == COLLECT_SCHEDULE_SECONDS == 60.0


def test_task_invokes_application_scenario(
    celery_app: tuple[Any, RunnerHolder],
    runner: FakeRunner,
) -> None:
    app, _ = celery_app
    task = app.tasks[COLLECT_PRICES_TASK_NAME]

    result = task()

    assert runner.entered == 1
    assert runner.collect_calls == 1
    assert isinstance(result, CollectionReport)


def test_task_is_not_a_coroutine_function(celery_app: tuple[Any, RunnerHolder]) -> None:
    app, _ = celery_app
    task = app.tasks[COLLECT_PRICES_TASK_NAME]

    assert not inspect.iscoroutinefunction(task.run)


def test_no_result_backend_configured(celery_app: tuple[Any, RunnerHolder]) -> None:
    app, _ = celery_app

    assert app.conf.result_backend is None
    assert app.conf.task_ignore_result is True
