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
    EMPLOYEE_WORK_EMAIL_CONFLICT_MESSAGE,
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
from app.services.audit_query_service import AuditAccessDeniedError, AuditEventNotFoundError
from app.services.auth_session_service import InvalidSessionError
from app.services.authentication_rate_limit_service import (
    AuthenticationRateLimitExceededError,
)
from app.services.authentication_service import (
    InvalidActivationError,
    InvalidCredentialsError,
    InvalidOrganizationSelectionError,
    OrganizationSwitchUnavailableError,
)
from app.services.authorization_service import (
    AuthorizationAccessDeniedError,
    RoleAssignmentConflictError,
    RoleAssignmentInvalidError,
    RoleAssignmentUserNotFoundError,
)
from app.services.department_service import (
    DepartmentConflictError,
    DepartmentCycleError,
    DepartmentNotFoundError,
    DuplicateDepartmentCodeError,
)
from app.services.employee_account_link_service import EmployeeAccountLinkUnavailableError
from app.services.employee_assignment_service import (
    EmployeeAssignmentAccessDeniedError,
    EmployeeAssignmentConflictError,
    EmployeeAssignmentNotFoundError,
)
from app.services.employee_document_service import (
    DocumentConflictError,
    DocumentNotFoundError,
    DocumentStorageUnavailableError,
    DocumentTypeNotFoundError,
    DocumentValidationError,
    DocumentVersionConflictError,
)
from app.services.employee_profile_change_request_service import (
    EmployeeProfileChangeRequestConflictError,
    EmployeeProfileChangeRequestInvalidError,
    EmployeeProfileChangeRequestNotFoundError,
    EmployeeProfileChangeRequestStaleProfileError,
)
from app.services.employee_service import (
    EMPLOYEE_NUMBER_NORMALIZED_UNIQUE_CONSTRAINT,
    EMPLOYEE_NUMBER_UNIQUE_CONSTRAINT,
    EMPLOYEE_WORK_EMAIL_NORMALIZED_UNIQUE_CONSTRAINT,
    DuplicateEmployeeNumberError,
    DuplicateWorkEmailError,
    EmployeeDateRangeError,
    EmployeeLifecycleConflictError,
    EmployeeLifecycleError,
    EmployeeNotFoundError,
    EmployeeOpenProcessConflictError,
    EmployeeVersionConflictError,
)
from app.services.leave_request_service import (
    LeaveRequestDateRangeError,
    LeaveRequestEmployeeNotFoundError,
    LeaveRequestNotFoundError,
    LeaveRequestTransitionError,
    LeaveRequestUserNotFoundError,
)
from app.services.leave_service import (
    LeaveAccessDeniedError,
    LeaveConflictError,
    LeaveEmployeeLinkUnavailableError,
    LeaveInsufficientBalanceError,
    LeaveNotFoundError,
    LeaveValidationError,
    LeaveVersionConflictError,
)
from app.services.organization_service import (
    BranchNotFoundError,
    DuplicateBranchCodeError,
    DuplicateLegalEntityCodeError,
    LegalEntityNotFoundError,
    OrganizationAccessDeniedError,
    OrganizationConflictError,
    OrganizationFeatureUnavailableError,
)
from app.services.password_recovery_service import InvalidPasswordResetError
from app.services.phase7_access import (
    Phase7AccessDeniedError,
    Phase7ConflictError,
    Phase7FeatureUnavailableError,
    Phase7NotFoundError,
    Phase7ValidationError,
    Phase7VersionConflictError,
)
from app.services.platform_auth_session_service import (
    InvalidPlatformSessionError,
    PlatformRoleRequiredError,
)
from app.services.platform_authentication_service import InvalidPlatformCredentialsError
from app.services.position_service import (
    DuplicatePositionCodeError,
    PositionConflictError,
    PositionNotFoundError,
)
from app.services.reporting_access import (
    ReportingAccessDeniedError,
    ReportingConflictError,
    ReportingFeatureUnavailableError,
    ReportingNotFoundError,
    ReportingStorageUnavailableError,
    ReportingValidationError,
)
from app.services.tenant_service import (
    DuplicateTenantSlugError,
    TenantClosedError,
    TenantLifecycleConflictError,
    TenantNotFoundError,
    TenantNotReadyError,
    TenantReadOnlyError,
)
from app.services.user_administration_service import (
    UserAdministrationAccessDeniedError,
    UserAdministrationStatusConflictError,
    UserAdministrationUserNotFoundError,
)
from app.services.user_invitation_service import (
    InvitationAccessDeniedError,
    InvitationConflictError,
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
OWN_PROFILE_CHANGE_REQUEST_API_PREFIX = "/api/v1/me/profile-change-requests"
HR_PROFILE_CHANGE_REQUEST_API_PREFIX = "/api/v1/employee-profile-change-requests"
LEAVE_BALANCE_API_SEGMENT = "/leave-balances"
LEAVE_REQUEST_API_PREFIX = "/api/v1/leave-requests"
LEAVE_TYPE_API_PREFIX = "/api/v1/leave-types"
HOLIDAY_CALENDAR_API_PREFIX = "/api/v1/holiday-calendars"
LEAVE_POLICY_API_PREFIX = "/api/v1/leave-policies"
LEAVE_ADJUSTMENT_API_PREFIX = "/api/v1/leave-adjustments"
OWN_LEAVE_BALANCE_API_PREFIX = "/api/v1/me/leave-balances"
APPROVAL_TASK_API_PREFIX = "/api/v1/approval-tasks"
TEAM_CALENDAR_API_PREFIX = "/api/v1/team-calendar"
PLATFORM_TENANT_API_PREFIX = "/api/v1/platform/tenants"
TENANT_API_PREFIX = "/api/v1/tenant"
AUTH_API_PREFIX = "/api/v1/auth"
PLATFORM_AUTH_API_PREFIX = "/api/v1/platform/auth"
USER_INVITATION_API_PREFIX = "/api/v1/users/invitations"
USER_ADMINISTRATION_API_PREFIX = "/api/v1/users"
LEGAL_ENTITY_API_PREFIX = "/api/v1/legal-entities"
BRANCH_API_PREFIX = "/api/v1/branches"
DEPARTMENT_API_PREFIX = "/api/v1/departments"
POSITION_API_PREFIX = "/api/v1/positions"
EMPLOYEE_ASSIGNMENT_API_PREFIX = "/api/v1/employee-assignments"
MANAGER_TEAM_API_PREFIX = "/api/v1/teams/me"
ORG_CHART_API_PREFIX = "/api/v1/org-chart"
DOCUMENT_TYPE_API_PREFIX = "/api/v1/document-types"
OWN_DOCUMENT_API_PREFIX = "/api/v1/me/documents"
PHASE7_API_PREFIXES = (
    "/api/v1/requests",
    "/api/v1/document-requests",
    "/api/v1/self-service",
    "/api/v1/announcements",
    "/api/v1/notifications",
    "/api/v1/privacy",
)
REPORT_API_PREFIX = "/api/v1/reports"
EXPORT_JOB_API_PREFIX = "/api/v1/export-jobs"
EMPLOYEE_IMPORT_API_PREFIX = "/api/v1/employees/imports"

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
EMPLOYEE_WORK_EMAIL_CONFLICT_ERROR_CODE = "employee_work_email_conflict"
EMPLOYEE_WORK_EMAIL_CONFLICT_ERROR_MESSAGE = EMPLOYEE_WORK_EMAIL_CONFLICT_MESSAGE
EMPLOYEE_ACCOUNT_LINK_CONFLICT_ERROR_CODE = "employee_account_link_conflict"
EMPLOYEE_ACCOUNT_LINK_CONFLICT_ERROR_MESSAGE = "The requested account link is unavailable"
EMPLOYEE_PROFILE_CHANGE_REQUEST_VALIDATION_ERROR_CODE = (
    "employee_profile_change_request_validation_error"
)
EMPLOYEE_PROFILE_CHANGE_REQUEST_VALIDATION_ERROR_MESSAGE = (
    "Employee profile change request validation failed"
)
EMPLOYEE_PROFILE_CHANGE_REQUEST_NOT_FOUND_ERROR_CODE = "employee_profile_change_request_not_found"
EMPLOYEE_PROFILE_CHANGE_REQUEST_NOT_FOUND_ERROR_MESSAGE = (
    "Employee profile change request was not found"
)
EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_ERROR_CODE = "employee_profile_change_request_conflict"
EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_ERROR_MESSAGE = (
    "The employee profile change request cannot be changed"
)
EMPLOYEE_PROFILE_CHANGE_REQUEST_STALE_PROFILE_ERROR_CODE = (
    "employee_profile_change_request_stale_profile"
)
EMPLOYEE_PROFILE_CHANGE_REQUEST_STALE_PROFILE_ERROR_MESSAGE = (
    "The employee profile changed after this request was submitted; reload before deciding"
)
EMPLOYEE_INVALID_DATE_RANGE_ERROR_CODE = "employee_invalid_date_range"
EMPLOYEE_INVALID_LIFECYCLE_ERROR_CODE = "employee_invalid_lifecycle"
EMPLOYEE_LIFECYCLE_CONFLICT_ERROR_CODE = "employee_lifecycle_conflict"
EMPLOYEE_LIFECYCLE_CONFLICT_ERROR_MESSAGE = "The requested employee lifecycle action is not allowed"
EMPLOYEE_OPEN_PROCESS_CONFLICT_ERROR_CODE = "employee_open_process_conflict"
EMPLOYEE_OPEN_PROCESS_CONFLICT_ERROR_MESSAGE = (
    "Resolve the submitted employee profile-change request before termination or archive"
)
LEAVE_REQUEST_NOT_FOUND_ERROR_CODE = "leave_request_not_found"
LEAVE_REQUEST_NOT_FOUND_ERROR_MESSAGE = LEAVE_REQUEST_NOT_FOUND_MESSAGE
LEAVE_REQUEST_INVALID_DATE_RANGE_ERROR_CODE = "leave_request_invalid_date_range"
LEAVE_REQUEST_TRANSITION_CONFLICT_ERROR_CODE = "leave_request_transition_conflict"
LEAVE_VALIDATION_ERROR_CODE = "leave_validation_error"
LEAVE_VALIDATION_ERROR_MESSAGE = "Leave request validation failed"
LEAVE_NOT_FOUND_ERROR_CODE = "leave_not_found"
LEAVE_NOT_FOUND_ERROR_MESSAGE = "The leave resource was not found"
LEAVE_CONFLICT_ERROR_CODE = "leave_conflict"
LEAVE_INSUFFICIENT_BALANCE_ERROR_CODE = "leave_balance_insufficient"
USER_NOT_FOUND_ERROR_CODE = "user_not_found"
USER_NOT_FOUND_ERROR_MESSAGE = USER_NOT_FOUND_MESSAGE
DATA_INTEGRITY_CONFLICT_ERROR_CODE = "data_integrity_conflict"
CONCURRENT_WRITE_CONFLICT_ERROR_CODE = "concurrent_write_conflict"
IDEMPOTENCY_KEY_INVALID_ERROR_CODE = "idempotency_key_invalid"
IDEMPOTENCY_KEY_MISMATCH_ERROR_CODE = "idempotency_key_mismatch"
APPLICATION_COMMAND_FAILED_ERROR_CODE = "application_command_failed"
PLATFORM_ACCESS_DENIED_ERROR_CODE = "platform_access_denied"
PLATFORM_ACCESS_DENIED_ERROR_MESSAGE = "A valid platform access credential is required"
PLATFORM_ROLE_REQUIRED_ERROR_CODE = "platform_role_required"
PLATFORM_ROLE_REQUIRED_ERROR_MESSAGE = "Platform access is not available for this account"
PLATFORM_STEP_UP_REQUIRED_ERROR_CODE = "platform_step_up_required"
PLATFORM_STEP_UP_REQUIRED_ERROR_MESSAGE = "A stronger platform authentication method is required"
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
AUTH_VALIDATION_ERROR_CODE = "auth_validation_error"
AUTH_VALIDATION_ERROR_MESSAGE = "Authentication request validation failed"
INVALID_CREDENTIALS_ERROR_CODE = "invalid_credentials"
INVALID_CREDENTIALS_ERROR_MESSAGE = "The email or password is incorrect"
AUTHENTICATION_RATE_LIMIT_ERROR_CODE = "authentication_rate_limited"
AUTHENTICATION_RATE_LIMIT_ERROR_MESSAGE = (
    "Too many login attempts were made; retry after a short wait"
)
INVALID_ACTIVATION_ERROR_CODE = "activation_invalid"
INVALID_ACTIVATION_ERROR_MESSAGE = (
    "This activation link is invalid, expired, or has already been used"
)
INVALID_PASSWORD_RESET_ERROR_CODE = "password_reset_invalid"
INVALID_PASSWORD_RESET_ERROR_MESSAGE = (
    "This password-reset link is invalid, expired, or has already been used"
)
AUTHENTICATION_REQUIRED_ERROR_CODE = "authentication_required"
AUTHENTICATION_REQUIRED_ERROR_MESSAGE = "A valid access credential is required"
SESSION_INVALID_ERROR_CODE = "session_invalid"
SESSION_INVALID_ERROR_MESSAGE = "The session is invalid, expired, or revoked"
ORGANIZATION_SELECTION_INVALID_ERROR_CODE = "organization_selection_invalid"
ORGANIZATION_SELECTION_INVALID_ERROR_MESSAGE = (
    "The organization selection is invalid, expired, or has already been used"
)
ORGANIZATION_SWITCH_UNAVAILABLE_ERROR_CODE = "organization_switch_unavailable"
ORGANIZATION_SWITCH_UNAVAILABLE_ERROR_MESSAGE = (
    "No other active organization is available for this identity"
)
INVITATION_ACCESS_DENIED_ERROR_CODE = "invitation_access_denied"
INVITATION_ACCESS_DENIED_ERROR_MESSAGE = "You do not have permission to invite users"
INVITATION_CONFLICT_ERROR_CODE = "invitation_conflict"
INVITATION_CONFLICT_ERROR_MESSAGE = "This user cannot be invited"
USER_ADMINISTRATION_ACCESS_DENIED_ERROR_CODE = "user_administration_access_denied"
USER_ADMINISTRATION_ACCESS_DENIED_ERROR_MESSAGE = "You do not have permission to administer users"
USER_ADMINISTRATION_VALIDATION_ERROR_CODE = "user_administration_validation_error"
USER_ADMINISTRATION_VALIDATION_ERROR_MESSAGE = "User administration request validation failed"
USER_ADMINISTRATION_STATUS_CONFLICT_ERROR_CODE = "user_status_conflict"
USER_ADMINISTRATION_STATUS_CONFLICT_ERROR_MESSAGE = (
    "The requested user status transition is not allowed"
)
AUTHORIZATION_ACCESS_DENIED_ERROR_CODE = "authorization_denied"
AUTHORIZATION_ACCESS_DENIED_ERROR_MESSAGE = "You do not have the required permission"
ROLE_ASSIGNMENT_INVALID_ERROR_CODE = "role_assignment_invalid"
ROLE_ASSIGNMENT_INVALID_ERROR_MESSAGE = "The requested tenant role set is invalid"
ROLE_ASSIGNMENT_CONFLICT_ERROR_CODE = "role_assignment_conflict"
ROLE_ASSIGNMENT_CONFLICT_ERROR_MESSAGE = "The requested role replacement is not allowed"
AUDIT_EVENT_NOT_FOUND_ERROR_CODE = "audit_event_not_found"
AUDIT_EVENT_NOT_FOUND_ERROR_MESSAGE = "Audit event was not found"
AUDIT_VALIDATION_ERROR_CODE = "audit_validation_error"
AUDIT_VALIDATION_ERROR_MESSAGE = "Audit query validation failed"
ORGANIZATION_ACCESS_DENIED_ERROR_CODE = "organization_access_denied"
ORGANIZATION_ACCESS_DENIED_ERROR_MESSAGE = (
    "You do not have permission to manage organization settings"
)
ORGANIZATION_VALIDATION_ERROR_CODE = "organization_validation_error"
ORGANIZATION_VALIDATION_ERROR_MESSAGE = "Organization request validation failed"
ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_CODE = "organization_feature_unavailable"
ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_MESSAGE = "Organization module is not enabled"
LEGAL_ENTITY_NOT_FOUND_ERROR_CODE = "legal_entity_not_found"
LEGAL_ENTITY_NOT_FOUND_ERROR_MESSAGE = "Legal entity was not found"
BRANCH_NOT_FOUND_ERROR_CODE = "branch_not_found"
BRANCH_NOT_FOUND_ERROR_MESSAGE = "Branch was not found"
LEGAL_ENTITY_CODE_CONFLICT_ERROR_CODE = "legal_entity_code_conflict"
LEGAL_ENTITY_CODE_CONFLICT_ERROR_MESSAGE = "Legal entity code is already in use"
BRANCH_CODE_CONFLICT_ERROR_CODE = "branch_code_conflict"
BRANCH_CODE_CONFLICT_ERROR_MESSAGE = "Branch code is already in use"
DEPARTMENT_NOT_FOUND_ERROR_CODE = "department_not_found"
DEPARTMENT_NOT_FOUND_ERROR_MESSAGE = "Department was not found"
DEPARTMENT_CODE_CONFLICT_ERROR_CODE = "department_code_conflict"
DEPARTMENT_CODE_CONFLICT_ERROR_MESSAGE = "Department code is already in use"
DEPARTMENT_CYCLE_CONFLICT_ERROR_CODE = "department_cycle_conflict"
DEPARTMENT_CYCLE_CONFLICT_ERROR_MESSAGE = (
    "The requested department move would create a hierarchy cycle"
)
POSITION_NOT_FOUND_ERROR_CODE = "position_not_found"
POSITION_NOT_FOUND_ERROR_MESSAGE = "Position was not found"
POSITION_CODE_CONFLICT_ERROR_CODE = "position_code_conflict"
POSITION_CODE_CONFLICT_ERROR_MESSAGE = "Position code is already in use"
ORGANIZATION_CONFLICT_ERROR_CODE = "organization_conflict"
ORGANIZATION_CONFLICT_ERROR_MESSAGE = "The requested organization change is not allowed"
EMPLOYEE_ASSIGNMENT_ACCESS_DENIED_ERROR_CODE = "employee_assignment_access_denied"
EMPLOYEE_ASSIGNMENT_ACCESS_DENIED_ERROR_MESSAGE = (
    "You do not have permission to access employee assignments"
)
EMPLOYEE_ASSIGNMENT_VALIDATION_ERROR_CODE = "employee_assignment_validation_error"
EMPLOYEE_ASSIGNMENT_VALIDATION_ERROR_MESSAGE = "Employee assignment request validation failed"
EMPLOYEE_ASSIGNMENT_NOT_FOUND_ERROR_CODE = "employee_assignment_not_found"
EMPLOYEE_ASSIGNMENT_NOT_FOUND_ERROR_MESSAGE = "Employee assignment was not found"
EMPLOYEE_ASSIGNMENT_CONFLICT_ERROR_CODE = "employee_assignment_conflict"
EMPLOYEE_ASSIGNMENT_CONFLICT_ERROR_MESSAGE = "The requested employee assignment is not allowed"
DOCUMENT_VALIDATION_ERROR_CODE = "document_validation_error"
DOCUMENT_VALIDATION_ERROR_MESSAGE = "Employee document request validation failed"
DOCUMENT_NOT_FOUND_ERROR_CODE = "document_not_found"
DOCUMENT_NOT_FOUND_ERROR_MESSAGE = "Employee document was not found"
DOCUMENT_TYPE_NOT_FOUND_ERROR_CODE = "document_type_not_found"
DOCUMENT_TYPE_NOT_FOUND_ERROR_MESSAGE = "Employee document type was not found"
DOCUMENT_CONFLICT_ERROR_CODE = "document_conflict"
DOCUMENT_CONFLICT_ERROR_MESSAGE = "The employee document operation is not allowed"
DOCUMENT_STORAGE_UNAVAILABLE_ERROR_CODE = "document_storage_unavailable"
DOCUMENT_STORAGE_UNAVAILABLE_ERROR_MESSAGE = "Employee document storage is temporarily unavailable"
REPORTING_VALIDATION_ERROR_CODE = "reporting_validation_error"
REPORTING_VALIDATION_ERROR_MESSAGE = "Report or import request validation failed"
REPORTING_NOT_FOUND_ERROR_CODE = "reporting_resource_not_found"
REPORTING_NOT_FOUND_ERROR_MESSAGE = "The requested report, export, or import was not found"
REPORTING_CONFLICT_ERROR_CODE = "reporting_conflict"
REPORTING_CONFLICT_ERROR_MESSAGE = (
    "The report, export, or import cannot be changed in its current state"
)
REPORTING_FEATURE_UNAVAILABLE_ERROR_CODE = "reporting_feature_unavailable"
REPORTING_FEATURE_UNAVAILABLE_ERROR_MESSAGE = "Reporting is not enabled for this organization"
REPORTING_STORAGE_UNAVAILABLE_ERROR_CODE = "reporting_storage_unavailable"
REPORTING_STORAGE_UNAVAILABLE_ERROR_MESSAGE = "Private report storage is temporarily unavailable"


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


EMPLOYEE_PROFILE_CHANGE_REQUEST_VALIDATION_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ApiErrorResponse,
        "description": "Profile-change request validation error envelope.",
        "content": {
            "application/json": {
                "example": _error_example(
                    EMPLOYEE_PROFILE_CHANGE_REQUEST_VALIDATION_ERROR_CODE,
                    EMPLOYEE_PROFILE_CHANGE_REQUEST_VALIDATION_ERROR_MESSAGE,
                )["value"]
            }
        },
    }
}
EMPLOYEE_PROFILE_CHANGE_REQUEST_NOT_FOUND_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {
        "model": ApiErrorResponse,
        "description": "The request is absent, unrelated, or outside the authenticated tenant.",
        "content": {
            "application/json": {
                "example": _error_example(
                    EMPLOYEE_PROFILE_CHANGE_REQUEST_NOT_FOUND_ERROR_CODE,
                    EMPLOYEE_PROFILE_CHANGE_REQUEST_NOT_FOUND_ERROR_MESSAGE,
                )["value"]
            }
        },
    }
}
EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_RESPONSES = _conflict_response(
    description="Active, optimistic-state, or stale-profile request conflict envelope.",
    examples={
        EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_ERROR_CODE: _error_example(
            EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_ERROR_CODE,
            EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_ERROR_MESSAGE,
        ),
        EMPLOYEE_PROFILE_CHANGE_REQUEST_STALE_PROFILE_ERROR_CODE: _error_example(
            EMPLOYEE_PROFILE_CHANGE_REQUEST_STALE_PROFILE_ERROR_CODE,
            EMPLOYEE_PROFILE_CHANGE_REQUEST_STALE_PROFILE_ERROR_MESSAGE,
        ),
    },
)


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

