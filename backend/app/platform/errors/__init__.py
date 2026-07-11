"""Stable HTTP error contract shared by API composition and module presentation."""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.platform.errors.application import ApplicationError
from app.platform.observability.correlation import (
    CORRELATION_ID_HEADER,
    correlation_response_headers,
    get_or_create_request_context,
    is_valid_request_id,
)

_PHASE0_ERROR_COMPATIBILITY_PREFIXES = (
    "/api/v1/dashboard",
    "/api/v1/employees",
    "/api/v1/leave-requests",
)


class ApiErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None
    correlation_id: str | None = None


class ApiErrorResponse(BaseModel):
    error: ApiErrorBody


class ApiError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.correlation_id = correlation_id


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    context = get_or_create_request_context(request)
    safe_metadata = context.safe_error_metadata()
    correlation_id = _error_correlation_id(request, exc, safe_metadata["request_id"])
    return JSONResponse(
        status_code=exc.status_code,
        headers={
            name.decode("ascii"): value.decode("ascii")
            for name, value in correlation_response_headers(context)
        },
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "correlation_id": correlation_id,
            }
        },
    )


def _error_correlation_id(
    request: Request,
    exc: ApiError,
    request_id: str,
) -> str | None:
    """Select only validated context metadata, with an explicit Phase-0 body adapter."""

    if exc.correlation_id == request_id and is_valid_request_id(exc.correlation_id):
        return request_id
    if request.url.path.startswith(_PHASE0_ERROR_COMPATIBILITY_PREFIXES):
        legacy_values = request.headers.getlist(CORRELATION_ID_HEADER)
        if (
            len(legacy_values) == 1
            and legacy_values[0] == request_id
            and is_valid_request_id(legacy_values[0])
        ):
            return request_id
        return None
    return request_id


__all__ = [
    "ApiError",
    "ApiErrorBody",
    "ApiErrorResponse",
    "ApplicationError",
    "api_error_handler",
]
