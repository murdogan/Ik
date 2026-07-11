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
    IDEMPOTENCY_KEY_INVALID_MESSAGE,
    IDEMPOTENCY_KEY_MISMATCH_MESSAGE,
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
from app.platform.idempotency import (
    IdempotencyKeyMismatchError,
    IdempotencyReplayUnavailableError,
)
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
from app.services.tenant_service import (
    DuplicateTenantSlugError,
    TenantClosedError,
    TenantLifecycleConflictError,
    TenantNotFoundError,
    TenantNotReadyError,
    TenantReadOnlyError,
)

TENANT_ID_HEADER = "X-Tenant-Id"
TENANT_SLUG_HEADER = "X-Tenant-Slug"
IDEMPOTENCY_KEY_HEADER = "X-Idempotency-Key"
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
PLATFORM_TENANT_API_PREFIX = "/api/v1/platform/tenants"
TENANT_API_PREFIX = "/api/v1/tenant"

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
IDEMPOTENCY_KEY_INVALID_ERROR_CODE = "idempotency_key_invalid"
IDEMPOTENCY_KEY_MISMATCH_ERROR_CODE = "idempotency_key_mismatch"
APPLICATION_COMMAND_FAILED_ERROR_CODE = "application_command_failed"
PLATFORM_ACCESS_DENIED_ERROR_CODE = "platform_access_denied"
PLATFORM_ACCESS_DENIED_ERROR_MESSAGE = "Platform tenant access requires a trusted principal"
TENANT_ACCESS_DENIED_ERROR_CODE = "tenant_access_denied"
TENANT_ACCESS_DENIED_ERROR_MESSAGE = "Tenant access requires a trusted principal"
PLATFORM_TENANT_VALIDATION_ERROR_CODE = "platform_tenant_validation_error"
PLATFORM_TENANT_VALIDATION_ERROR_MESSAGE = "Platform tenant request validation failed"
TENANT_SETTINGS_VALIDATION_ERROR_CODE = "tenant_settings_validation_error"
TENANT_SETTINGS_VALIDATION_ERROR_MESSAGE = "Tenant settings request validation failed"
TENANT_NOT_FOUND_ERROR_CODE = "tenant_not_found"
TENANT_NOT_FOUND_ERROR_MESSAGE = "Tenant was not found"
TENANT_SLUG_CONFLICT_ERROR_CODE = "tenant_slug_conflict"
TENANT_SLUG_CONFLICT_ERROR_MESSAGE = "Tenant slug is already in use"
TENANT_LIFECYCLE_CONFLICT_ERROR_CODE = "tenant_lifecycle_conflict"
TENANT_NOT_READY_ERROR_CODE = "tenant_not_ready"
TENANT_NOT_READY_ERROR_MESSAGE = "Tenant provisioning is not complete"
TENANT_CLOSED_ERROR_CODE = "tenant_closed"
TENANT_CLOSED_ERROR_MESSAGE = "Tenant is closed"
TENANT_READ_ONLY_ERROR_CODE = "tenant_read_only"
TENANT_READ_ONLY_ERROR_MESSAGE = "Tenant settings are read-only in the current lifecycle status"


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
IDEMPOTENCY_KEY_INVALID_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {
        "model": ApiErrorResponse,
        "description": "Idempotency key validation error envelope.",
        "content": {
            "application/json": {
                "examples": {
                    IDEMPOTENCY_KEY_INVALID_ERROR_CODE: {
                        "value": {
                            "error": {
                                "code": IDEMPOTENCY_KEY_INVALID_ERROR_CODE,
                                "message": IDEMPOTENCY_KEY_INVALID_MESSAGE,
                                "details": None,
                                "correlation_id": "req_wf_demo_001",
                            }
                        }
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


UNEXPECTED_ERROR_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ApiErrorResponse,
        "description": "Unexpected application failure with safe correlation metadata.",
        "content": {
            "application/json": {
                "example": _error_example(
                    APPLICATION_COMMAND_FAILED_ERROR_CODE,
                    APPLICATION_COMMAND_FAILED_MESSAGE,
                )["value"]
            }
        },
    }
}


PLATFORM_AUTHORIZATION_RESPONSES = {
    status.HTTP_403_FORBIDDEN: {
        "model": ApiErrorResponse,
        "description": "Platform principal authorization denial envelope.",
        "content": {
            "application/json": {
                "example": _error_example(
                    PLATFORM_ACCESS_DENIED_ERROR_CODE,
                    PLATFORM_ACCESS_DENIED_ERROR_MESSAGE,
                )["value"]
            }
        },
    }
}
TENANT_AUTHORIZATION_RESPONSES = {
    status.HTTP_403_FORBIDDEN: {
        "model": ApiErrorResponse,
        "description": "Tenant principal authorization denial envelope.",
        "content": {
            "application/json": {
                "example": _error_example(
                    TENANT_ACCESS_DENIED_ERROR_CODE,
                    TENANT_ACCESS_DENIED_ERROR_MESSAGE,
                )["value"]
            }
        },
    }
}
PLATFORM_TENANT_VALIDATION_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ApiErrorResponse,
        "description": "Platform tenant request validation error envelope.",
    }
}
TENANT_SETTINGS_VALIDATION_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ApiErrorResponse,
        "description": "Tenant settings request validation error envelope.",
    }
}
TENANT_NOT_FOUND_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {
        "model": ApiErrorResponse,
        "description": "Tenant not-found error envelope.",
        "content": {
            "application/json": {
                "example": _error_example(
                    TENANT_NOT_FOUND_ERROR_CODE,
                    TENANT_NOT_FOUND_ERROR_MESSAGE,
                )["value"]
            }
        },
    }
}
TENANT_CLOSED_RESPONSES = {
    status.HTTP_410_GONE: {
        "model": ApiErrorResponse,
        "description": "Closed tenant error envelope.",
        "content": {
            "application/json": {
                "example": _error_example(
                    TENANT_CLOSED_ERROR_CODE,
                    TENANT_CLOSED_ERROR_MESSAGE,
                )["value"]
            }
        },
    }
}
TENANT_NOT_READY_RESPONSES = {
    status.HTTP_423_LOCKED: {
        "model": ApiErrorResponse,
        "description": "Tenant lifecycle access lock envelope.",
        "content": {
            "application/json": {
                "examples": {
                    TENANT_NOT_READY_ERROR_CODE: _error_example(
                        TENANT_NOT_READY_ERROR_CODE,
                        TENANT_NOT_READY_ERROR_MESSAGE,
                    )
                }
            }
        },
    }
}
TENANT_SETTINGS_WRITE_LOCKED_RESPONSES = {
    status.HTTP_423_LOCKED: {
        "model": ApiErrorResponse,
        "description": "Tenant settings lifecycle lock envelope.",
        "content": {
            "application/json": {
                "examples": {
                    TENANT_NOT_READY_ERROR_CODE: _error_example(
                        TENANT_NOT_READY_ERROR_CODE,
                        TENANT_NOT_READY_ERROR_MESSAGE,
                    ),
                    TENANT_READ_ONLY_ERROR_CODE: _error_example(
                        TENANT_READ_ONLY_ERROR_CODE,
                        TENANT_READ_ONLY_ERROR_MESSAGE,
                    ),
                }
            }
        },
    }
}
TENANT_CREATE_CONFLICT_RESPONSES = _conflict_response(
    description="Tenant provisioning conflict envelope.",
    examples={
        TENANT_SLUG_CONFLICT_ERROR_CODE: _error_example(
            TENANT_SLUG_CONFLICT_ERROR_CODE,
            TENANT_SLUG_CONFLICT_ERROR_MESSAGE,
        )
    },
)
TENANT_UPDATE_CONFLICT_RESPONSES = _conflict_response(
    description="Tenant lifecycle update conflict envelope.",
    examples={
        TENANT_LIFECYCLE_CONFLICT_ERROR_CODE: _error_example(
            TENANT_LIFECYCLE_CONFLICT_ERROR_CODE,
            "Tenant lifecycle transition is not allowed",
        )
    },
)


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
IDEMPOTENT_EMPLOYEE_COMMAND_CONFLICT_RESPONSES = _conflict_response(
    description="Idempotent employee command conflict envelope.",
    examples={
        **EMPLOYEE_COMMAND_CONFLICT_RESPONSES[status.HTTP_409_CONFLICT]["content"]
        ["application/json"]["examples"],
        IDEMPOTENCY_KEY_MISMATCH_ERROR_CODE: _error_example(
            IDEMPOTENCY_KEY_MISMATCH_ERROR_CODE,
            IDEMPOTENCY_KEY_MISMATCH_MESSAGE,
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
        IDEMPOTENCY_KEY_MISMATCH_ERROR_CODE: _error_example(
            IDEMPOTENCY_KEY_MISMATCH_ERROR_CODE,
            IDEMPOTENCY_KEY_MISMATCH_MESSAGE,
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
        IDEMPOTENCY_KEY_MISMATCH_ERROR_CODE: _error_example(
            IDEMPOTENCY_KEY_MISMATCH_ERROR_CODE,
            IDEMPOTENCY_KEY_MISMATCH_MESSAGE,
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


async def unexpected_error_handler(request: Request, _exc: Exception) -> Response:
    """Return a metadata-safe envelope without exposing unexpected exception details."""

    return await api_error_handler(request, application_command_failed_error())


def application_error_to_api_error(exc: ApplicationError) -> ApiError:
    if isinstance(exc, TenantNotFoundError):
        return tenant_not_found_error()
    if isinstance(exc, DuplicateTenantSlugError):
        return tenant_slug_conflict_error()
    if isinstance(exc, TenantLifecycleConflictError):
        return tenant_lifecycle_conflict_error(str(exc))
    if isinstance(exc, TenantNotReadyError):
        return tenant_not_ready_error()
    if isinstance(exc, TenantClosedError):
        return tenant_closed_error()
    if isinstance(exc, TenantReadOnlyError):
        return tenant_read_only_error()
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
    if isinstance(exc, IdempotencyKeyMismatchError):
        return idempotency_key_mismatch_error()
    if isinstance(exc, IdempotencyReplayUnavailableError):
        return concurrent_write_conflict_error()
    if isinstance(exc, PersistenceConcurrencyError):
        return concurrent_write_conflict_error()
    if isinstance(exc, PersistenceIntegrityError):
        if exc.constraint_name == EMPLOYEE_NUMBER_UNIQUE_CONSTRAINT:
            return employee_number_conflict_error()
        return data_integrity_conflict_error()
    return application_command_failed_error()


def application_command_failed_error() -> ApiError:
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


def idempotency_key_invalid_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code=IDEMPOTENCY_KEY_INVALID_ERROR_CODE,
        message=IDEMPOTENCY_KEY_INVALID_MESSAGE,
    )


def platform_access_denied_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        code=PLATFORM_ACCESS_DENIED_ERROR_CODE,
        message=PLATFORM_ACCESS_DENIED_ERROR_MESSAGE,
    )


def tenant_access_denied_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        code=TENANT_ACCESS_DENIED_ERROR_CODE,
        message=TENANT_ACCESS_DENIED_ERROR_MESSAGE,
    )


def tenant_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=TENANT_NOT_FOUND_ERROR_CODE,
        message=TENANT_NOT_FOUND_ERROR_MESSAGE,
    )


def tenant_slug_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=TENANT_SLUG_CONFLICT_ERROR_CODE,
        message=TENANT_SLUG_CONFLICT_ERROR_MESSAGE,
    )


