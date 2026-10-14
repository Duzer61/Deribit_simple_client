"""Общие фикстуры unit-тестов: управляемый HTTP-сервер Deribit, часы и sleeper."""

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from aiohttp import ClientSession, ClientTimeout, web
from aiohttp.test_utils import TestServer

INDEX_PRICE_PATH = "/api/v2/public/get_index_price"
DEFAULT_PRICE_LITERAL = "81634.110000000001"


@dataclass
class StubResponse:
    """Ответ, который тестовый сервер отдаёт на очередной запрос."""

    status: int = 200
    raw_body: str | None = None
    payload: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    delay_seconds: float = 0.0


def index_price_response(price_literal: str = DEFAULT_PRICE_LITERAL) -> StubResponse:
    """Строит ответ в точности как у Deribit: числовой литерал сохраняется как есть."""
    body = (
        '{"jsonrpc":"2.0","result":{"estimated_delivery_price":'
        f"{price_literal}"
        ',"index_price":'
        f"{price_literal}"
        '},"usIn":1791990382715147,"usOut":1791990382715494,"usDiff":347,"testnet":false}'
    )
    return StubResponse(raw_body=body)


def jsonrpc_error_response(code: int = -32602, message: str = "Invalid params") -> StubResponse:
    """Строит JSON-RPC ошибку Deribit."""
    body = f'{{"jsonrpc":"2.0","error":{{"code":{code},"message":"{message}"}},"testnet":false}}'
    return StubResponse(raw_body=body)


class DeribitStub:
    """HTTP-сервер, который отвечает заданной очередью ответов и записывает запросы."""

    def __init__(self) -> None:
        self._queue: deque[StubResponse] = deque()
        self._last_response: StubResponse = index_price_response()
        self.requests: list[dict[str, str]] = []
        self.base_url = ""

    def enqueue(self, response: StubResponse) -> None:
        """Добавляет ответ; при исчерпании очереди повторяется последний ответ."""
        self._queue.append(response)
        self._last_response = response

    def enqueue_price(self, price_literal: str = DEFAULT_PRICE_LITERAL) -> None:
        self.enqueue(index_price_response(price_literal))

    @property
    def request_count(self) -> int:
        return len(self.requests)

    async def handle(self, request: web.Request) -> web.Response:
        self.requests.append(dict(request.query))
        response = self._queue.popleft() if self._queue else self._last_response
        if response.delay_seconds:
            await asyncio.sleep(response.delay_seconds)
        if response.raw_body is not None:
            return web.Response(
                text=response.raw_body,
                status=response.status,
                content_type="application/json",
                headers=response.headers,
            )
        return web.json_response(
            response.payload or {}, status=response.status, headers=response.headers
        )


@pytest.fixture
async def deribit_stub() -> AsyncIterator[DeribitStub]:
    """Поднимает локальный сервер, повторяющий контракт public/get_index_price."""
    stub = DeribitStub()
    app = web.Application()
    app.router.add_get(INDEX_PRICE_PATH, stub.handle)
    server = TestServer(app)
    await server.start_server()
    stub.base_url = f"{server.scheme}://{server.host}:{server.port}/api/v2"
    try:
        yield stub
    finally:
        await server.close()


class RecordingSleeper:
    """Заменяет ``asyncio.sleep``, чтобы тесты не ждали реальные паузы."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


class RecordingSessionFactory:
    """Создаёт ``ClientSession`` и запоминает их, чтобы проверить закрытие ресурсов."""

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.sessions: list[ClientSession] = []

    def __call__(self) -> ClientSession:
        session = ClientSession(timeout=ClientTimeout(total=self.timeout_seconds))
        self.sessions.append(session)
        return session


@pytest.fixture
def recording_sleeper() -> RecordingSleeper:
    return RecordingSleeper()


@pytest.fixture
def session_factory() -> RecordingSessionFactory:
    return RecordingSessionFactory()