AUTH_VALIDATION_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ApiErrorResponse,
        "description": "Credential-safe authentication validation error envelope.",
    }
}
AUTHENTICATION_RATE_LIMIT_RESPONSES = {
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "model": ApiErrorResponse,
        "description": "Authentication attempt rate-limit envelope.",
        "headers": {
            "Retry-After": {
                "description": "Seconds until this login bucket can be retried.",
                "schema": {"type": "integer", "minimum": 1},
            }
        },
        "content": {
            "application/json": {
                "example": {
                    "error": {
                        "code": AUTHENTICATION_RATE_LIMIT_ERROR_CODE,
                        "message": AUTHENTICATION_RATE_LIMIT_ERROR_MESSAGE,
                        "details": None,
                        "correlation_id": "req_wf_demo_001",
                    }
                }
            }
        },
    }
}
AUTHENTICATION_REQUIRED_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ApiErrorResponse,
        "description": "Missing, malformed, expired, or invalid access credential.",
    }
}
INVITATION_AUTHORIZATION_RESPONSES = {
    status.HTTP_403_FORBIDDEN: {
        "model": ApiErrorResponse,
        "description": "The authenticated actor cannot invite users.",
    }
}
INVITATION_CONFLICT_RESPONSES = _conflict_response(
    description="The target user is not in an invitable state.",
    examples={
        INVITATION_CONFLICT_ERROR_CODE: _error_example(
            INVITATION_CONFLICT_ERROR_CODE,
            INVITATION_CONFLICT_ERROR_MESSAGE,
        )
    },
)
USER_ADMINISTRATION_AUTHORIZATION_RESPONSES = {
    status.HTTP_403_FORBIDDEN: {
        "model": ApiErrorResponse,
        "description": "The authenticated actor cannot administer tenant users.",
        "content": {
            "application/json": {
                "example": _error_example(
                    USER_ADMINISTRATION_ACCESS_DENIED_ERROR_CODE,
                    USER_ADMINISTRATION_ACCESS_DENIED_ERROR_MESSAGE,
                )["value"]
            }
        },
    }
}
AUTHORIZATION_RESPONSES = {
    status.HTTP_403_FORBIDDEN: {
        "model": ApiErrorResponse,
        "description": "The authenticated actor lacks the exact required permission.",
        "content": {
            "application/json": {
                "example": _error_example(
                    AUTHORIZATION_ACCESS_DENIED_ERROR_CODE,
                    AUTHORIZATION_ACCESS_DENIED_ERROR_MESSAGE,
                )["value"]
            }
        },
    }
}
ROLE_ASSIGNMENT_VALIDATION_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ApiErrorResponse,
        "description": "The replacement contains an unknown or non-tenant role.",
    }
}
ROLE_ASSIGNMENT_CONFLICT_RESPONSES = _conflict_response(
    description="The role replacement would remove required administrator access.",
    examples={
        ROLE_ASSIGNMENT_CONFLICT_ERROR_CODE: _error_example(
            ROLE_ASSIGNMENT_CONFLICT_ERROR_CODE,
            ROLE_ASSIGNMENT_CONFLICT_ERROR_MESSAGE,
        )
    },
)
USER_ADMINISTRATION_VALIDATION_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ApiErrorResponse,
        "description": "User administration request validation error envelope.",
    }
}
USER_ADMINISTRATION_NOT_FOUND_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {
        "model": ApiErrorResponse,
        "description": "The user is absent or outside the authenticated tenant.",
        "content": {
            "application/json": {
                "example": _error_example(
                    USER_NOT_FOUND_ERROR_CODE,
                    USER_NOT_FOUND_ERROR_MESSAGE,
                )["value"]
            }
        },
    }
}
USER_ADMINISTRATION_CONFLICT_RESPONSES = _conflict_response(
    description="The requested account status would violate account invariants.",
    examples={
        USER_ADMINISTRATION_STATUS_CONFLICT_ERROR_CODE: _error_example(
            USER_ADMINISTRATION_STATUS_CONFLICT_ERROR_CODE,
            USER_ADMINISTRATION_STATUS_CONFLICT_ERROR_MESSAGE,
        )
    },
)

