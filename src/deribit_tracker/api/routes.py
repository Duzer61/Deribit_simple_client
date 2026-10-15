"""Маршруты HTTP API: только чтение сохранённых наблюдений.

Все три обязательных метода — GET с обязательным query-параметром ``ticker``.
API не обращается к Deribit: он читает уже сохранённые данные из PostgreSQL.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from deribit_tracker.api.dependencies import get_price_query_service
from deribit_tracker.api.schemas import HealthResponse, PriceObservationResponse
from deribit_tracker.application.services import PriceQueryService
from deribit_tracker.domain.models import Ticker

router = APIRouter()

TickerQuery = Annotated[
    Ticker,
    Query(description="Supported ticker: btc_usd or eth_usd"),
]
DateQuery = Annotated[
    date,
    Query(alias="date", description="UTC calendar day in YYYY-MM-DD format"),
]
PriceQueryServiceDep = Annotated[PriceQueryService, Depends(get_price_query_service)]


@router.get("/api/v1/prices", response_model=list[PriceObservationResponse])
async def list_prices(
    ticker: TickerQuery,
    service: PriceQueryServiceDep,
) -> list[PriceObservationResponse]:
    """Возвращает все сохранённые наблюдения тикера."""
    observations = await service.list_prices(ticker)
    return [PriceObservationResponse.from_observation(item) for item in observations]


@router.get("/api/v1/prices/latest", response_model=PriceObservationResponse)
async def get_latest_price(
    ticker: TickerQuery,
    service: PriceQueryServiceDep,
) -> PriceObservationResponse:
    """Возвращает последнее сохранённое наблюдение тикера."""
    observation = await service.get_latest_price(ticker)
    return PriceObservationResponse.from_observation(observation)


@router.get("/api/v1/prices/by-date", response_model=list[PriceObservationResponse])
async def list_prices_by_date(
    ticker: TickerQuery,
    service: PriceQueryServiceDep,
    day: DateQuery,
) -> list[PriceObservationResponse]:
    """Возвращает наблюдения тикера за календарный день UTC."""
    observations = await service.list_prices_for_date(ticker, day)
    return [PriceObservationResponse.from_observation(item) for item in observations]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Технический healthcheck; тикер не требуется."""
    return HealthResponse(status="ok")
