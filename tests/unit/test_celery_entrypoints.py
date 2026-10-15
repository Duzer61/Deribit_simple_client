"""Тесты entrypoints Celery worker/beat без реального брокера."""

import pytest

from deribit_tracker.infrastructure.celery import beat, worker

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/deribit_tracker"
BROKER_URL = "redis://localhost:6379/0"


class RecordingCeleryApp:
    """Celery-подобный объект, записывающий аргументы запуска."""

    def __init__(self) -> None:
        self.worker_calls: list[list[str]] = []
        self.start_calls: list[list[str]] = []

    def worker_main(self, argv: list[str]) -> None:
        self.worker_calls.append(list(argv))

    def start(self, argv: list[str]) -> None:
        self.start_calls.append(list(argv))


@pytest.fixture
def recording_app(monkeypatch: pytest.MonkeyPatch) -> RecordingCeleryApp:
    app = RecordingCeleryApp()
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CELERY_BROKER_URL", BROKER_URL)
    monkeypatch.setattr(worker, "create_celery_app", lambda settings: app)
    monkeypatch.setattr(beat, "create_celery_app", lambda settings: app)
    return app


def test_worker_main_runs_single_worker_with_concurrency_one(
    recording_app: RecordingCeleryApp,
) -> None:
    worker.main()

    assert len(recording_app.worker_calls) == 1
    argv = recording_app.worker_calls[0]
    assert argv[0] == "worker"
    assert "--concurrency=1" in argv


def test_beat_main_runs_single_beat(recording_app: RecordingCeleryApp) -> None:
    beat.main()

    assert len(recording_app.start_calls) == 1
    assert recording_app.start_calls[0][0] == "beat"