def tenant_lifecycle_conflict_error(message: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=TENANT_LIFECYCLE_CONFLICT_ERROR_CODE,
        message=message or "Tenant lifecycle transition is not allowed",
    )


def tenant_not_ready_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_423_LOCKED,
        code=TENANT_NOT_READY_ERROR_CODE,
        message=TENANT_NOT_READY_ERROR_MESSAGE,
    )


def tenant_closed_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_410_GONE,
        code=TENANT_CLOSED_ERROR_CODE,
        message=TENANT_CLOSED_ERROR_MESSAGE,
    )


def tenant_read_only_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_423_LOCKED,
        code=TENANT_READ_ONLY_ERROR_CODE,
        message=TENANT_READ_ONLY_ERROR_MESSAGE,
    )


def platform_tenant_pagination_validation_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=PLATFORM_TENANT_VALIDATION_ERROR_CODE,
        message=PLATFORM_TENANT_VALIDATION_ERROR_MESSAGE,
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


def employee_pagination_validation_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=EMPLOYEE_VALIDATION_ERROR_CODE,
        message=EMPLOYEE_VALIDATION_ERROR_MESSAGE,
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


def leave_request_pagination_validation_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=LEAVE_REQUEST_VALIDATION_ERROR_CODE,
        message=LEAVE_REQUEST_VALIDATION_ERROR_MESSAGE,
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


def idempotency_key_mismatch_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=IDEMPOTENCY_KEY_MISMATCH_ERROR_CODE,
        message=IDEMPOTENCY_KEY_MISMATCH_MESSAGE,
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
    if _matches_api_prefix(path, PLATFORM_TENANT_API_PREFIX):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=PLATFORM_TENANT_VALIDATION_ERROR_CODE,
            message=PLATFORM_TENANT_VALIDATION_ERROR_MESSAGE,
        )
    if _matches_api_prefix(path, TENANT_API_PREFIX):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=TENANT_SETTINGS_VALIDATION_ERROR_CODE,
            message=TENANT_SETTINGS_VALIDATION_ERROR_MESSAGE,
        )
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
