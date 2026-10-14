"""Тесты aiohttp-клиента Deribit (без обращения к реальной бирже)."""

from decimal import Decimal

import conftest
import pytest

from deribit_tracker.domain.exceptions import (
    PriceSourceHttpError,
    PriceSourceInvalidResponseError,
    PriceSourceRateLimitedError,
    PriceSourceTimeoutError,
    PriceSourceUnavailableError,
)
from deribit_tracker.domain.models import Ticker
from deribit_tracker.infrastructure.deribit.client import DeribitClient


def build_client(
    stub: conftest.DeribitStub,
    sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
    *,
    retry_attempts: int = 3,
    retry_backoff_seconds: float = 0.01,
    retry_max_after_seconds: float = 5.0,
) -> DeribitClient:
    return DeribitClient(
        base_url=stub.base_url,
        timeout_seconds=10.0,
        retry_attempts=retry_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        retry_max_after_seconds=retry_max_after_seconds,
        session_factory=session_factory,
        sleeper=sleeper,
    )


async def test_requests_btc_index_price(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
) -> None:
    deribit_stub.enqueue_price("81634.11")
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    async with client:
        price = await client.fetch_index_price(Ticker.BTC_USD)

    assert price == Decimal("81634.11")
    assert deribit_stub.requests == [{"index_name": "btc_usd"}]
    assert deribit_stub.request_count == 1


async def test_requests_eth_index_price(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
) -> None:
    deribit_stub.enqueue_price("2427.98")
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    async with client:
        price = await client.fetch_index_price(Ticker.ETH_USD)

    assert price == Decimal("2427.98")
    assert deribit_stub.requests == [{"index_name": "eth_usd"}]


async def test_returns_decimal_without_float_rounding(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
) -> None:
    deribit_stub.enqueue_price("81634.110000000001")
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    async with client:
        price = await client.fetch_index_price(Ticker.BTC_USD)

    assert isinstance(price, Decimal)
    assert price == Decimal("81634.110000000001")
    assert str(price) == "81634.110000000001"


async def test_maps_timeout_to_timeout_error_and_retries_three_times(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
) -> None:
    session_factory = conftest.RecordingSessionFactory(timeout_seconds=0.05)
    deribit_stub.enqueue(conftest.StubResponse(delay_seconds=0.3))
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    with pytest.raises(PriceSourceTimeoutError):
        async with client:
            await client.fetch_index_price(Ticker.BTC_USD)

    assert deribit_stub.request_count == 3
    assert recording_sleeper.delays == [0.01, 0.02]


async def test_retries_on_http_500_then_succeeds(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
) -> None:
    deribit_stub.enqueue(conftest.StubResponse(status=500))
    deribit_stub.enqueue_price("81634.11")
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    async with client:
        price = await client.fetch_index_price(Ticker.BTC_USD)

    assert price == Decimal("81634.11")
    assert deribit_stub.request_count == 2
    assert recording_sleeper.delays == [0.01]


async def test_respects_retry_after_capped_by_max_after(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
) -> None:
    deribit_stub.enqueue(conftest.StubResponse(status=429, headers={"Retry-After": "60"}))
    deribit_stub.enqueue_price("81634.11")
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    async with client:
        price = await client.fetch_index_price(Ticker.BTC_USD)

    assert price == Decimal("81634.11")
    assert recording_sleeper.delays == [5.0]


async def test_raises_rate_limited_after_exhausted_retries(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
) -> None:
    deribit_stub.enqueue(conftest.StubResponse(status=429))
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    with pytest.raises(PriceSourceRateLimitedError):
        async with client:
            await client.fetch_index_price(Ticker.BTC_USD)

    assert deribit_stub.request_count == 3


async def test_does_not_retry_on_http_400(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
) -> None:
    deribit_stub.enqueue(
        conftest.StubResponse(status=400, raw_body=conftest.jsonrpc_error_response().raw_body)
    )
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    with pytest.raises(PriceSourceHttpError) as error_info:
        async with client:
            await client.fetch_index_price(Ticker.BTC_USD)

    assert error_info.value.status_code == 400
    assert deribit_stub.request_count == 1
    assert recording_sleeper.delays == []


async def test_raises_invalid_response_on_jsonrpc_error_with_http_200(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
) -> None:
    deribit_stub.enqueue(conftest.jsonrpc_error_response())
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    with pytest.raises(PriceSourceInvalidResponseError):
        async with client:
            await client.fetch_index_price(Ticker.BTC_USD)

    assert deribit_stub.request_count == 1
    assert recording_sleeper.delays == []


@pytest.mark.parametrize(
    "raw_body",
    [
        '{"jsonrpc":"2.0"}',
        '{"jsonrpc":"2.0","result":null}',
        '{"jsonrpc":"2.0","result":{"estimated_delivery_price":81634.11}}',
    ],
)
async def test_raises_invalid_response_when_result_or_price_missing(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
    raw_body: str,
) -> None:
    deribit_stub.enqueue(conftest.StubResponse(raw_body=raw_body))
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    with pytest.raises(PriceSourceInvalidResponseError):
        async with client:
            await client.fetch_index_price(Ticker.BTC_USD)

    assert deribit_stub.request_count == 1


@pytest.mark.parametrize("price_literal", ["0", "-1", "true", '"81634.11"', "null"])
async def test_rejects_invalid_price_literals(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
    price_literal: str,
) -> None:
    deribit_stub.enqueue(conftest.index_price_response(price_literal))
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    with pytest.raises(PriceSourceInvalidResponseError):
        async with client:
            await client.fetch_index_price(Ticker.BTC_USD)


async def test_raises_invalid_response_on_broken_json_body(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
) -> None:
    deribit_stub.enqueue(conftest.StubResponse(raw_body="{not-a-json"))
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    with pytest.raises(PriceSourceInvalidResponseError):
        async with client:
            await client.fetch_index_price(Ticker.BTC_USD)

    assert deribit_stub.request_count == 1


async def test_maps_connection_error_to_unavailable_after_retries(
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
) -> None:
    client = DeribitClient(
        base_url="http://127.0.0.1:1/api/v2",
        timeout_seconds=1.0,
        retry_attempts=2,
        retry_backoff_seconds=0.01,
        session_factory=session_factory,
        sleeper=recording_sleeper,
    )

    with pytest.raises(PriceSourceUnavailableError):
        async with client:
            await client.fetch_index_price(Ticker.BTC_USD)

    assert recording_sleeper.delays == [0.01]


async def test_session_is_created_on_enter_and_closed_on_exit(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
) -> None:
    deribit_stub.enqueue_price("81634.11")
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    assert session_factory.sessions == []

    async with client:
        assert len(session_factory.sessions) == 1
        assert session_factory.sessions[0].closed is False
        await client.fetch_index_price(Ticker.BTC_USD)

    assert session_factory.sessions[0].closed is True


async def test_fetch_without_context_manager_raises_runtime_error(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
) -> None:
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    with pytest.raises(RuntimeError):
        await client.fetch_index_price(Ticker.BTC_USD)

    assert session_factory.sessions == []


async def test_fetch_after_context_exit_raises_runtime_error(
    deribit_stub: conftest.DeribitStub,
    recording_sleeper: conftest.RecordingSleeper,
    session_factory: conftest.RecordingSessionFactory,
) -> None:
    deribit_stub.enqueue_price("81634.11")
    client = build_client(deribit_stub, recording_sleeper, session_factory)

    async with client:
        await client.fetch_index_price(Ticker.BTC_USD)

    with pytest.raises(RuntimeError):
        await client.fetch_index_price(Ticker.BTC_USD)
