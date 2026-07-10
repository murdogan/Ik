from typing import Any

from fastapi import Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response

from app.core.error_messages import (
    APPLICATION_COMMAND_FAILED_MESSAGE,
    CONCURRENT_WRITE_CONFLICT_MESSAGE,
    DATA_INTEGRITY_CONFLICT_MESSAGE,
    EMPLOYEE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE,
    EMPLOYEE_END_DATE_ONLY_FOR_TERMINATED_MESSAGE,
    EMPLOYEE_NOT_FOUND_MESSAGE,
    EMPLOYEE_NUMBER_CONFLICT_MESSAGE,
    EMPLOYEE_REQUEST_VALIDATION_FAILED_MESSAGE,
    EMPLOYEE_STATUS_MUST_NOT_BE_NULL_MESSAGE,
    EMPLOYEE_TERMINATED_REQUIRES_END_DATE_MESSAGE,
    LEAVE_BALANCE_REQUEST_VALIDATION_FAILED_MESSAGE,
    LEAVE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE,
    LEAVE_REQUEST_FILTER_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE,
    LEAVE_REQUEST_NOT_FOUND_MESSAGE,
    LEAVE_REQUEST_ONLY_PENDING_CAN_BE_DECIDED_MESSAGE,
    LEAVE_REQUEST_VALIDATION_FAILED_MESSAGE,
    USER_NOT_FOUND_MESSAGE,
)
from app.platform.db import PersistenceConcurrencyError, PersistenceIntegrityError
from app.platform.errors import ApiError, ApiErrorResponse, api_error_handler
from app.platform.errors import ApiErrorBody as ApiErrorBody
from app.platform.errors.application import ApplicationError
from app.services.employee_service import (
    EMPLOYEE_NUMBER_UNIQUE_CONSTRAINT,
    DuplicateEmployeeNumberError,
    EmployeeDateRangeError,
    EmployeeLifecycleError,
    EmployeeNotFoundError,
)
from app.services.leave_request_service import (
    LeaveRequestDateRangeError,
    LeaveRequestEmployeeNotFoundError,
    LeaveRequestNotFoundError,
    LeaveRequestTransitionError,
    LeaveRequestUserNotFoundError,
)

TENANT_ID_HEADER = "X-Tenant-Id"
TENANT_SLUG_HEADER = "X-Tenant-Slug"
TENANT_ID_HEADER_MISSING_MESSAGE = f"{TENANT_ID_HEADER} header is required"
TENANT_ID_HEADER_INVALID_MESSAGE = (
    f"{TENANT_ID_HEADER} header must be a single canonical hyphenated UUID"
)
TENANT_SLUG_HEADER_INVALID_MESSAGE = (
    f"{TENANT_SLUG_HEADER} header must be sent at most once and be non-empty when provided"
)
EMPLOYEE_API_PREFIX = "/api/v1/employees"
LEAVE_BALANCE_API_SEGMENT = "/leave-balances"
LEAVE_REQUEST_API_PREFIX = "/api/v1/leave-requests"

EMPLOYEE_VALIDATION_ERROR_CODE = "employee_validation_error"
EMPLOYEE_VALIDATION_ERROR_MESSAGE = EMPLOYEE_REQUEST_VALIDATION_FAILED_MESSAGE
LEAVE_BALANCE_VALIDATION_ERROR_CODE = "leave_balance_validation_error"
LEAVE_BALANCE_VALIDATION_ERROR_MESSAGE = LEAVE_BALANCE_REQUEST_VALIDATION_FAILED_MESSAGE
LEAVE_REQUEST_VALIDATION_ERROR_CODE = "leave_request_validation_error"
LEAVE_REQUEST_VALIDATION_ERROR_MESSAGE = LEAVE_REQUEST_VALIDATION_FAILED_MESSAGE
EMPLOYEE_NOT_FOUND_ERROR_CODE = "employee_not_found"
EMPLOYEE_NOT_FOUND_ERROR_MESSAGE = EMPLOYEE_NOT_FOUND_MESSAGE
EMPLOYEE_NUMBER_CONFLICT_ERROR_CODE = "employee_number_conflict"
EMPLOYEE_NUMBER_CONFLICT_ERROR_MESSAGE = EMPLOYEE_NUMBER_CONFLICT_MESSAGE
EMPLOYEE_INVALID_DATE_RANGE_ERROR_CODE = "employee_invalid_date_range"
EMPLOYEE_INVALID_LIFECYCLE_ERROR_CODE = "employee_invalid_lifecycle"
LEAVE_REQUEST_NOT_FOUND_ERROR_CODE = "leave_request_not_found"
LEAVE_REQUEST_NOT_FOUND_ERROR_MESSAGE = LEAVE_REQUEST_NOT_FOUND_MESSAGE
LEAVE_REQUEST_INVALID_DATE_RANGE_ERROR_CODE = "leave_request_invalid_date_range"
LEAVE_REQUEST_TRANSITION_CONFLICT_ERROR_CODE = "leave_request_transition_conflict"
USER_NOT_FOUND_ERROR_CODE = "user_not_found"
USER_NOT_FOUND_ERROR_MESSAGE = USER_NOT_FOUND_MESSAGE
DATA_INTEGRITY_CONFLICT_ERROR_CODE = "data_integrity_conflict"
CONCURRENT_WRITE_CONFLICT_ERROR_CODE = "concurrent_write_conflict"
APPLICATION_COMMAND_FAILED_ERROR_CODE = "application_command_failed"


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


