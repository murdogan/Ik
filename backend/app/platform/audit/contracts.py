"""Framework-neutral contracts for safe, append-only audit recording."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from app.platform.request_context import RequestContext


class AuditScopeType(StrEnum):
    PLATFORM = "platform"
    TENANT = "tenant"


class AuditActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"
    WORKER = "worker"
    PLATFORM_ADMIN = "platform_admin"
    SUPPORT_SESSION = "support_session"


class AuditCategory(StrEnum):
    PLATFORM_OPERATIONS = "platform_operations"
    TENANT_SECURITY = "tenant_security"
    TENANT_ADMIN = "tenant_admin"
    HR_OPERATIONS = "hr_operations"


class AuditSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AuditResult(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class AuditDataClassification(StrEnum):
    PLATFORM_METADATA = "platform_metadata"
    SECURITY_METADATA = "security_metadata"
    TENANT_ADMINISTRATION = "tenant_administration"
    HR_METADATA = "hr_metadata"


class AuditVisibilityClass(StrEnum):
    PLATFORM_OPS = "platform_ops"
    TENANT_SECURITY = "tenant_security"
    TENANT_ADMIN = "tenant_admin"
    HR_OPERATIONS = "hr_operations"
    AUDITOR_READONLY = "auditor_readonly"


class AuditEventType(StrEnum):
    LOGIN_SUCCEEDED = "auth.login.succeeded"
    LOGIN_FAILED = "auth.login.failed"
    PLATFORM_LOGIN_SUCCEEDED = "platform.auth.login.succeeded"
    PLATFORM_LOGIN_FAILED = "platform.auth.login.failed"
    PLATFORM_LOGIN_DENIED = "platform.auth.login.denied"
    ACTIVATION_COMPLETED = "auth.activation.completed"
    PASSWORD_RESET_REQUESTED = "auth.password_reset.requested"
    PASSWORD_RESET_COMPLETED = "auth.password_reset.completed"
    INVITATION_CREATED = "user.invitation.created"
    ROLES_REPLACED = "user.roles.replaced"
    USER_STATUS_CHANGED = "user.status.changed"
    SESSION_STARTED = "session.started"
    SESSION_REFRESHED = "session.refreshed"
    SESSION_REUSE_DETECTED = "session.reuse_detected"
    SESSION_REVOKED = "session.revoked"
    PLATFORM_SESSION_STARTED = "platform.session.started"
    PLATFORM_SESSION_REFRESHED = "platform.session.refreshed"
    PLATFORM_SESSION_REUSE_DETECTED = "platform.session.reuse_detected"
    PLATFORM_SESSION_REVOKED = "platform.session.revoked"
    PLATFORM_TENANT_CREATED = "platform.tenant.created"
    PLATFORM_TENANT_STATUS_CHANGED = "platform.tenant.status_changed"
    PLATFORM_TENANT_SETTING_CHANGED = "platform.tenant.setting_changed"
    PLATFORM_FEATURE_FLAG_CHANGED = "platform.feature_flag.changed"
    TENANT_SETTING_CHANGED = "tenant.setting.changed"
    LEGAL_ENTITY_CREATED = "legal_entity.created"
    LEGAL_ENTITY_UPDATED = "legal_entity.updated"
    BRANCH_CREATED = "branch.created"
    BRANCH_UPDATED = "branch.updated"
    BRANCH_ARCHIVED = "branch.archived"
    DEPARTMENT_CREATED = "department.created"
    DEPARTMENT_UPDATED = "department.updated"
    DEPARTMENT_ARCHIVED = "department.archived"
    POSITION_CREATED = "position.created"
    POSITION_UPDATED = "position.updated"
    POSITION_ARCHIVED = "position.archived"
    EMPLOYEE_CREATED = "employee.created"
    EMPLOYEE_UPDATED = "employee.updated"
    EMPLOYEE_ARCHIVED = "employee.archived"
    EMPLOYEE_PERSONAL_PROFILE_UPDATED = "employee.personal_profile.updated"
    EMPLOYEE_EMPLOYMENT_PROFILE_UPDATED = "employee.employment_profile.updated"
    EMPLOYEE_ACCOUNT_LINK_CHANGED = "employee.account_link.changed"
    EMPLOYEE_PROFILE_CHANGE_REQUEST_SUBMITTED = "employee.profile_change_request.submitted"
    EMPLOYEE_PROFILE_CHANGE_REQUEST_APPROVED = "employee.profile_change_request.approved"
    EMPLOYEE_PROFILE_CHANGE_REQUEST_REJECTED = "employee.profile_change_request.rejected"
    EMPLOYEE_PROFILE_CHANGE_REQUEST_CANCELLED = "employee.profile_change_request.cancelled"
    EMPLOYEE_ASSIGNMENT_CHANGED = "employee.assignment.changed"
    REPORTING_LINE_CHANGED = "reporting_line.changed"


@dataclass(frozen=True, slots=True)
class AuditContext:
    """Only request metadata safe to cross the audit boundary."""

    request_id: str
    trace_id: str
    ip_address: str | None = None
    user_agent: str | None = None

    @classmethod
    def from_request_context(cls, context: RequestContext) -> AuditContext:
        return cls(request_id=context.request_id, trace_id=context.trace_id)

    @classmethod
    def internal(cls) -> AuditContext:
        identifier = uuid4().hex
        return cls(request_id=f"internal-{identifier}", trace_id=identifier)


@dataclass(frozen=True, slots=True)
class AuditEventDraft:
    """Closed-shape command passed to a same-session persistence adapter.

    Before/after mappings are accepted only as candidates for event-specific redaction. The
    persistence adapter intersects them with the event's explicit value allowlist and the final
    changed-field set; callers must never pass generic request payloads or domain snapshots.
    """

    scope_type: AuditScopeType
    tenant_id: UUID | None
    actor_type: AuditActorType
    event_type: AuditEventType
    category: AuditCategory
    resource_type: str | None
    resource_id: UUID | None
    action: str
    context: AuditContext
    actor_user_id: UUID | None = None
    impersonator_user_id: UUID | None = None
    session_id: UUID | None = None
    severity: AuditSeverity = AuditSeverity.INFO
    result: AuditResult = AuditResult.SUCCESS
    changed_fields: tuple[str, ...] = ()
    before_values: Mapping[str, object] = field(default_factory=dict)
    after_values: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)
    data_classification: AuditDataClassification = AuditDataClassification.SECURITY_METADATA
    visibility_class: AuditVisibilityClass = AuditVisibilityClass.TENANT_SECURITY
    id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.scope_type is AuditScopeType.TENANT:
            if not isinstance(self.tenant_id, UUID) or self.tenant_id.int == 0:
                raise ValueError("Tenant audit events require a non-zero tenant ID")
        elif self.tenant_id is not None:
            raise ValueError("Platform audit events cannot carry a tenant ID")
        for field_name in (
            "id",
            "actor_user_id",
            "impersonator_user_id",
            "resource_id",
            "session_id",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, UUID) or value.int == 0):
                raise ValueError(f"{field_name} must be a non-zero UUID")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("Audit occurred_at must include a timezone")


class AuditRecorder(Protocol):
    async def record(self, event: AuditEventDraft, /) -> None: ...


__all__ = [
    "AuditActorType",
    "AuditCategory",
    "AuditContext",
    "AuditDataClassification",
    "AuditEventDraft",
    "AuditEventType",
    "AuditRecorder",
    "AuditResult",
    "AuditScopeType",
    "AuditSeverity",
    "AuditVisibilityClass",
]
