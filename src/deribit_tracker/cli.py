"""CLI: разовый запуск цикла сбора для проверки.

Команда вызывает тот же application-сценарий, что и периодическая Celery-задача,
а не дублирует реализацию сбора.
"""

import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence

from deribit_tracker.application.ports import CollectionRunner
from deribit_tracker.application.services import CollectionReport
from deribit_tracker.bootstrap import create_collect_runner, setup_logging
from deribit_tracker.config import Settings

RunnerFactory = Callable[[Settings], CollectionRunner]


def main(
    argv: Sequence[str] | None = None,
    *,
    runner_factory: RunnerFactory = create_collect_runner,
) -> int:
    """Запускает команду CLI и возвращает код завершения."""
    parser = argparse.ArgumentParser(prog="deribit_tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("collect-prices", help="Run a single price collection cycle")
    parser.parse_args(argv)

    settings = Settings()
    setup_logging(settings.log_level)
    report = asyncio.run(_collect_once(runner_factory(settings)))
    _print_report(report)
    return 1 if report.failures else 0


async def _collect_once(runner: CollectionRunner) -> CollectionReport:
    async with runner:
        return await runner.collect_once()


def _print_report(report: CollectionReport) -> None:
    for observation in report.saved:
        print(
            f"saved ticker={observation.ticker.value} "
            f"price={observation.price} timestamp={observation.timestamp}",
            file=sys.stdout,
        )
    for failure in report.failures:
        print(
            f"failed ticker={failure.ticker.value} reason={failure.reason}",
            file=sys.stdout,
        )
    print(f"collected saved={len(report.saved)} failures={len(report.failures)}")


if __name__ == "__main__":
    raise SystemExit(main())