def _conflict_response(*, description: str, examples: dict[str, dict[str, Any]]) -> dict:
    return {
        status.HTTP_409_CONFLICT: {
            "model": ApiErrorResponse,
            "description": description,
            "content": {"application/json": {"examples": examples}},
        }
    }


def _error_example(code: str, message: str) -> dict[str, Any]:
    return {
        "value": {
            "error": {
                "code": code,
                "message": message,
                "details": None,
                "correlation_id": "req_wf_demo_001",
            }
        }
    }


EMPLOYEE_COMMAND_CONFLICT_RESPONSES = _conflict_response(
    description="Employee command conflict envelope.",
    examples={
        EMPLOYEE_NUMBER_CONFLICT_ERROR_CODE: _error_example(
            EMPLOYEE_NUMBER_CONFLICT_ERROR_CODE,
            EMPLOYEE_NUMBER_CONFLICT_ERROR_MESSAGE,
        ),
        DATA_INTEGRITY_CONFLICT_ERROR_CODE: _error_example(
            DATA_INTEGRITY_CONFLICT_ERROR_CODE,
            DATA_INTEGRITY_CONFLICT_MESSAGE,
        ),
        CONCURRENT_WRITE_CONFLICT_ERROR_CODE: _error_example(
            CONCURRENT_WRITE_CONFLICT_ERROR_CODE,
            CONCURRENT_WRITE_CONFLICT_MESSAGE,
        ),
    },
)
LEAVE_REQUEST_PERSISTENCE_CONFLICT_RESPONSES = _conflict_response(
    description="Leave request command persistence conflict envelope.",
    examples={
        DATA_INTEGRITY_CONFLICT_ERROR_CODE: _error_example(
            DATA_INTEGRITY_CONFLICT_ERROR_CODE,
            DATA_INTEGRITY_CONFLICT_MESSAGE,
        ),
        CONCURRENT_WRITE_CONFLICT_ERROR_CODE: _error_example(
            CONCURRENT_WRITE_CONFLICT_ERROR_CODE,
            CONCURRENT_WRITE_CONFLICT_MESSAGE,
        ),
    },
)
LEAVE_REQUEST_DECISION_CONFLICT_RESPONSES = _conflict_response(
    description="Leave request command conflict envelope.",
    examples={
        LEAVE_REQUEST_TRANSITION_CONFLICT_ERROR_CODE: _error_example(
            LEAVE_REQUEST_TRANSITION_CONFLICT_ERROR_CODE,
            LEAVE_REQUEST_ONLY_PENDING_CAN_BE_DECIDED_MESSAGE,
        ),
        DATA_INTEGRITY_CONFLICT_ERROR_CODE: _error_example(
            DATA_INTEGRITY_CONFLICT_ERROR_CODE,
            DATA_INTEGRITY_CONFLICT_MESSAGE,
        ),
        CONCURRENT_WRITE_CONFLICT_ERROR_CODE: _error_example(
            CONCURRENT_WRITE_CONFLICT_ERROR_CODE,
            CONCURRENT_WRITE_CONFLICT_MESSAGE,
        ),
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


async def application_error_handler(request: Request, exc: ApplicationError) -> Response:
    return await api_error_handler(request, application_error_to_api_error(exc))


def application_error_to_api_error(exc: ApplicationError) -> ApiError:
    if isinstance(exc, (EmployeeNotFoundError, LeaveRequestEmployeeNotFoundError)):
        return employee_not_found_error()
    if isinstance(exc, DuplicateEmployeeNumberError):
        return employee_number_conflict_error()
    if isinstance(exc, EmployeeDateRangeError):
        return employee_date_range_error(str(exc))
    if isinstance(exc, EmployeeLifecycleError):
        return employee_lifecycle_error(str(exc))
    if isinstance(exc, LeaveRequestNotFoundError):
        return leave_request_not_found_error()
    if isinstance(exc, LeaveRequestUserNotFoundError):
        return user_not_found_error()
    if isinstance(exc, LeaveRequestDateRangeError):
        return leave_request_date_range_error(str(exc))
    if isinstance(exc, LeaveRequestTransitionError):
        return leave_request_transition_conflict_error(str(exc))
    if isinstance(exc, PersistenceConcurrencyError):
        return concurrent_write_conflict_error()
    if isinstance(exc, PersistenceIntegrityError):
        if exc.constraint_name == EMPLOYEE_NUMBER_UNIQUE_CONSTRAINT:
            return employee_number_conflict_error()
        return data_integrity_conflict_error()
    return ApiError(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code=APPLICATION_COMMAND_FAILED_ERROR_CODE,
        message=APPLICATION_COMMAND_FAILED_MESSAGE,
    )


def tenant_header_missing_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="tenant_header_missing",
        message=TENANT_ID_HEADER_MISSING_MESSAGE,
    )


def tenant_header_invalid_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="tenant_header_invalid",
        message=TENANT_ID_HEADER_INVALID_MESSAGE,
    )


