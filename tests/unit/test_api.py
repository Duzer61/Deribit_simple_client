"""Тесты read-only HTTP API через ASGI transport с подменой зависимостей."""

from collections.abc import Sequence
from decimal import Decimal

import fakes
import pytest
from httpx import ASGITransport, AsyncClient

from deribit_tracker.api.app import create_app
from deribit_tracker.api.dependencies import get_price_query_service
from deribit_tracker.application.ports import PriceRepository
from deribit_tracker.application.services import PriceQueryService
from deribit_tracker.config import Settings
from deribit_tracker.domain.exceptions import StorageUnavailableError
from deribit_tracker.domain.models import PriceObservation, Ticker

DAY_START = 1791936000
NEXT_DAY_START = 1792022400
READ_ROUTES = ["/api/v1/prices", "/api/v1/prices/latest", "/api/v1/prices/by-date"]


class FailingUnitOfWork:
    """Единица работы, которая не может открыть сессию (хранилище недоступно)."""

    async def __aenter__(self) -> PriceRepository:
        raise StorageUnavailableError("connection refused: password=secret")

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


def build_settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/deribit_tracker",
        celery_broker_url="redis://localhost:6379/0",
    )


def build_service(observations: Sequence[PriceObservation] = ()) -> PriceQueryService:
    return PriceQueryService(unit_of_work=fakes.FakePriceUnitOfWork(list(observations)))


def build_client(service: PriceQueryService) -> AsyncClient:
    app = create_app(build_settings())
    app.dependency_overrides[get_price_query_service] = lambda: service
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def observation(
    ticker: Ticker,
    price: str,
    timestamp: int,
    observation_id: int,
) -> PriceObservation:
    return PriceObservation(
        ticker=ticker, price=Decimal(price), timestamp=timestamp, id=observation_id
    )


@pytest.mark.parametrize("route", READ_ROUTES)
async def test_missing_ticker_returns_422(route: str) -> None:
    async with build_client(build_service()) as client:
        response = await client.get(route)

    assert response.status_code == 422


async def test_returns_all_observations() -> None:
    first = observation(Ticker.BTC_USD, "81634.110000000001", DAY_START, 1)
    second = observation(Ticker.BTC_USD, "81640.00", DAY_START + 60, 2)
    service = build_service([first, second])

    async with build_client(service) as client:
        response = await client.get("/api/v1/prices", params={"ticker": "btc_usd"})

    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "ticker": "btc_usd", "price": "81634.110000000001", "timestamp": DAY_START},
        {"id": 2, "ticker": "btc_usd", "price": "81640.00", "timestamp": DAY_START + 60},
    ]


async def test_returns_empty_list_when_no_data() -> None:
    async with build_client(build_service()) as client:
        response = await client.get("/api/v1/prices", params={"ticker": "eth_usd"})

    assert response.status_code == 200
    assert response.json() == []


async def test_latest_returns_single_observation() -> None:
    older = observation(Ticker.ETH_USD, "2400.00", DAY_START, 1)
    newer = observation(Ticker.ETH_USD, "2427.98", DAY_START + 60, 2)
    service = build_service([older, newer])

    async with build_client(service) as client:
        response = await client.get("/api/v1/prices/latest", params={"ticker": "eth_usd"})

    assert response.status_code == 200
    assert response.json() == {
        "id": 2,
        "ticker": "eth_usd",
        "price": "2427.98",
        "timestamp": DAY_START + 60,
    }


async def test_latest_returns_404_with_detail_when_no_data() -> None:
    async with build_client(build_service()) as client:
        response = await client.get("/api/v1/prices/latest", params={"ticker": "btc_usd"})

    assert response.status_code == 404
    assert "btc_usd" in response.json()["detail"]


async def test_by_date_returns_observations_for_day() -> None:
    inside = observation(Ticker.BTC_USD, "81634.11", DAY_START + 10, 1)
    next_day = observation(Ticker.BTC_USD, "81640.00", NEXT_DAY_START, 2)
    service = build_service([inside, next_day])

    async with build_client(service) as client:
        response = await client.get(
            "/api/v1/prices/by-date",
            params={"ticker": "btc_usd", "date": "2026-10-14"},
        )

    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "ticker": "btc_usd", "price": "81634.11", "timestamp": DAY_START + 10}
    ]


async def test_by_date_requires_date_returns_422() -> None:
    async with build_client(build_service()) as client:
        response = await client.get("/api/v1/prices/by-date", params={"ticker": "btc_usd"})

    assert response.status_code == 422


async def test_by_date_invalid_date_returns_422() -> None:
    async with build_client(build_service()) as client:
        response = await client.get(
            "/api/v1/prices/by-date",
            params={"ticker": "btc_usd", "date": "2026-13-01"},
        )

    assert response.status_code == 422


async def test_by_date_empty_returns_200_and_empty_list() -> None:
    async with build_client(build_service()) as client:
        response = await client.get(
            "/api/v1/prices/by-date",
            params={"ticker": "btc_usd", "date": "2026-10-14"},
        )

    assert response.status_code == 200
    assert response.json() == []


async def test_storage_unavailable_returns_503_without_traceback() -> None:
    service = PriceQueryService(unit_of_work=FailingUnitOfWork())

    async with build_client(service) as client:
        response = await client.get("/api/v1/prices", params={"ticker": "btc_usd"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Price storage is temporarily unavailable"}
    assert "password" not in response.text
    assert "Traceback" not in response.text


async def test_health_returns_ok() -> None:
    async with build_client(build_service()) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("route", READ_ROUTES)
async def test_unsupported_ticker_returns_422(route: str) -> None:
    async with build_client(build_service()) as client:
        response = await client.get(route, params={"ticker": "btc"})

    assert response.status_code == 422
