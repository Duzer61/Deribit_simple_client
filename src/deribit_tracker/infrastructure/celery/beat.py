"""Entrypoint Celery beat.

Должен работать ровно в одном экземпляре: расписание раз в минуту выдаёт задача сбора.
"""

from celery import Celery

from deribit_tracker.bootstrap import create_celery_app, setup_logging
from deribit_tracker.config import Settings


def main() -> None:
    """Создаёт Celery-приложение и запускает beat."""
    settings = Settings()
    setup_logging(settings.log_level)
    celery_app: Celery = create_celery_app(settings)
    celery_app.start(["beat", f"--loglevel={settings.log_level}"])


if __name__ == "__main__":
    main()