def tenant_slug_header_invalid_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="tenant_slug_header_invalid",
        message=TENANT_SLUG_HEADER_INVALID_MESSAGE,
    )


def employee_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=EMPLOYEE_NOT_FOUND_ERROR_CODE,
        message=EMPLOYEE_NOT_FOUND_ERROR_MESSAGE,
    )


def employee_number_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=EMPLOYEE_NUMBER_CONFLICT_ERROR_CODE,
        message=EMPLOYEE_NUMBER_CONFLICT_ERROR_MESSAGE,
    )


def employee_date_range_error(message: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=EMPLOYEE_INVALID_DATE_RANGE_ERROR_CODE,
        message=message,
    )


def employee_lifecycle_error(message: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=EMPLOYEE_INVALID_LIFECYCLE_ERROR_CODE,
        message=message,
    )


def leave_request_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=LEAVE_REQUEST_NOT_FOUND_ERROR_CODE,
        message=LEAVE_REQUEST_NOT_FOUND_ERROR_MESSAGE,
    )


def user_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=USER_NOT_FOUND_ERROR_CODE,
        message=USER_NOT_FOUND_ERROR_MESSAGE,
    )


def leave_request_date_range_error(message: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=LEAVE_REQUEST_INVALID_DATE_RANGE_ERROR_CODE,
        message=message,
    )


def leave_request_transition_conflict_error(message: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=LEAVE_REQUEST_TRANSITION_CONFLICT_ERROR_CODE,
        message=message,
    )


def data_integrity_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=DATA_INTEGRITY_CONFLICT_ERROR_CODE,
        message=DATA_INTEGRITY_CONFLICT_MESSAGE,
    )


def concurrent_write_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=CONCURRENT_WRITE_CONFLICT_ERROR_CODE,
        message=CONCURRENT_WRITE_CONFLICT_MESSAGE,
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
    if EMPLOYEE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE in messages:
        return employee_date_range_error(EMPLOYEE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE)
    for lifecycle_message in (
        EMPLOYEE_TERMINATED_REQUIRES_END_DATE_MESSAGE,
        EMPLOYEE_END_DATE_ONLY_FOR_TERMINATED_MESSAGE,
        EMPLOYEE_STATUS_MUST_NOT_BE_NULL_MESSAGE,
    ):
        if lifecycle_message in messages:
            return employee_lifecycle_error(lifecycle_message)
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
        LEAVE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE,
        LEAVE_REQUEST_FILTER_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE,
    ):
        if date_range_message in messages:
            return leave_request_date_range_error(date_range_message)
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
