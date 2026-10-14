"""Клиент публичного метода Deribit ``public/get_index_price``.

Клиент создаёт одну ``aiohttp.ClientSession`` на время работы (``async with``) и закрывает её
при выходе. Повторные попытки выполняет только клиент и только для временных ошибок.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal
from types import TracebackType
from typing import Any, Self

import aiohttp

from deribit_tracker.domain.exceptions import (
    PriceSourceError,
    PriceSourceHttpError,
    PriceSourceInvalidResponseError,
    PriceSourceRateLimitedError,
    PriceSourceTimeoutError,
    PriceSourceUnavailableError,
)
from deribit_tracker.domain.models import Ticker

INDEX_PRICE_PATH = "/public/get_index_price"
_TOO_MANY_REQUESTS = 429
_SERVER_ERROR_STATUS = 500

Sleeper = Callable[[float], Awaitable[None]]
SessionFactory = Callable[[], aiohttp.ClientSession]


class DeribitClient:
    """Асинхронный клиент index price Deribit для поддерживаемых тикеров."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 0.5,
        retry_max_after_seconds: float = 5.0,
        session_factory: SessionFactory | None = None,
        sleeper: Sleeper = asyncio.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._retry_attempts = retry_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        self._retry_max_after_seconds = retry_max_after_seconds
        self._session_factory = session_factory or self._create_session
        self._sleeper = sleeper
        self._logger = logger if logger is not None else logging.getLogger(__name__)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> Self:
        if self._session is not None:
            msg = "DeribitClient is already opened"
            raise RuntimeError(msg)
        self._session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._session
        self._session = None
        if session is not None:
            await session.close()

    async def fetch_index_price(self, ticker: Ticker) -> Decimal:
        """Возвращает index price тикера или выбрасывает ``PriceSourceError``."""
        session = self._require_session()
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return await self._fetch_attempt(session, ticker)
            except PriceSourceError as error:
                delay = self._retry_delay(error, attempt)
                if delay is None or attempt == self._retry_attempts:
                    self._logger.warning(
                        "index price request failed ticker=%s attempt=%d error=%s",
                        ticker.value,
                        attempt,
                        type(error).__name__,
                    )
                    raise
                self._logger.warning(
                    "retrying index price request ticker=%s attempt=%d error=%s delay=%.3f",
                    ticker.value,
                    attempt,
                    type(error).__name__,
                    delay,
                )
                await self._sleeper(delay)
        msg = "retry loop must return or raise"
        raise AssertionError(msg)

    def _create_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self._timeout_seconds))

    def _require_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            msg = "DeribitClient must be used as an async context manager"
            raise RuntimeError(msg)
        return self._session

    async def _fetch_attempt(self, session: aiohttp.ClientSession, ticker: Ticker) -> Decimal:
        url = f"{self._base_url}{INDEX_PRICE_PATH}"
        try:
            async with session.get(url, params={"index_name": ticker.value}) as response:
                status = response.status
                headers = response.headers
                body = await response.read()
        except TimeoutError as error:
            msg = f"timeout after {self._timeout_seconds}s"
            raise PriceSourceTimeoutError(msg) from error
        except aiohttp.ClientError as error:
            msg = f"network error: {type(error).__name__}"
            raise PriceSourceUnavailableError(msg) from error

        if status == _TOO_MANY_REQUESTS:
            raise PriceSourceRateLimitedError(retry_after_seconds=self._parse_retry_after(headers))
        if status >= 400:
            raise PriceSourceHttpError(status_code=status)
        return self._extract_index_price(self._decode_body(body), ticker)

    def _decode_body(self, body: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(body, parse_float=Decimal)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            msg = "response body is not valid JSON"
            raise PriceSourceInvalidResponseError(msg) from error
        if not isinstance(payload, dict):
            msg = "response body must be a JSON object"
            raise PriceSourceInvalidResponseError(msg)
        return payload

    def _extract_index_price(self, payload: dict[str, Any], ticker: Ticker) -> Decimal:
        if payload.get("error") is not None:
            reason = self._describe_jsonrpc_error(payload["error"])
            msg = f"JSON-RPC error for {ticker.value}: {reason}"
            raise PriceSourceInvalidResponseError(msg)
        result = payload.get("result")
        if not isinstance(result, dict) or "index_price" not in result:
            msg = f"result.index_price is missing for {ticker.value}"
            raise PriceSourceInvalidResponseError(msg)
        return self._parse_price(result["index_price"], ticker)

    def _parse_price(self, raw_price: Any, ticker: Ticker) -> Decimal:
        if isinstance(raw_price, bool) or not isinstance(raw_price, (Decimal, int)):
            msg = f"index_price must be a number for {ticker.value}, got {type(raw_price).__name__}"
            raise PriceSourceInvalidResponseError(msg)
        price = raw_price if isinstance(raw_price, Decimal) else Decimal(raw_price)
        if not price.is_finite():
            msg = f"index_price must be finite for {ticker.value}"
            raise PriceSourceInvalidResponseError(msg)
        if price <= 0:
            msg = f"index_price must be positive for {ticker.value}"
            raise PriceSourceInvalidResponseError(msg)
        return price

    @staticmethod
    def _describe_jsonrpc_error(error: Any) -> str:
        if isinstance(error, dict):
            return f"code={error.get('code')} message={error.get('message')}"
        return str(error)

    @staticmethod
    def _parse_retry_after(headers: Mapping[str, str]) -> float | None:
        value = headers.get("Retry-After")
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            return None

    def _retry_delay(self, error: PriceSourceError, attempt: int) -> float | None:
        """Возвращает паузу до следующей попытки или ``None``, если повторять бессмысленно."""
        if isinstance(error, PriceSourceRateLimitedError):
            if error.retry_after_seconds is None:
                return self._backoff_delay(attempt)
            return min(error.retry_after_seconds, self._retry_max_after_seconds)
        if isinstance(error, (PriceSourceTimeoutError, PriceSourceUnavailableError)):
            return self._backoff_delay(attempt)
        if isinstance(error, PriceSourceHttpError) and error.status_code >= _SERVER_ERROR_STATUS:
            return self._backoff_delay(attempt)
        return None

    def _backoff_delay(self, attempt: int) -> float:
        multiplier = float(2 ** (attempt - 1))
        return self._retry_backoff_seconds * multiplier
