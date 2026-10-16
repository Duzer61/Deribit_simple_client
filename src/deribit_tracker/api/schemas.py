"""Pydantic-схемы ответов HTTP API."""

from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer

from deribit_tracker.domain.models import PriceObservation, Ticker


class PriceObservationResponse(BaseModel):
    """Сохранённое наблюдение цены.

    ``price`` отдаётся строкой, чтобы не терять точность ``Decimal`` при JSON-сериализации.
    """

    id: int
    ticker: Ticker
    price: Decimal = Field(description="Index price as decimal string")
    timestamp: int = Field(description="Observation time: UNIX timestamp in seconds (UTC)")

    @field_serializer("price")
    def _serialize_price(self, value: Decimal) -> str:
        return str(value)

    @classmethod
    def from_observation(cls, observation: PriceObservation) -> PriceObservationResponse:
        """Строит ответ из доменного наблюдения; требует сохранённый идентификатор."""
        observation_id = observation.id
        if observation_id is None:
            msg = "stored observation must have an identifier"
            raise ValueError(msg)
        return cls(
            id=observation_id,
            ticker=observation.ticker,
            price=observation.price,
            timestamp=observation.timestamp,
        )


class HealthResponse(BaseModel):
    """Ответ технического healthcheck."""

    status: str
