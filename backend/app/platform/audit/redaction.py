"""Event-specific audit metadata allowlisting and identifier redaction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from ipaddress import ip_address
from re import compile as compile_regex
from uuid import UUID

from app.platform.audit.contracts import AuditEventDraft, AuditEventType

_SAFE_VALUE = compile_regex(r"[A-Za-z0-9](?:[A-Za-z0-9_.:-]{0,126}[A-Za-z0-9])?")
_FORBIDDEN_KEY_PARTS = frozenset(
    {
        "authorization",
        "bank",
        "body",
        "content",
        "cookie",
        "credential",
        "document",
        "hash",
        "health",
        "iban",
        "medical",
        "otp",
        "passphrase",
        "password",
        "payload",
        "payroll",
        "salary",
        "secret",
        "ssn",
        "tckn",
        "token",
    }
)


@dataclass(frozen=True, slots=True)
class AuditMetadataPolicy:
    metadata_keys: frozenset[str] = frozenset()
    changed_fields: frozenset[str] = frozenset()
    value_fields: frozenset[str] = frozenset()


_ROLE_CODES = frozenset(
    {
        "tenant_admin",
        "hr_director",
        "hr_specialist",
        "it_admin",
        "auditor",
        "manager",
        "employee",
    }
)
_STATUS_VALUES = frozenset(
    {
        "invited",
        "active",
        "on_leave",
        "terminated",
        "inactive",
        "archived",
        "locked",
        "disabled",
    }
)
_METADATA_VALUE_SETS: dict[str, frozenset[str]] = {
    "authentication_method": frozenset({"local", "organization_selection"}),
    "failure_reason": frozenset({"authentication_failed"}),
    "initial_role": frozenset({"employee"}),
    "before_status": _STATUS_VALUES,
    "after_status": _STATUS_VALUES,
    "revocation_reason": frozenset(
        {
            "logout",
            "account_locked",
            "account_disabled",
            "refresh_reuse",
            "organization_switch",
            "employee_termination",
        }
    ),
    "source": frozenset(
        {"access_session", "account_status", "refresh_cookie", "employee_lifecycle"}
    ),
    "status": frozenset({"provisioning", "trial", "active", "suspended", "offboarding", "closed"}),
    "plan_code": frozenset({"core", "professional", "enterprise"}),
    "data_region": frozenset({"tr-1", "eu-1"}),
    "link_status": frozenset({"linked", "relinked", "unlinked"}),
    "before_request_status": frozenset({"none", "submitted"}),
    "after_request_status": frozenset({"submitted", "approved", "rejected", "cancelled"}),
    "reason_code": frozenset(
        {
            "employee_submitted",
            "hr_approved",
            "hr_rejected",
            "employee_cancelled",
            "resignation",
            "dismissal",
            "retirement",
            "contract_end",
            "other",
        }
    ),
    "before_state": frozenset(
        {
            "active",
            "archived",
            "pending_upload",
            "pending_scan",
            "available",
            "infected",
            "scan_error",
            "rejected",
        }
    ),
    "after_state": frozenset(
        {
            "active",
            "archived",
            "pending_upload",
            "pending_scan",
            "available",
            "infected",
            "scan_error",
            "rejected",
        }
    ),
    "file_class": frozenset({"pdf", "jpeg", "png"}),
    "scan_result": frozenset({"clean", "infected", "error"}),
    "scanner_provider": frozenset({"clamav", "local_clean"}),
    "access_scope": frozenset({"hr", "own"}),
    "sensitivity": frozenset({"standard", "sensitive", "highly_sensitive"}),
}

_POLICIES: dict[AuditEventType, AuditMetadataPolicy] = {
    AuditEventType.LOGIN_SUCCEEDED: AuditMetadataPolicy(
        metadata_keys=frozenset({"authentication_method"})
    ),
    AuditEventType.LOGIN_FAILED: AuditMetadataPolicy(metadata_keys=frozenset({"failure_reason"})),
    AuditEventType.PLATFORM_LOGIN_SUCCEEDED: AuditMetadataPolicy(),
    AuditEventType.PLATFORM_LOGIN_FAILED: AuditMetadataPolicy(),
    AuditEventType.PLATFORM_LOGIN_DENIED: AuditMetadataPolicy(),
    AuditEventType.ACTIVATION_COMPLETED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_status", "after_status"}),
        changed_fields=frozenset({"status"}),
    ),
    AuditEventType.PASSWORD_RESET_REQUESTED: AuditMetadataPolicy(),
    AuditEventType.PASSWORD_RESET_COMPLETED: AuditMetadataPolicy(),
    AuditEventType.INVITATION_CREATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"is_reinvite", "initial_role"}),
        changed_fields=frozenset({"status", "roles"}),
    ),
    AuditEventType.ROLES_REPLACED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_role_codes", "after_role_codes", "permission_version"}),
        changed_fields=frozenset({"roles", "permission_version"}),
    ),
    AuditEventType.USER_STATUS_CHANGED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_status", "after_status", "sessions_revoked"}),
        changed_fields=frozenset({"full_name", "status"}),
    ),
    AuditEventType.SESSION_STARTED: AuditMetadataPolicy(
        metadata_keys=frozenset({"authentication_method"})
    ),
    AuditEventType.SESSION_REFRESHED: AuditMetadataPolicy(),
    AuditEventType.SESSION_REUSE_DETECTED: AuditMetadataPolicy(
        metadata_keys=frozenset({"revocation_reason"})
    ),
    AuditEventType.SESSION_REVOKED: AuditMetadataPolicy(
        metadata_keys=frozenset({"revocation_reason", "source"})
    ),
    AuditEventType.PLATFORM_SESSION_STARTED: AuditMetadataPolicy(),
    AuditEventType.PLATFORM_SESSION_REFRESHED: AuditMetadataPolicy(),
    AuditEventType.PLATFORM_SESSION_REUSE_DETECTED: AuditMetadataPolicy(),
    AuditEventType.PLATFORM_SESSION_REVOKED: AuditMetadataPolicy(
        metadata_keys=frozenset({"revocation_reason", "source"})
    ),
    AuditEventType.PLATFORM_TENANT_CREATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"status", "plan_code", "data_region"})
    ),
    AuditEventType.PLATFORM_TENANT_STATUS_CHANGED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_status", "after_status"}),
        changed_fields=frozenset({"status"}),
    ),
    AuditEventType.PLATFORM_TENANT_SETTING_CHANGED: AuditMetadataPolicy(
        changed_fields=frozenset(
            {
                "name",
                "plan_code",
                "data_region",
                "locale",
                "timezone",
                "week_start_day",
                "date_format",
                "time_format",
                "active_employee_limit",
            }
        )
    ),
    AuditEventType.PLATFORM_FEATURE_FLAG_CHANGED: AuditMetadataPolicy(
        metadata_keys=frozenset({"feature_key", "before_enabled", "after_enabled"}),
        changed_fields=frozenset({"enabled"}),
    ),
    AuditEventType.TENANT_SETTING_CHANGED: AuditMetadataPolicy(
        changed_fields=frozenset(
            {"locale", "timezone", "week_start_day", "date_format", "time_format"}
        )
    ),
    AuditEventType.LEGAL_ENTITY_CREATED: AuditMetadataPolicy(
        changed_fields=frozenset(
            {
                "code",
                "name",
                "registered_name",
                "country_code",
                "tax_number",
                "timezone",
                "status",
            }
        )
    ),
    AuditEventType.LEGAL_ENTITY_UPDATED: AuditMetadataPolicy(
        changed_fields=frozenset(
            {
                "name",
                "registered_name",
                "country_code",
                "tax_number",
                "timezone",
                "status",
            }
        )
    ),
    AuditEventType.BRANCH_CREATED: AuditMetadataPolicy(
        changed_fields=frozenset(
            {
                "legal_entity_id",
                "code",
                "name",
                "timezone",
                "country_code",
                "city",
                "address",
                "status",
            }
        )
    ),
    AuditEventType.BRANCH_UPDATED: AuditMetadataPolicy(
        changed_fields=frozenset({"name", "timezone", "country_code", "city", "address"})
    ),
    AuditEventType.BRANCH_ARCHIVED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_status", "after_status"}),
        changed_fields=frozenset({"status", "archived_at"}),
    ),
    AuditEventType.DEPARTMENT_CREATED: AuditMetadataPolicy(
        changed_fields=frozenset({"parent_id", "code", "name", "status"})
    ),
    AuditEventType.DEPARTMENT_UPDATED: AuditMetadataPolicy(
        changed_fields=frozenset({"name", "parent_id"})
    ),
    AuditEventType.DEPARTMENT_ARCHIVED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_status", "after_status"}),
        changed_fields=frozenset({"status", "archived_at"}),
    ),
    AuditEventType.POSITION_CREATED: AuditMetadataPolicy(
        changed_fields=frozenset({"code", "title", "status"})
    ),
    AuditEventType.POSITION_UPDATED: AuditMetadataPolicy(changed_fields=frozenset({"title"})),
    AuditEventType.POSITION_ARCHIVED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_status", "after_status"}),
        changed_fields=frozenset({"status", "archived_at"}),
    ),
    AuditEventType.EMPLOYEE_CREATED: AuditMetadataPolicy(
        changed_fields=frozenset(
            {
                "employee_number",
                "first_name",
                "last_name",
                "email",
                "department",
                "position",
                "status",
                "employment_start_date",
                "employment_end_date",
            }
        )
    ),
    AuditEventType.EMPLOYEE_UPDATED: AuditMetadataPolicy(
        changed_fields=frozenset(
            {
                "employee_number",
                "first_name",
                "last_name",
                "email",
                "department",
                "position",
                "status",
                "employment_start_date",
                "employment_end_date",
            }
        )
    ),
    AuditEventType.EMPLOYEE_LIFECYCLE_CHANGED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "before_status",
                "after_status",
                "reason_code",
                "assignment_closed",
                "membership_deactivated",
                "sessions_revoked",
            }
        ),
        changed_fields=frozenset(
            {"status", "employment_end_date", "termination_reason"}
        ),
    ),
    AuditEventType.EMPLOYEE_PERSONAL_PROFILE_UPDATED: AuditMetadataPolicy(
        changed_fields=frozenset(
            {
                "first_name",
                "last_name",
                "email",
                "preferred_name",
                "birth_date",
                "phone",
            }
        ),
        value_fields=frozenset(
            {
                "first_name",
                "last_name",
                "email",
                "preferred_name",
                "birth_date",
                "phone",
            }
        ),
    ),
    AuditEventType.EMPLOYEE_EMPLOYMENT_PROFILE_UPDATED: AuditMetadataPolicy(
        changed_fields=frozenset({"employment_start_date", "contract_type", "work_type"}),
        value_fields=frozenset({"employment_start_date", "contract_type", "work_type"}),
    ),
    AuditEventType.EMPLOYEE_ACCOUNT_LINK_CHANGED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "previous_membership_id",
                "new_membership_id",
                "link_status",
            }
        ),
        changed_fields=frozenset({"membership_id", "link_status"}),
    ),
    AuditEventType.EMPLOYEE_PROFILE_CHANGE_REQUEST_SUBMITTED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "request_id",
                "employee_id",
                "before_request_status",
                "after_request_status",
                "reason_code",
            }
        ),
        changed_fields=frozenset({"preferred_name", "phone", "birth_date"}),
    ),
    AuditEventType.EMPLOYEE_PROFILE_CHANGE_REQUEST_APPROVED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "request_id",
                "employee_id",
                "before_request_status",
                "after_request_status",
                "reason_code",
            }
        ),
        changed_fields=frozenset({"preferred_name", "phone", "birth_date"}),
    ),
    AuditEventType.EMPLOYEE_PROFILE_CHANGE_REQUEST_REJECTED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "request_id",
                "employee_id",
                "before_request_status",
                "after_request_status",
                "reason_code",
            }
        ),
        changed_fields=frozenset({"preferred_name", "phone", "birth_date"}),
    ),
    AuditEventType.EMPLOYEE_PROFILE_CHANGE_REQUEST_CANCELLED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "request_id",
                "employee_id",
                "before_request_status",
                "after_request_status",
                "reason_code",
            }
        ),
        changed_fields=frozenset({"preferred_name", "phone", "birth_date"}),
    ),
    AuditEventType.EMPLOYEE_ARCHIVED: AuditMetadataPolicy(
        changed_fields=frozenset({"archived_at"})
    ),
    AuditEventType.EMPLOYEE_ASSIGNMENT_CHANGED: AuditMetadataPolicy(
        changed_fields=frozenset(
            {
                "legal_entity_id",
                "branch_id",
                "department_id",
                "position_id",
                "manager_id",
                "effective_from",
                "effective_to",
            }
        )
    ),
    AuditEventType.REPORTING_LINE_CHANGED: AuditMetadataPolicy(
        changed_fields=frozenset({"manager_id"})
    ),
    AuditEventType.DOCUMENT_TYPE_CREATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"sensitivity"}),
        changed_fields=frozenset(
            {
                "code",
                "name",
                "description",
                "required",
                "employee_visible",
                "sensitivity",
                "expiry_mode",
                "allowed_mime_types",
                "allowed_extensions",
                "max_size_bytes",
            }
        ),
    ),
    AuditEventType.DOCUMENT_TYPE_UPDATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"sensitivity"}),
        changed_fields=frozenset(
            {
                "name",
                "description",
                "required",
                "employee_visible",
                "sensitivity",
                "expiry_mode",
                "allowed_mime_types",
                "allowed_extensions",
                "max_size_bytes",
            }
        ),
    ),
    AuditEventType.DOCUMENT_TYPE_ARCHIVED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_state", "after_state"}),
        changed_fields=frozenset({"archived_at"}),
    ),
    AuditEventType.DOCUMENT_TYPE_UNARCHIVED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_state", "after_state"}),
        changed_fields=frozenset({"archived_at"}),
    ),
    AuditEventType.EMPLOYEE_DOCUMENT_UPLOAD_INITIATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"after_state", "file_class", "sensitivity"}),
        changed_fields=frozenset({"processing_state"}),
    ),
    AuditEventType.EMPLOYEE_DOCUMENT_UPLOAD_FINALIZED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_state", "after_state", "file_class"}),
        changed_fields=frozenset({"processing_state", "finalized_at"}),
    ),
    AuditEventType.EMPLOYEE_DOCUMENT_SCAN_COMPLETED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {"before_state", "after_state", "scan_result", "scanner_provider"}
        ),
        changed_fields=frozenset({"processing_state", "scan_result", "scanned_at"}),
    ),
    AuditEventType.EMPLOYEE_DOCUMENT_UPDATED: AuditMetadataPolicy(
        changed_fields=frozenset(
            {"display_filename", "issued_on", "expires_on", "employee_visible"}
        )
    ),
    AuditEventType.EMPLOYEE_DOCUMENT_ARCHIVED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_state", "after_state"}),
        changed_fields=frozenset({"archived_at"}),
    ),
    AuditEventType.EMPLOYEE_DOCUMENT_UNARCHIVED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_state", "after_state"}),
        changed_fields=frozenset({"archived_at"}),
    ),
    AuditEventType.EMPLOYEE_DOCUMENT_VIEWED: AuditMetadataPolicy(
        metadata_keys=frozenset({"access_scope"})
    ),
    AuditEventType.EMPLOYEE_DOCUMENT_DOWNLOAD_URL_ISSUED: AuditMetadataPolicy(
        metadata_keys=frozenset({"access_scope"})
    ),
}


@dataclass(frozen=True, slots=True)
class RedactedAuditValues:
    changed_fields: list[str]
    before_data: dict[str, object]
    after_data: dict[str, object]
    metadata: dict[str, object]
    ip_address: str | None
    user_agent: str | None


def redact_audit_values(event: AuditEventDraft) -> RedactedAuditValues:
    policy = _POLICIES[event.event_type]
    changed_fields = sorted(
        {
            field_name
            for field_name in event.changed_fields
            if field_name in policy.changed_fields and not _is_forbidden_key(field_name)
        }
    )
    metadata: dict[str, object] = {}
    for key, raw_value in event.metadata.items():
        if (
            key not in policy.metadata_keys
            or _is_forbidden_key(key)
            or (value := _safe_metadata_value(key, raw_value)) is None
        ):
            continue
        metadata[key] = value
    return RedactedAuditValues(
        changed_fields=changed_fields,
        before_data=_redact_changed_values(
            event.before_values,
            policy=policy,
            changed_fields=frozenset(changed_fields),
        ),
        after_data=_redact_changed_values(
            event.after_values,
            policy=policy,
            changed_fields=frozenset(changed_fields),
        ),
        metadata=metadata,
        ip_address=redact_ip_address(event.context.ip_address),
        user_agent=redact_user_agent(event.context.user_agent),
    )


def redact_ip_address(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = ip_address(value)
    except ValueError:
        return None
    if parsed.version == 4:
        octets = str(parsed).split(".")
        return ".".join((*octets[:3], "0"))
    exploded = parsed.exploded.split(":")
    return ":".join((*exploded[:4], "0", "0", "0", "0"))


def redact_user_agent(value: str | None) -> str | None:
    if value is None:
        return None
    lowered = value.lower()
    for marker, family in (
        ("edg/", "Edge"),
        ("chrome/", "Chrome"),
        ("firefox/", "Firefox"),
        ("safari/", "Safari"),
        ("curl/", "curl"),
    ):
        if marker in lowered:
            return family
    return "Other"


def _safe_metadata_value(key: str, value: object) -> object | None:
    if isinstance(value, StrEnum):
        value = value.value
    if isinstance(value, UUID):
        value = str(value)
    if isinstance(value, bool):
        return value
    if type(value) is int:
        return value if 0 <= value <= 2_147_483_647 else None
    if isinstance(value, str):
        allowed_values = _METADATA_VALUE_SETS.get(key)
        if allowed_values is not None and value not in allowed_values:
            return None
        if key in {"before_role_codes", "after_role_codes"}:
            return None
        return value if len(value) <= 128 and _SAFE_VALUE.fullmatch(value) else None
    if isinstance(value, (list, tuple, frozenset)):
        if key not in {"before_role_codes", "after_role_codes"} or len(value) > 16:
            return None
        role_codes = sorted({str(item) for item in value})
        if not set(role_codes) <= _ROLE_CODES:
            return None
        return role_codes
    return None


_UNSAFE_VALUE = object()


def _redact_changed_values(
    candidates: Mapping[str, object],
    *,
    policy: AuditMetadataPolicy,
    changed_fields: frozenset[str],
) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key in sorted(changed_fields):
        if key not in policy.value_fields or key not in candidates or _is_forbidden_key(key):
            continue
        value = _safe_changed_value(candidates[key])
        if value is not _UNSAFE_VALUE:
            redacted[key] = value
    return redacted


def _safe_changed_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, StrEnum):
        value = value.value
    if isinstance(value, datetime):
        return _UNSAFE_VALUE
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        if not value or len(value) > 320 or not value.isprintable():
            return _UNSAFE_VALUE
        return value
    return _UNSAFE_VALUE


def _is_forbidden_key(key: str) -> bool:
    normalized = key.lower()
    return any(part in normalized for part in _FORBIDDEN_KEY_PARTS)


def safe_metadata_keys() -> Mapping[AuditEventType, frozenset[str]]:
    """Expose the immutable allowlist for focused security tests."""

    return {event_type: policy.metadata_keys for event_type, policy in _POLICIES.items()}


__all__ = [
    "RedactedAuditValues",
    "redact_audit_values",
    "redact_ip_address",
    "redact_user_agent",
    "safe_metadata_keys",
]
