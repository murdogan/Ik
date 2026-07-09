from typing import Any

from fastapi import Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

TENANT_ID_HEADER = "X-Tenant-Id"
TENANT_SLUG_HEADER = "X-Tenant-Slug"


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
    correlation_id = exc.correlation_id or request.headers.get("X-Correlation-Id")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "correlation_id": correlation_id,
            }
        },
    )


async def request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> Response:
    if _has_missing_tenant_header_error(exc):
        return await api_error_handler(request, tenant_header_missing_error())
    return await request_validation_exception_handler(request, exc)


def tenant_header_missing_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="tenant_header_missing",
        message=f"{TENANT_ID_HEADER} header is required",
    )


def tenant_header_invalid_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="tenant_header_invalid",
        message=f"{TENANT_ID_HEADER} header must be a valid UUID",
    )


def tenant_slug_header_invalid_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="tenant_slug_header_invalid",
        message=f"{TENANT_SLUG_HEADER} header must be non-empty when provided",
    )


def _has_missing_tenant_header_error(exc: RequestValidationError) -> bool:
    return any(
        tuple(error.get("loc", ())) == ("header", TENANT_ID_HEADER)
        and error.get("type") == "missing"
        for error in exc.errors()
    )
