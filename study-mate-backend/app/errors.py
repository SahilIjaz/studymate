"""Typed application errors and the handlers that turn them into JSON.

Every error response has the same shape so the frontend can rely on it:

    {"error": {"code": "document_not_found", "message": "...", "request_id": "..."}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_config import get_logger, get_request_id

log = get_logger(__name__)


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or {}
        self.headers = headers or {}

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "request_id": get_request_id(),
        }
        if self.details:
            payload["details"] = self.details
        return {"error": payload}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class UpstreamError(AppError):
    """Claude or another dependency failed in a way the caller can't fix."""

    status_code = 502
    code = "upstream_error"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            log.error("app_error", extra={"code": exc.code, "detail": exc.message})
        return JSONResponse(exc.to_payload(), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        err = ValidationError("Request failed validation.", details={"errors": exc.errors()})
        return JSONResponse(err.to_payload(), status_code=err.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        err = AppError(str(exc.detail), code="http_error", status_code=exc.status_code)
        return JSONResponse(err.to_payload(), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error")
        err = AppError("Something went wrong on our side.", code="internal_error", status_code=500)
        return JSONResponse(err.to_payload(), status_code=500)
