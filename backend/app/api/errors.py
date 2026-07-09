from typing import Any

from fastapi import Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

TENANT_ID_HEADER = "X-Tenant-Id"
TENANT_SLUG_HEADER = "X-Tenant-Slug"
EMPLOYEE_API_PREFIX = "/api/v1/employees"
LEAVE_BALANCE_API_SEGMENT = "/leave-balances"
LEAVE_REQUEST_API_PREFIX = "/api/v1/leave-requests"

EMPLOYEE_VALIDATION_ERROR_CODE = "employee_validation_error"
EMPLOYEE_VALIDATION_ERROR_MESSAGE = "Employee request validation failed"
LEAVE_BALANCE_VALIDATION_ERROR_CODE = "leave_balance_validation_error"
LEAVE_BALANCE_VALIDATION_ERROR_MESSAGE = "Leave balance request validation failed"
LEAVE_REQUEST_VALIDATION_ERROR_CODE = "leave_request_validation_error"
LEAVE_REQUEST_VALIDATION_ERROR_MESSAGE = "Leave request validation failed"


class ApiErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None
    correlation_id: str | None = None


class ApiErrorResponse(BaseModel):
    error: ApiErrorBody


EMPLOYEE_VALIDATION_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ApiErrorResponse,
        "description": "Employee endpoint validation error envelope.",
        "content": {
            "application/json": {
                "example": {
                    "error": {
                        "code": EMPLOYEE_VALIDATION_ERROR_CODE,
                        "message": EMPLOYEE_VALIDATION_ERROR_MESSAGE,
                        "details": None,
                        "correlation_id": "req_wf_demo_001",
                    }
                }
            }
        },
    }
}
LEAVE_BALANCE_VALIDATION_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ApiErrorResponse,
        "description": "Leave balance endpoint validation error envelope.",
        "content": {
            "application/json": {
                "example": {
                    "error": {
                        "code": LEAVE_BALANCE_VALIDATION_ERROR_CODE,
                        "message": LEAVE_BALANCE_VALIDATION_ERROR_MESSAGE,
                        "details": None,
                        "correlation_id": "req_wf_demo_001",
                    }
                }
            }
        },
    }
}
LEAVE_REQUEST_VALIDATION_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ApiErrorResponse,
        "description": "Leave request endpoint validation error envelope.",
        "content": {
            "application/json": {
                "example": {
                    "error": {
                        "code": LEAVE_REQUEST_VALIDATION_ERROR_CODE,
                        "message": LEAVE_REQUEST_VALIDATION_ERROR_MESSAGE,
                        "details": None,
                        "correlation_id": "req_wf_demo_001",
                    }
                }
            }
        },
    }
}


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
    api_error = _domain_request_validation_error(request, exc)
    if api_error is not None:
        return await api_error_handler(request, api_error)
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


def _domain_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> ApiError | None:
    path = request.url.path
    if _is_leave_balance_api_path(path):
        return _leave_balance_request_validation_error()
    if _matches_api_prefix(path, EMPLOYEE_API_PREFIX):
        return _employee_request_validation_error(exc)
    if _matches_api_prefix(path, LEAVE_REQUEST_API_PREFIX):
        return _leave_request_validation_error(exc)
    return None


def _matches_api_prefix(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(f"{prefix}/")


def _is_leave_balance_api_path(path: str) -> bool:
    return _matches_api_prefix(path, EMPLOYEE_API_PREFIX) and LEAVE_BALANCE_API_SEGMENT in path


def _employee_request_validation_error(exc: RequestValidationError) -> ApiError:
    messages = _validation_messages(exc)
    if "Employment end date must be on or after start date" in messages:
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="employee_invalid_date_range",
            message="Employment end date must be on or after start date",
        )
    for lifecycle_message in (
        "Terminated employees must have an employment end date",
        "Employment end date is only allowed when status is terminated",
        "Status must not be null",
    ):
        if lifecycle_message in messages:
            return ApiError(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="employee_invalid_lifecycle",
                message=lifecycle_message,
            )
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=EMPLOYEE_VALIDATION_ERROR_CODE,
        message=EMPLOYEE_VALIDATION_ERROR_MESSAGE,
    )


def _leave_balance_request_validation_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=LEAVE_BALANCE_VALIDATION_ERROR_CODE,
        message=LEAVE_BALANCE_VALIDATION_ERROR_MESSAGE,
    )


def _leave_request_validation_error(exc: RequestValidationError) -> ApiError:
    messages = _validation_messages(exc)
    for date_range_message in (
        "Leave end date must be on or after start date",
        "Leave request end_date filter must be on or after start_date",
    ):
        if date_range_message in messages:
            return ApiError(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="leave_request_invalid_date_range",
                message=date_range_message,
            )
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=LEAVE_REQUEST_VALIDATION_ERROR_CODE,
        message=LEAVE_REQUEST_VALIDATION_ERROR_MESSAGE,
    )


def _validation_messages(exc: RequestValidationError) -> set[str]:
    return {_clean_validation_message(error.get("msg")) for error in exc.errors()}


def _clean_validation_message(message: Any) -> str:
    clean_message = str(message or "Request validation failed")
    value_error_prefix = "Value error, "
    if clean_message.startswith(value_error_prefix):
        return clean_message.removeprefix(value_error_prefix)
    return clean_message
