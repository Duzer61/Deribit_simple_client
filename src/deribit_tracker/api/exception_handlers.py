"""Обработчики ошибок HTTP API.

Клиенту возвращается понятный ``detail`` без SQL, паролей и traceback; внутренние
ошибки логируются на сервере.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from deribit_tracker.domain.exceptions import PriceNotFoundError, StorageUnavailableError

STORAGE_UNAVAILABLE_DETAIL = "Price storage is temporarily unavailable"


async def _handle_price_not_found(request: Request, exc: Exception) -> JSONResponse:
    detail = str(exc) or "price observation not found"
    return JSONResponse(status_code=404, content={"detail": detail})


async def _handle_storage_unavailable(request: Request, exc: Exception) -> JSONResponse:
    logger = logging.getLogger(__name__)
    logger.error("price storage is unavailable", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": STORAGE_UNAVAILABLE_DETAIL})


def register_exception_handlers(app: FastAPI) -> None:
    """Регистрирует обработчики доменных ошибок на приложении."""
    app.add_exception_handler(PriceNotFoundError, _handle_price_not_found)
    app.add_exception_handler(StorageUnavailableError, _handle_storage_unavailable)