ORGANIZATION_AUTHORIZATION_RESPONSES = {
    status.HTTP_403_FORBIDDEN: {
        "model": ApiErrorResponse,
        "description": "The authenticated actor cannot administer organization settings.",
        "content": {
            "application/json": {
                "example": _error_example(
                    ORGANIZATION_ACCESS_DENIED_ERROR_CODE,
                    ORGANIZATION_ACCESS_DENIED_ERROR_MESSAGE,
                )["value"]
            }
        },
    }
}
ORGANIZATION_VALIDATION_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ApiErrorResponse,
        "description": "Organization request validation error envelope.",
    }
}
ORGANIZATION_FEATURE_UNAVAILABLE_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {
        "model": ApiErrorResponse,
        "description": "The organization module is not enabled for this tenant.",
        "content": {
            "application/json": {
                "example": _error_example(
                    ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_CODE,
                    ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_MESSAGE,
                )["value"]
            }
        },
    }
}
ORGANIZATION_NOT_FOUND_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {
        "model": ApiErrorResponse,
        "description": "The resource is absent or outside the authenticated tenant.",
        "content": {
            "application/json": {
                "examples": {
                    TENANT_NOT_FOUND_ERROR_CODE: _error_example(
                        TENANT_NOT_FOUND_ERROR_CODE,
                        TENANT_NOT_FOUND_ERROR_MESSAGE,
                    ),
                    LEGAL_ENTITY_NOT_FOUND_ERROR_CODE: _error_example(
                        LEGAL_ENTITY_NOT_FOUND_ERROR_CODE,
                        LEGAL_ENTITY_NOT_FOUND_ERROR_MESSAGE,
                    ),
                    BRANCH_NOT_FOUND_ERROR_CODE: _error_example(
                        BRANCH_NOT_FOUND_ERROR_CODE,
                        BRANCH_NOT_FOUND_ERROR_MESSAGE,
                    ),
                    ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_CODE: _error_example(
                        ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_CODE,
                        ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_MESSAGE,
                    ),
                }
            }
        },
    }
}
ORGANIZATION_CONFLICT_RESPONSES = _conflict_response(
    description="Organization code or lifecycle conflict envelope.",
    examples={
        LEGAL_ENTITY_CODE_CONFLICT_ERROR_CODE: _error_example(
            LEGAL_ENTITY_CODE_CONFLICT_ERROR_CODE,
            LEGAL_ENTITY_CODE_CONFLICT_ERROR_MESSAGE,
        ),
        BRANCH_CODE_CONFLICT_ERROR_CODE: _error_example(
            BRANCH_CODE_CONFLICT_ERROR_CODE,
            BRANCH_CODE_CONFLICT_ERROR_MESSAGE,
        ),
        ORGANIZATION_CONFLICT_ERROR_CODE: _error_example(
            ORGANIZATION_CONFLICT_ERROR_CODE,
            ORGANIZATION_CONFLICT_ERROR_MESSAGE,
        ),
    },
)

