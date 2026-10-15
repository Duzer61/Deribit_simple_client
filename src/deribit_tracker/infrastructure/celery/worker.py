"""Entrypoint Celery worker.

Запускает единственный worker с ``concurrency=1`` (для тестового задания этого
достаточно) и настраивает логирование из окружения.
"""

from celery import Celery

from deribit_tracker.bootstrap import create_celery_app, setup_logging
from deribit_tracker.config import Settings


def main() -> None:
    """Создаёт Celery-приложение и запускает worker."""
    settings = Settings()
    setup_logging(settings.log_level)
    celery_app: Celery = create_celery_app(settings)
    celery_app.worker_main(["worker", f"--loglevel={settings.log_level}", "--concurrency=1"])


if __name__ == "__main__":
    main()
