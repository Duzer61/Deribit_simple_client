"""Тесты CLI-команды разового сбора ``collect-prices``."""

from decimal import Decimal

import pytest

from deribit_tracker.application.services import (
    CollectionFailure,
    CollectionReport,
)
from deribit_tracker.cli import main
from deribit_tracker.config import Settings
from deribit_tracker.domain.models import PriceObservation, Ticker

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/deribit_tracker"
BROKER_URL = "redis://localhost:6379/0"
OBSERVATION_TIME = 1791990570


class FakeRunner:
    """Раннер сбора, возвращающий заранее заданный отчёт."""

    def __init__(self, report: CollectionReport) -> None:
        self._report = report
        self.collect_calls = 0

    async def __aenter__(self) -> FakeRunner:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    async def collect_once(self) -> CollectionReport:
        self.collect_calls += 1
        return self._report


@pytest.fixture(autouse=True)
def _settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CELERY_BROKER_URL", BROKER_URL)


def test_collect_prices_prints_saved_observations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    observation = PriceObservation(
        ticker=Ticker.BTC_USD,
        price=Decimal("81634.11"),
        timestamp=OBSERVATION_TIME,
        id=7,
    )
    runner = FakeRunner(CollectionReport(saved=(observation,)))

    exit_code = main(["collect-prices"], runner_factory=lambda settings: runner)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert runner.collect_calls == 1
    assert "saved" in output
    assert "btc_usd" in output
    assert "81634.11" in output


def test_collect_prices_reports_failures_and_returns_nonzero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    failure = CollectionFailure(ticker=Ticker.ETH_USD, reason="timeout")
    runner = FakeRunner(CollectionReport(failures=(failure,)))

    exit_code = main(["collect-prices"], runner_factory=lambda settings: runner)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "failed" in output
    assert "eth_usd" in output


def test_collect_prices_passes_settings_to_runner_factory() -> None:
    received: list[Settings] = []

    def runner_factory(settings: Settings) -> FakeRunner:
        received.append(settings)
        return FakeRunner(CollectionReport())

    main(["collect-prices"], runner_factory=runner_factory)

    assert len(received) == 1
    assert received[0].database_url == DATABASE_URL