DEPARTMENT_NOT_FOUND_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {
        "model": ApiErrorResponse,
        "description": "The department is absent or outside the authenticated tenant.",
        "content": {
            "application/json": {
                "examples": {
                    TENANT_NOT_FOUND_ERROR_CODE: _error_example(
                        TENANT_NOT_FOUND_ERROR_CODE,
                        TENANT_NOT_FOUND_ERROR_MESSAGE,
                    ),
                    DEPARTMENT_NOT_FOUND_ERROR_CODE: _error_example(
                        DEPARTMENT_NOT_FOUND_ERROR_CODE,
                        DEPARTMENT_NOT_FOUND_ERROR_MESSAGE,
                    ),
                    ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_CODE: _error_example(
                        ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_CODE,
                        ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_MESSAGE,
                    ),
                }
            }
        },
    }
}
DEPARTMENT_CONFLICT_RESPONSES = _conflict_response(
    description="Department code, hierarchy, or archive conflict envelope.",
    examples={
        DEPARTMENT_CODE_CONFLICT_ERROR_CODE: _error_example(
            DEPARTMENT_CODE_CONFLICT_ERROR_CODE,
            DEPARTMENT_CODE_CONFLICT_ERROR_MESSAGE,
        ),
        DEPARTMENT_CYCLE_CONFLICT_ERROR_CODE: _error_example(
            DEPARTMENT_CYCLE_CONFLICT_ERROR_CODE,
            DEPARTMENT_CYCLE_CONFLICT_ERROR_MESSAGE,
        ),
        ORGANIZATION_CONFLICT_ERROR_CODE: _error_example(
            ORGANIZATION_CONFLICT_ERROR_CODE,
            ORGANIZATION_CONFLICT_ERROR_MESSAGE,
        ),
    },
)

