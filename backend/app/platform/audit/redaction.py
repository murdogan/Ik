"""Event-specific audit metadata allowlisting and identifier redaction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from ipaddress import ip_address
from re import compile as compile_regex
from uuid import UUID

from app.platform.audit.contracts import AuditEventDraft, AuditEventType

_SAFE_VALUE = compile_regex(r"[A-Za-z0-9](?:[A-Za-z0-9_.:-]{0,126}[A-Za-z0-9])?")
_SHA256_VALUE = compile_regex(r"[0-9a-f]{64}")
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
_FORBIDDEN_EXACT_KEYS = frozenset({"reason", "decision_note", "employee_note"})
_SAFE_KEY_EXCEPTIONS = frozenset({"document_required", "notice_content_hash"})


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
        "pending",
        "draft",
        "published",
        "approved",
        "rejected",
        "resolved",
        "cancelled",
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
    "before_request_status": frozenset(
        {
            "none",
            "submitted",
            "pending",
            "approved",
            "rejected",
            "resolved",
            "cancelled",
        }
    ),
    "after_request_status": frozenset(
        {"submitted", "pending", "approved", "rejected", "resolved", "cancelled"}
    ),
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
            "inactive",
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
            "inactive",
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
    "channel": frozenset({"email"}),
    "delivery_error_code": frozenset(
        {
            "provider_unavailable",
            "provider_rejected",
            "recipient_unavailable",
            "capture_failed",
        }
    ),
    "report_type": frozenset({"employees", "leaves", "missing_documents"}),
    "export_format": frozenset({"csv", "xlsx"}),
    "report_scope": frozenset({"tenant", "team"}),
    "file_format": frozenset({"csv", "xlsx"}),
    "template_version": frozenset({"1"}),
    "failure_code": frozenset(
        {
            "authorization_revoked",
            "cancelled",
            "file_too_large",
            "infected_file",
            "invalid_file",
            "row_limit_exceeded",
            "scanner_unavailable",
            "storage_unavailable",
            "worker_failure",
        }
    ),
    "notice_kind": frozenset({"employee"}),
    "data_category": frozenset(
        {
            "employee_records",
            "employee_documents",
            "leave_requests",
            "audit_events",
        }
    ),
    "retention_action": frozenset({"review", "delete", "anonymize"}),
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
    AuditEventType.LEAVE_TYPE_CREATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"leave_type_id", "after_status", "version"}),
        changed_fields=frozenset({"code", "name", "description", "is_active"}),
    ),
    AuditEventType.LEAVE_TYPE_UPDATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"leave_type_id", "before_status", "after_status", "version"}),
        changed_fields=frozenset({"name", "description", "is_active"}),
    ),
    AuditEventType.LEAVE_TYPE_DEACTIVATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"leave_type_id", "before_status", "after_status", "version"}),
        changed_fields=frozenset({"is_active"}),
    ),
    AuditEventType.HOLIDAY_CALENDAR_CREATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"calendar_id", "after_status", "version"}),
        changed_fields=frozenset({"name", "is_default", "is_active", "non_working_weekdays"}),
    ),
    AuditEventType.HOLIDAY_CALENDAR_UPDATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"calendar_id", "before_status", "after_status", "version"}),
        changed_fields=frozenset({"name", "is_default", "is_active", "non_working_weekdays"}),
    ),
    AuditEventType.HOLIDAY_ENTRY_CREATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"calendar_id", "holiday_entry_id", "after_status", "version"}),
        changed_fields=frozenset({"holiday_date", "name", "is_active"}),
    ),
    AuditEventType.HOLIDAY_ENTRY_UPDATED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "calendar_id",
                "holiday_entry_id",
                "before_status",
                "after_status",
                "version",
            }
        ),
        changed_fields=frozenset({"name", "is_active"}),
    ),
    AuditEventType.HOLIDAY_ENTRY_DEACTIVATED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "calendar_id",
                "holiday_entry_id",
                "before_status",
                "after_status",
                "version",
            }
        ),
        changed_fields=frozenset({"is_active"}),
    ),
    AuditEventType.LEAVE_POLICY_VERSION_CREATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"policy_id", "leave_type_id", "policy_version"}),
        changed_fields=frozenset(
            {
                "leave_type_id",
                "version",
                "effective_from",
                "effective_to",
                "paid",
                "document_required",
                "negative_balance_allowed",
                "accrual_enabled",
                "accrual_days_per_month",
                "carryover_enabled",
                "carryover_limit_days",
            }
        ),
    ),
    AuditEventType.LEAVE_BALANCE_ADJUSTED: AuditMetadataPolicy(
        metadata_keys=frozenset({"employee_id", "leave_type_id", "period_year", "amount_days"}),
        changed_fields=frozenset({"adjusted_days", "available_days"}),
    ),
    AuditEventType.LEAVE_REQUEST_SUBMITTED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "request_id",
                "employee_id",
                "leave_type_id",
                "policy_id",
                "before_status",
                "after_status",
                "before_request_status",
                "after_request_status",
                "counted_days",
                "version",
            }
        ),
        changed_fields=frozenset({"status", "counted_days", "version"}),
    ),
    AuditEventType.LEAVE_REQUEST_APPROVED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "request_id",
                "employee_id",
                "leave_type_id",
                "before_status",
                "after_status",
                "before_request_status",
                "after_request_status",
                "counted_days",
                "version",
            }
        ),
        changed_fields=frozenset({"status", "counted_days", "version"}),
    ),
    AuditEventType.LEAVE_REQUEST_REJECTED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "request_id",
                "employee_id",
                "leave_type_id",
                "before_status",
                "after_status",
                "before_request_status",
                "after_request_status",
                "counted_days",
                "version",
            }
        ),
        changed_fields=frozenset({"status", "counted_days", "version"}),
    ),
    AuditEventType.LEAVE_REQUEST_CANCELLED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "request_id",
                "employee_id",
                "leave_type_id",
                "before_status",
                "after_status",
                "before_request_status",
                "after_request_status",
                "counted_days",
                "version",
            }
        ),
        changed_fields=frozenset({"status", "counted_days", "version"}),
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
    AuditEventType.DOCUMENT_REQUEST_SUBMITTED: AuditMetadataPolicy(
        metadata_keys=frozenset({"request_id", "employee_id", "after_request_status"}),
        changed_fields=frozenset({"status", "version"}),
    ),
    AuditEventType.DOCUMENT_REQUEST_RESOLVED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {"request_id", "employee_id", "before_request_status", "after_request_status"}
        ),
        changed_fields=frozenset({"status", "version"}),
    ),
    AuditEventType.DOCUMENT_REQUEST_REJECTED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {"request_id", "employee_id", "before_request_status", "after_request_status"}
        ),
        changed_fields=frozenset({"status", "version"}),
    ),
    AuditEventType.ANNOUNCEMENT_CREATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"after_status", "version"}),
        changed_fields=frozenset(
            {"title", "text_changed", "is_critical", "targeting", "status", "version"}
        ),
    ),
    AuditEventType.ANNOUNCEMENT_UPDATED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_status", "after_status", "version"}),
        changed_fields=frozenset(
            {"title", "text_changed", "is_critical", "targeting", "version"}
        ),
    ),
    AuditEventType.ANNOUNCEMENT_PUBLISHED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_status", "after_status", "recipient_count", "version"}),
        changed_fields=frozenset({"status", "published_at", "version"}),
    ),
    AuditEventType.ANNOUNCEMENT_ARCHIVED: AuditMetadataPolicy(
        metadata_keys=frozenset({"before_status", "after_status", "version"}),
        changed_fields=frozenset({"status", "archived_at", "version"}),
    ),
    AuditEventType.ANNOUNCEMENT_ACKNOWLEDGED: AuditMetadataPolicy(
        metadata_keys=frozenset({"after_status", "version"}),
        changed_fields=frozenset({"acknowledged_at", "version"}),
    ),
    AuditEventType.PRIVACY_NOTICE_PUBLISHED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {"notice_kind", "notice_version", "notice_content_hash"}
        ),
        changed_fields=frozenset({"status", "published_at", "revision"}),
    ),
    AuditEventType.PRIVACY_NOTICE_ACKNOWLEDGED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "notice_kind",
                "notice_version",
                "notice_content_hash",
                "membership_id",
            }
        ),
        changed_fields=frozenset({"acknowledged_at"}),
    ),
    AuditEventType.PRIVACY_CONSENT_GRANTED: AuditMetadataPolicy(
        metadata_keys=frozenset({"membership_id", "purpose_id", "purpose_version"}),
        changed_fields=frozenset({"granted", "version"}),
    ),
    AuditEventType.PRIVACY_CONSENT_WITHDRAWN: AuditMetadataPolicy(
        metadata_keys=frozenset({"membership_id", "purpose_id", "purpose_version"}),
        changed_fields=frozenset({"granted", "version"}),
    ),
    AuditEventType.RETENTION_POLICY_MUTATED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {"data_category", "retention_action", "policy_version"}
        ),
        changed_fields=frozenset(
            {
                "data_category",
                "legal_basis_note",
                "retention_days",
                "anchor",
                "action",
                "status",
                "version",
            }
        ),
    ),
    AuditEventType.RETENTION_DRY_RUN: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {"data_category", "retention_action", "policy_version", "count"}
        )
    ),
    AuditEventType.NOTIFICATION_DELIVERY_FAILED: AuditMetadataPolicy(
        metadata_keys=frozenset({"channel", "delivery_error_code", "attempt_count"}),
        changed_fields=frozenset({"status", "attempt_count"}),
    ),
    AuditEventType.REPORT_EXPORT_REQUESTED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {"report_type", "export_format", "report_scope", "field_count", "field_classifications"}
        ),
        changed_fields=frozenset({"status"}),
    ),
    AuditEventType.REPORT_EXPORT_COMPLETED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {
                "report_type",
                "export_format",
                "report_scope",
                "row_count",
                "field_count",
                "field_classifications",
            }
        ),
        changed_fields=frozenset({"status"}),
    ),
    AuditEventType.REPORT_EXPORT_FAILED: AuditMetadataPolicy(
        metadata_keys=frozenset({"report_type", "export_format", "failure_code", "attempt_count"}),
        changed_fields=frozenset({"status", "attempt_count"}),
    ),
    AuditEventType.REPORT_EXPORT_CANCELLED: AuditMetadataPolicy(
        metadata_keys=frozenset({"report_type", "export_format"}),
        changed_fields=frozenset({"status"}),
    ),
    AuditEventType.REPORT_EXPORT_EXPIRED: AuditMetadataPolicy(
        metadata_keys=frozenset({"report_type", "export_format", "row_count"}),
        changed_fields=frozenset({"status"}),
    ),
    AuditEventType.REPORT_EXPORT_DOWNLOAD_INTENT_ISSUED: AuditMetadataPolicy(
        metadata_keys=frozenset({"report_type", "export_format", "download_intent_count"})
    ),
    AuditEventType.EMPLOYEE_IMPORT_UPLOADED: AuditMetadataPolicy(
        metadata_keys=frozenset({"file_format", "template_version", "size_bytes"}),
        changed_fields=frozenset({"status"}),
    ),
    AuditEventType.EMPLOYEE_IMPORT_VALIDATED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {"file_format", "template_version", "row_count", "error_count", "warning_count"}
        ),
        changed_fields=frozenset({"status"}),
    ),
    AuditEventType.EMPLOYEE_IMPORT_FAILED: AuditMetadataPolicy(
        metadata_keys=frozenset(
            {"file_format", "template_version", "failure_code", "attempt_count"}
        ),
        changed_fields=frozenset({"status", "attempt_count"}),
    ),
    AuditEventType.EMPLOYEE_IMPORT_COMMITTED: AuditMetadataPolicy(
        metadata_keys=frozenset({"file_format", "template_version", "row_count"}),
        changed_fields=frozenset({"status"}),
    ),
    AuditEventType.EMPLOYEE_IMPORT_SOURCE_EXPIRED: AuditMetadataPolicy(
        metadata_keys=frozenset({"file_format", "template_version", "row_count"}),
        changed_fields=frozenset({"source_deleted_at", "status"}),
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
    if isinstance(value, Decimal):
        if not value.is_finite() or abs(value) > Decimal("2147483647"):
            return None
        formatted = format(value, "f")
        return formatted if len(formatted) <= 128 else None
    if type(value) is int:
        return value if 0 <= value <= 2_147_483_647 else None
    if isinstance(value, str):
        if key == "notice_content_hash":
            return value if _SHA256_VALUE.fullmatch(value) is not None else None
        allowed_values = _METADATA_VALUE_SETS.get(key)
        if allowed_values is not None and value not in allowed_values:
            return None
        if key in {"before_role_codes", "after_role_codes"}:
            return None
        return value if len(value) <= 128 and _SAFE_VALUE.fullmatch(value) else None
    if isinstance(value, (list, tuple, frozenset)):
        if key == "field_classifications":
            classifications = sorted({str(item) for item in value})
            if len(classifications) > 8 or not set(classifications) <= {
                "hr_metadata",
                "work_contact",
                "work_safe",
            }:
                return None
            return classifications
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
    if normalized in _SAFE_KEY_EXCEPTIONS:
        return False
    return normalized in _FORBIDDEN_EXACT_KEYS or any(
        part in normalized for part in _FORBIDDEN_KEY_PARTS
    )


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