POSITION_NOT_FOUND_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {
        "model": ApiErrorResponse,
        "description": "The position is absent or outside the authenticated tenant.",
        "content": {
            "application/json": {
                "examples": {
                    TENANT_NOT_FOUND_ERROR_CODE: _error_example(
                        TENANT_NOT_FOUND_ERROR_CODE,
                        TENANT_NOT_FOUND_ERROR_MESSAGE,
                    ),
                    POSITION_NOT_FOUND_ERROR_CODE: _error_example(
                        POSITION_NOT_FOUND_ERROR_CODE,
                        POSITION_NOT_FOUND_ERROR_MESSAGE,
                    ),
                    ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_CODE: _error_example(
                        ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_CODE,
                        ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_MESSAGE,
                    ),
                }
            }
        },
    }
}
POSITION_CONFLICT_RESPONSES = _conflict_response(
    description="Position code or archive lifecycle conflict envelope.",
    examples={
        POSITION_CODE_CONFLICT_ERROR_CODE: _error_example(
            POSITION_CODE_CONFLICT_ERROR_CODE,
            POSITION_CODE_CONFLICT_ERROR_MESSAGE,
        ),
        ORGANIZATION_CONFLICT_ERROR_CODE: _error_example(
            ORGANIZATION_CONFLICT_ERROR_CODE,
            ORGANIZATION_CONFLICT_ERROR_MESSAGE,
        ),
    },
)

EMPLOYEE_ASSIGNMENT_AUTHORIZATION_RESPONSES = {
    status.HTTP_403_FORBIDDEN: {
        "model": ApiErrorResponse,
        "description": "The authenticated actor is outside the required employee scope.",
        "content": {
            "application/json": {
                "example": _error_example(
                    EMPLOYEE_ASSIGNMENT_ACCESS_DENIED_ERROR_CODE,
                    EMPLOYEE_ASSIGNMENT_ACCESS_DENIED_ERROR_MESSAGE,
                )["value"]
            }
        },
    }
}
EMPLOYEE_ASSIGNMENT_VALIDATION_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ApiErrorResponse,
        "description": "Employee assignment request validation error envelope.",
    }
}
EMPLOYEE_ASSIGNMENT_NOT_FOUND_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {
        "model": ApiErrorResponse,
        "description": "The assignment is absent or outside the authenticated tenant.",
        "content": {
            "application/json": {
                "examples": {
                    TENANT_NOT_FOUND_ERROR_CODE: _error_example(
                        TENANT_NOT_FOUND_ERROR_CODE,
                        TENANT_NOT_FOUND_ERROR_MESSAGE,
                    ),
                    EMPLOYEE_ASSIGNMENT_NOT_FOUND_ERROR_CODE: _error_example(
                        EMPLOYEE_ASSIGNMENT_NOT_FOUND_ERROR_CODE,
                        EMPLOYEE_ASSIGNMENT_NOT_FOUND_ERROR_MESSAGE,
                    ),
                    ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_CODE: _error_example(
                        ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_CODE,
                        ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_MESSAGE,
                    ),
                }
            }
        },
    }
}
EMPLOYEE_ASSIGNMENT_CONFLICT_RESPONSES = _conflict_response(
    description="Employee assignment history or reference conflict envelope.",
    examples={
        EMPLOYEE_ASSIGNMENT_CONFLICT_ERROR_CODE: _error_example(
            EMPLOYEE_ASSIGNMENT_CONFLICT_ERROR_CODE,
            EMPLOYEE_ASSIGNMENT_CONFLICT_ERROR_MESSAGE,
        ),
        CONCURRENT_WRITE_CONFLICT_ERROR_CODE: _error_example(
            CONCURRENT_WRITE_CONFLICT_ERROR_CODE,
            CONCURRENT_WRITE_CONFLICT_MESSAGE,
        ),
    },
)


EMPLOYEE_COMMAND_CONFLICT_RESPONSES = _conflict_response(
    description="Employee command conflict envelope.",
    examples={
        EMPLOYEE_NUMBER_CONFLICT_ERROR_CODE: _error_example(
            EMPLOYEE_NUMBER_CONFLICT_ERROR_CODE,
            EMPLOYEE_NUMBER_CONFLICT_ERROR_MESSAGE,
        ),
        EMPLOYEE_WORK_EMAIL_CONFLICT_ERROR_CODE: _error_example(
            EMPLOYEE_WORK_EMAIL_CONFLICT_ERROR_CODE,
            EMPLOYEE_WORK_EMAIL_CONFLICT_ERROR_MESSAGE,
        ),
        EMPLOYEE_LIFECYCLE_CONFLICT_ERROR_CODE: _error_example(
            EMPLOYEE_LIFECYCLE_CONFLICT_ERROR_CODE,
            EMPLOYEE_LIFECYCLE_CONFLICT_ERROR_MESSAGE,
        ),
        EMPLOYEE_OPEN_PROCESS_CONFLICT_ERROR_CODE: _error_example(
            EMPLOYEE_OPEN_PROCESS_CONFLICT_ERROR_CODE,
            EMPLOYEE_OPEN_PROCESS_CONFLICT_ERROR_MESSAGE,
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
EMPLOYEE_ACCOUNT_LINK_CONFLICT_RESPONSES = _conflict_response(
    description="Employee account-link conflict envelope.",
    examples={
        EMPLOYEE_ACCOUNT_LINK_CONFLICT_ERROR_CODE: _error_example(
            EMPLOYEE_ACCOUNT_LINK_CONFLICT_ERROR_CODE,
            EMPLOYEE_ACCOUNT_LINK_CONFLICT_ERROR_MESSAGE,
        ),
        CONCURRENT_WRITE_CONFLICT_ERROR_CODE: _error_example(
            CONCURRENT_WRITE_CONFLICT_ERROR_CODE,
            CONCURRENT_WRITE_CONFLICT_MESSAGE,
        ),
        DATA_INTEGRITY_CONFLICT_ERROR_CODE: _error_example(
            DATA_INTEGRITY_CONFLICT_ERROR_CODE,
            DATA_INTEGRITY_CONFLICT_MESSAGE,
        ),
    },
)
IDEMPOTENT_EMPLOYEE_COMMAND_CONFLICT_RESPONSES = _conflict_response(
    description="Idempotent employee command conflict envelope.",
    examples={
        **EMPLOYEE_COMMAND_CONFLICT_RESPONSES[status.HTTP_409_CONFLICT]["content"][
            "application/json"
        ]["examples"],
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
    if isinstance(exc, ReportingAccessDeniedError):
        return authorization_access_denied_error()
    if isinstance(exc, ReportingValidationError):
        return reporting_validation_error()
    if isinstance(exc, ReportingNotFoundError):
        return reporting_not_found_error()
    if isinstance(exc, ReportingFeatureUnavailableError):
        return reporting_feature_unavailable_error()
    if isinstance(exc, ReportingStorageUnavailableError):
        return reporting_storage_unavailable_error()
    if isinstance(exc, ReportingConflictError):
        return reporting_conflict_error()
    if isinstance(exc, Phase7AccessDeniedError):
        return authorization_access_denied_error()
    if isinstance(exc, Phase7VersionConflictError):
        return concurrent_write_conflict_error()
    if isinstance(exc, Phase7NotFoundError):
        return phase7_not_found_error()
    if isinstance(exc, Phase7ValidationError):
        return phase7_validation_error()
    if isinstance(exc, Phase7FeatureUnavailableError):
        return phase7_feature_unavailable_error()
    if isinstance(exc, Phase7ConflictError):
        return phase7_conflict_error()
    if isinstance(exc, AuthenticationRateLimitExceededError):
        return authentication_rate_limit_error()
    if isinstance(exc, InvalidCredentialsError):
        return invalid_credentials_error()
    if isinstance(exc, InvalidPlatformCredentialsError):
        return invalid_credentials_error()
    if isinstance(exc, InvalidActivationError):
        return invalid_activation_error()
    if isinstance(exc, InvalidPasswordResetError):
        return invalid_password_reset_error()
    if isinstance(exc, InvalidSessionError):
        return session_invalid_error()
    if isinstance(exc, InvalidPlatformSessionError):
        return session_invalid_error()
    if isinstance(exc, PlatformRoleRequiredError):
        return platform_role_required_error()
    if isinstance(exc, InvalidOrganizationSelectionError):
        return organization_selection_invalid_error()
    if isinstance(exc, OrganizationSwitchUnavailableError):
        return organization_switch_unavailable_error()
    if isinstance(exc, AuditAccessDeniedError):
        return authorization_access_denied_error()
    if isinstance(exc, AuditEventNotFoundError):
        return audit_event_not_found_error()
    if isinstance(exc, AuthorizationAccessDeniedError):
        return authorization_access_denied_error()
    if isinstance(exc, RoleAssignmentInvalidError):
        return role_assignment_invalid_error()
    if isinstance(exc, RoleAssignmentConflictError):
        return role_assignment_conflict_error(str(exc))
    if isinstance(exc, RoleAssignmentUserNotFoundError):
        return user_not_found_error()
    if isinstance(exc, InvitationAccessDeniedError):
        return invitation_access_denied_error()
    if isinstance(exc, InvitationConflictError):
        return invitation_conflict_error()
    if isinstance(exc, UserAdministrationAccessDeniedError):
        return user_administration_access_denied_error()
    if isinstance(exc, UserAdministrationUserNotFoundError):
        return user_not_found_error()
    if isinstance(exc, UserAdministrationStatusConflictError):
        return user_administration_status_conflict_error(str(exc))
    if isinstance(exc, EmployeeAssignmentAccessDeniedError):
        return employee_assignment_access_denied_error()
    if isinstance(exc, EmployeeAssignmentNotFoundError):
        return employee_assignment_not_found_error()
    if isinstance(exc, EmployeeAssignmentConflictError):
        return employee_assignment_conflict_error(str(exc))
    if isinstance(exc, EmployeeProfileChangeRequestInvalidError):
        return employee_profile_change_request_validation_error()
    if isinstance(exc, EmployeeProfileChangeRequestNotFoundError):
        return employee_profile_change_request_not_found_error()
    if isinstance(exc, EmployeeProfileChangeRequestStaleProfileError):
        return employee_profile_change_request_stale_profile_error()
    if isinstance(exc, EmployeeProfileChangeRequestConflictError):
        return employee_profile_change_request_conflict_error()
    if isinstance(exc, DocumentValidationError):
        return document_validation_error(str(exc))
    if isinstance(exc, DocumentTypeNotFoundError):
        return document_type_not_found_error()
    if isinstance(exc, DocumentNotFoundError):
        return document_not_found_error()
    if isinstance(exc, DocumentVersionConflictError):
        return concurrent_write_conflict_error()
    if isinstance(exc, DocumentConflictError):
        return document_conflict_error(str(exc))
    if isinstance(exc, DocumentStorageUnavailableError):
        return document_storage_unavailable_error()
    if isinstance(exc, LeaveAccessDeniedError):
        return authorization_access_denied_error()
    if isinstance(exc, LeaveEmployeeLinkUnavailableError):
        return employee_account_link_conflict_error()
    if isinstance(exc, LeaveNotFoundError):
        return leave_not_found_error()
    if isinstance(exc, LeaveVersionConflictError):
        return concurrent_write_conflict_error()
    if isinstance(exc, LeaveInsufficientBalanceError):
        return leave_insufficient_balance_error(str(exc))
    if isinstance(exc, LeaveValidationError):
        return leave_validation_error(str(exc))
    if isinstance(exc, LeaveConflictError):
        return leave_conflict_error(str(exc))
    if isinstance(exc, EmployeeAccountLinkUnavailableError):
        return employee_account_link_conflict_error()
    if isinstance(exc, OrganizationAccessDeniedError):
        return organization_access_denied_error()
    if isinstance(exc, OrganizationFeatureUnavailableError):
        return organization_feature_unavailable_error()
    if isinstance(exc, LegalEntityNotFoundError):
        return legal_entity_not_found_error()
    if isinstance(exc, BranchNotFoundError):
        return branch_not_found_error()
    if isinstance(exc, DepartmentNotFoundError):
        return department_not_found_error()
    if isinstance(exc, PositionNotFoundError):
        return position_not_found_error()
    if isinstance(exc, DuplicateLegalEntityCodeError):
        return legal_entity_code_conflict_error()
    if isinstance(exc, DuplicateBranchCodeError):
        return branch_code_conflict_error()
    if isinstance(exc, DuplicateDepartmentCodeError):
        return department_code_conflict_error()
    if isinstance(exc, DuplicatePositionCodeError):
        return position_code_conflict_error()
    if isinstance(exc, DepartmentCycleError):
        return department_cycle_conflict_error()
    if isinstance(exc, DepartmentConflictError):
        return organization_conflict_error(str(exc))
    if isinstance(exc, PositionConflictError):
        return organization_conflict_error(str(exc))
    if isinstance(exc, OrganizationConflictError):
        return organization_conflict_error(str(exc))
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
    if isinstance(exc, DuplicateWorkEmailError):
        return employee_work_email_conflict_error()
    if isinstance(exc, EmployeeDateRangeError):
        return employee_date_range_error(str(exc))
    if isinstance(exc, EmployeeLifecycleConflictError):
        return employee_lifecycle_conflict_error(str(exc))
    if isinstance(exc, EmployeeOpenProcessConflictError):
        return employee_open_process_conflict_error()
    if isinstance(exc, EmployeeLifecycleError):
        return employee_lifecycle_error(str(exc))
    if isinstance(exc, EmployeeVersionConflictError):
        return concurrent_write_conflict_error()
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
        if exc.constraint_name in {
            EMPLOYEE_NUMBER_UNIQUE_CONSTRAINT,
            EMPLOYEE_NUMBER_NORMALIZED_UNIQUE_CONSTRAINT,
        }:
            return employee_number_conflict_error()
        if exc.constraint_name == EMPLOYEE_WORK_EMAIL_NORMALIZED_UNIQUE_CONSTRAINT:
            return employee_work_email_conflict_error()
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


def platform_role_required_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        code=PLATFORM_ROLE_REQUIRED_ERROR_CODE,
        message=PLATFORM_ROLE_REQUIRED_ERROR_MESSAGE,
    )


def platform_step_up_required_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        code=PLATFORM_STEP_UP_REQUIRED_ERROR_CODE,
        message=PLATFORM_STEP_UP_REQUIRED_ERROR_MESSAGE,
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


def invalid_credentials_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code=INVALID_CREDENTIALS_ERROR_CODE,
        message=INVALID_CREDENTIALS_ERROR_MESSAGE,
    )


def authentication_rate_limit_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code=AUTHENTICATION_RATE_LIMIT_ERROR_CODE,
        message=AUTHENTICATION_RATE_LIMIT_ERROR_MESSAGE,
    )


def invalid_activation_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code=INVALID_ACTIVATION_ERROR_CODE,
        message=INVALID_ACTIVATION_ERROR_MESSAGE,
    )


def invalid_password_reset_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code=INVALID_PASSWORD_RESET_ERROR_CODE,
        message=INVALID_PASSWORD_RESET_ERROR_MESSAGE,
    )


def authentication_required_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code=AUTHENTICATION_REQUIRED_ERROR_CODE,
        message=AUTHENTICATION_REQUIRED_ERROR_MESSAGE,
    )


def session_invalid_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code=SESSION_INVALID_ERROR_CODE,
        message=SESSION_INVALID_ERROR_MESSAGE,
    )


def organization_selection_invalid_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code=ORGANIZATION_SELECTION_INVALID_ERROR_CODE,
        message=ORGANIZATION_SELECTION_INVALID_ERROR_MESSAGE,
    )


def organization_switch_unavailable_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=ORGANIZATION_SWITCH_UNAVAILABLE_ERROR_CODE,
        message=ORGANIZATION_SWITCH_UNAVAILABLE_ERROR_MESSAGE,
    )


def invitation_access_denied_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        code=INVITATION_ACCESS_DENIED_ERROR_CODE,
        message=INVITATION_ACCESS_DENIED_ERROR_MESSAGE,
    )


def invitation_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=INVITATION_CONFLICT_ERROR_CODE,
        message=INVITATION_CONFLICT_ERROR_MESSAGE,
    )


def user_administration_access_denied_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        code=USER_ADMINISTRATION_ACCESS_DENIED_ERROR_CODE,
        message=USER_ADMINISTRATION_ACCESS_DENIED_ERROR_MESSAGE,
    )


def authorization_access_denied_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        code=AUTHORIZATION_ACCESS_DENIED_ERROR_CODE,
        message=AUTHORIZATION_ACCESS_DENIED_ERROR_MESSAGE,
    )


def audit_event_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=AUDIT_EVENT_NOT_FOUND_ERROR_CODE,
        message=AUDIT_EVENT_NOT_FOUND_ERROR_MESSAGE,
    )


def audit_pagination_validation_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=AUDIT_VALIDATION_ERROR_CODE,
        message=AUDIT_VALIDATION_ERROR_MESSAGE,
    )


def role_assignment_invalid_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=ROLE_ASSIGNMENT_INVALID_ERROR_CODE,
        message=ROLE_ASSIGNMENT_INVALID_ERROR_MESSAGE,
    )


def role_assignment_conflict_error(message: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=ROLE_ASSIGNMENT_CONFLICT_ERROR_CODE,
        message=message or ROLE_ASSIGNMENT_CONFLICT_ERROR_MESSAGE,
    )


def user_administration_validation_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=USER_ADMINISTRATION_VALIDATION_ERROR_CODE,
        message=USER_ADMINISTRATION_VALIDATION_ERROR_MESSAGE,
    )


def user_administration_status_conflict_error(message: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=USER_ADMINISTRATION_STATUS_CONFLICT_ERROR_CODE,
        message=message or USER_ADMINISTRATION_STATUS_CONFLICT_ERROR_MESSAGE,
    )


def organization_access_denied_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        code=ORGANIZATION_ACCESS_DENIED_ERROR_CODE,
        message=ORGANIZATION_ACCESS_DENIED_ERROR_MESSAGE,
    )


def organization_feature_unavailable_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_CODE,
        message=ORGANIZATION_FEATURE_UNAVAILABLE_ERROR_MESSAGE,
    )


def legal_entity_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=LEGAL_ENTITY_NOT_FOUND_ERROR_CODE,
        message=LEGAL_ENTITY_NOT_FOUND_ERROR_MESSAGE,
    )


def branch_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=BRANCH_NOT_FOUND_ERROR_CODE,
        message=BRANCH_NOT_FOUND_ERROR_MESSAGE,
    )


def legal_entity_code_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=LEGAL_ENTITY_CODE_CONFLICT_ERROR_CODE,
        message=LEGAL_ENTITY_CODE_CONFLICT_ERROR_MESSAGE,
    )


def branch_code_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=BRANCH_CODE_CONFLICT_ERROR_CODE,
        message=BRANCH_CODE_CONFLICT_ERROR_MESSAGE,
    )


def department_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=DEPARTMENT_NOT_FOUND_ERROR_CODE,
        message=DEPARTMENT_NOT_FOUND_ERROR_MESSAGE,
    )


def department_code_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=DEPARTMENT_CODE_CONFLICT_ERROR_CODE,
        message=DEPARTMENT_CODE_CONFLICT_ERROR_MESSAGE,
    )


def department_cycle_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=DEPARTMENT_CYCLE_CONFLICT_ERROR_CODE,
        message=DEPARTMENT_CYCLE_CONFLICT_ERROR_MESSAGE,
    )


def position_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=POSITION_NOT_FOUND_ERROR_CODE,
        message=POSITION_NOT_FOUND_ERROR_MESSAGE,
    )


def position_code_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=POSITION_CODE_CONFLICT_ERROR_CODE,
        message=POSITION_CODE_CONFLICT_ERROR_MESSAGE,
    )


def organization_conflict_error(message: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=ORGANIZATION_CONFLICT_ERROR_CODE,
        message=message or ORGANIZATION_CONFLICT_ERROR_MESSAGE,
    )


def employee_assignment_access_denied_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        code=EMPLOYEE_ASSIGNMENT_ACCESS_DENIED_ERROR_CODE,
        message=EMPLOYEE_ASSIGNMENT_ACCESS_DENIED_ERROR_MESSAGE,
    )


def employee_assignment_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=EMPLOYEE_ASSIGNMENT_NOT_FOUND_ERROR_CODE,
        message=EMPLOYEE_ASSIGNMENT_NOT_FOUND_ERROR_MESSAGE,
    )


def employee_assignment_conflict_error(message: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=EMPLOYEE_ASSIGNMENT_CONFLICT_ERROR_CODE,
        message=message or EMPLOYEE_ASSIGNMENT_CONFLICT_ERROR_MESSAGE,
    )


def employee_assignment_validation_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=EMPLOYEE_ASSIGNMENT_VALIDATION_ERROR_CODE,
        message=EMPLOYEE_ASSIGNMENT_VALIDATION_ERROR_MESSAGE,
    )


def organization_pagination_validation_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=ORGANIZATION_VALIDATION_ERROR_CODE,
        message=ORGANIZATION_VALIDATION_ERROR_MESSAGE,
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


def employee_work_email_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=EMPLOYEE_WORK_EMAIL_CONFLICT_ERROR_CODE,
        message=EMPLOYEE_WORK_EMAIL_CONFLICT_ERROR_MESSAGE,
    )


def employee_account_link_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=EMPLOYEE_ACCOUNT_LINK_CONFLICT_ERROR_CODE,
        message=EMPLOYEE_ACCOUNT_LINK_CONFLICT_ERROR_MESSAGE,
    )


def employee_profile_change_request_validation_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=EMPLOYEE_PROFILE_CHANGE_REQUEST_VALIDATION_ERROR_CODE,
        message=EMPLOYEE_PROFILE_CHANGE_REQUEST_VALIDATION_ERROR_MESSAGE,
    )


def employee_profile_change_request_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=EMPLOYEE_PROFILE_CHANGE_REQUEST_NOT_FOUND_ERROR_CODE,
        message=EMPLOYEE_PROFILE_CHANGE_REQUEST_NOT_FOUND_ERROR_MESSAGE,
    )


def employee_profile_change_request_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_ERROR_CODE,
        message=EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_ERROR_MESSAGE,
    )


def employee_profile_change_request_stale_profile_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=EMPLOYEE_PROFILE_CHANGE_REQUEST_STALE_PROFILE_ERROR_CODE,
        message=EMPLOYEE_PROFILE_CHANGE_REQUEST_STALE_PROFILE_ERROR_MESSAGE,
    )


def document_validation_error(message: str = "") -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=DOCUMENT_VALIDATION_ERROR_CODE,
        message=message or DOCUMENT_VALIDATION_ERROR_MESSAGE,
    )


def document_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=DOCUMENT_NOT_FOUND_ERROR_CODE,
        message=DOCUMENT_NOT_FOUND_ERROR_MESSAGE,
    )


def document_type_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=DOCUMENT_TYPE_NOT_FOUND_ERROR_CODE,
        message=DOCUMENT_TYPE_NOT_FOUND_ERROR_MESSAGE,
    )


def document_conflict_error(message: str = "") -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=DOCUMENT_CONFLICT_ERROR_CODE,
        message=message or DOCUMENT_CONFLICT_ERROR_MESSAGE,
    )


def document_storage_unavailable_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code=DOCUMENT_STORAGE_UNAVAILABLE_ERROR_CODE,
        message=DOCUMENT_STORAGE_UNAVAILABLE_ERROR_MESSAGE,
    )


def reporting_validation_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=REPORTING_VALIDATION_ERROR_CODE,
        message=REPORTING_VALIDATION_ERROR_MESSAGE,
    )


def reporting_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=REPORTING_NOT_FOUND_ERROR_CODE,
        message=REPORTING_NOT_FOUND_ERROR_MESSAGE,
    )


def reporting_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=REPORTING_CONFLICT_ERROR_CODE,
        message=REPORTING_CONFLICT_ERROR_MESSAGE,
    )


def reporting_feature_unavailable_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=REPORTING_FEATURE_UNAVAILABLE_ERROR_CODE,
        message=REPORTING_FEATURE_UNAVAILABLE_ERROR_MESSAGE,
    )


def reporting_storage_unavailable_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code=REPORTING_STORAGE_UNAVAILABLE_ERROR_CODE,
        message=REPORTING_STORAGE_UNAVAILABLE_ERROR_MESSAGE,
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


def employee_lifecycle_conflict_error(message: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=EMPLOYEE_LIFECYCLE_CONFLICT_ERROR_CODE,
        message=message or EMPLOYEE_LIFECYCLE_CONFLICT_ERROR_MESSAGE,
    )


def employee_open_process_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=EMPLOYEE_OPEN_PROCESS_CONFLICT_ERROR_CODE,
        message=EMPLOYEE_OPEN_PROCESS_CONFLICT_ERROR_MESSAGE,
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


def leave_validation_error(message: str = "") -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=LEAVE_VALIDATION_ERROR_CODE,
        message=message or LEAVE_VALIDATION_ERROR_MESSAGE,
    )


def leave_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=LEAVE_NOT_FOUND_ERROR_CODE,
        message=LEAVE_NOT_FOUND_ERROR_MESSAGE,
    )


def phase7_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="self_service_resource_not_found",
        message="The requested self-service resource was not found",
    )


def phase7_validation_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="self_service_validation_error",
        message="Self-service request validation failed",
    )


def phase7_feature_unavailable_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="self_service_feature_unavailable",
        message="This self-service feature is not enabled",
    )


def phase7_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="self_service_conflict",
        message="The resource changed or cannot be changed in its current state",
    )


def leave_conflict_error(message: str = "") -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=LEAVE_CONFLICT_ERROR_CODE,
        message=message or "The requested leave operation conflicts with current state",
    )


def leave_insufficient_balance_error(message: str = "") -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code=LEAVE_INSUFFICIENT_BALANCE_ERROR_CODE,
        message=message or "Available leave balance is insufficient",
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
    if any(
        _matches_api_prefix(path, prefix)
        for prefix in (REPORT_API_PREFIX, EXPORT_JOB_API_PREFIX, EMPLOYEE_IMPORT_API_PREFIX)
    ):
        return reporting_validation_error()
    if any(_matches_api_prefix(path, prefix) for prefix in PHASE7_API_PREFIXES):
        return phase7_validation_error()
    if (
        _matches_api_prefix(path, AUTH_API_PREFIX)
        or _matches_api_prefix(path, PLATFORM_AUTH_API_PREFIX)
        or _matches_api_prefix(path, USER_INVITATION_API_PREFIX)
    ):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=AUTH_VALIDATION_ERROR_CODE,
            message=AUTH_VALIDATION_ERROR_MESSAGE,
        )
    if _matches_api_prefix(path, USER_ADMINISTRATION_API_PREFIX):
        return user_administration_validation_error()
    if (
        _matches_api_prefix(path, LEGAL_ENTITY_API_PREFIX)
        or _matches_api_prefix(path, BRANCH_API_PREFIX)
        or _matches_api_prefix(path, DEPARTMENT_API_PREFIX)
        or _matches_api_prefix(path, POSITION_API_PREFIX)
        or _matches_api_prefix(path, ORG_CHART_API_PREFIX)
    ):
        return organization_pagination_validation_error()
    if _matches_api_prefix(path, EMPLOYEE_ASSIGNMENT_API_PREFIX) or _matches_api_prefix(
        path, MANAGER_TEAM_API_PREFIX
    ):
        return employee_assignment_validation_error()
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
    if any(
        _matches_api_prefix(path, prefix)
        for prefix in (
            LEAVE_TYPE_API_PREFIX,
            HOLIDAY_CALENDAR_API_PREFIX,
            LEAVE_POLICY_API_PREFIX,
            LEAVE_ADJUSTMENT_API_PREFIX,
            OWN_LEAVE_BALANCE_API_PREFIX,
            APPROVAL_TASK_API_PREFIX,
            TEAM_CALENDAR_API_PREFIX,
        )
    ):
        return leave_validation_error()
    if _is_leave_balance_api_path(path):
        return _leave_balance_request_validation_error()
    if _matches_api_prefix(path, OWN_PROFILE_CHANGE_REQUEST_API_PREFIX) or _matches_api_prefix(
        path, HR_PROFILE_CHANGE_REQUEST_API_PREFIX
    ):
        return employee_profile_change_request_validation_error()
    if (
        _matches_api_prefix(path, DOCUMENT_TYPE_API_PREFIX)
        or _matches_api_prefix(path, OWN_DOCUMENT_API_PREFIX)
        or (
            _matches_api_prefix(path, EMPLOYEE_API_PREFIX)
            and "/documents" in path
        )
    ):
        return document_validation_error()
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
