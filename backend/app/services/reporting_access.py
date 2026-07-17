"""Fail-closed Phase 8 feature, scope, and report-field authorization."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reporting import ReportScope, ReportType
from app.models.tenant import Tenant, TenantFeatureFlag
from app.modules.core.domain.feature_flags import FeatureFlagKey, default_feature_flag_enabled
from app.modules.core.domain.tenant import TenantAccessMode, TenantStatus, access_mode_for_status
from app.platform.errors.application import ApplicationError
from app.schemas.reporting import (
    DocumentReportField,
    EmployeeReportField,
    LeaveReportField,
)

REPORT_READ_TENANT_PERMISSION = "report:read:tenant"
REPORT_READ_TEAM_PERMISSION = "report:read:team"
REPORT_EXPORT_TENANT_PERMISSION = "report:export:tenant"
REPORT_EXPORT_TEAM_PERMISSION = "report:export:team"
REPORT_WORK_EMAIL_PERMISSION = "report_field:read:work_email"
EMPLOYEE_IMPORT_PERMISSION = "employee_import:manage:tenant"


class ReportingAccessDeniedError(ApplicationError):
    pass


class ReportingFeatureUnavailableError(ApplicationError):
    pass


class ReportingNotFoundError(ApplicationError):
    pass


class ReportingValidationError(ApplicationError, ValueError):
    pass


class ReportingConflictError(ApplicationError):
    pass


class ReportingStorageUnavailableError(ApplicationError):
    pass


@dataclass(frozen=True, slots=True)
class ReportAuthorization:
    scope: ReportScope
    scope_user_id: UUID | None


def resolve_report_authorization(
    *,
    permissions: tuple[str, ...],
    actor_id: UUID,
    require_export: bool,
) -> ReportAuthorization:
    granted = frozenset(permissions)
    tenant_allowed = REPORT_READ_TENANT_PERMISSION in granted and (
        not require_export or REPORT_EXPORT_TENANT_PERMISSION in granted
    )
    if tenant_allowed:
        return ReportAuthorization(scope=ReportScope.TENANT, scope_user_id=None)
    team_allowed = REPORT_READ_TEAM_PERMISSION in granted and (
        not require_export or REPORT_EXPORT_TEAM_PERMISSION in granted
    )
    if team_allowed:
        return ReportAuthorization(scope=ReportScope.TEAM, scope_user_id=actor_id)
    raise ReportingAccessDeniedError()


def reduce_report_authorization(
    *,
    request_scope: ReportScope,
    request_scope_user_id: UUID | None,
    current: ReportAuthorization,
) -> ReportAuthorization:
    """Intersect a request snapshot with current authority without ever expanding it."""

    if request_scope is ReportScope.TEAM:
        if request_scope_user_id is None:
            raise ReportingAccessDeniedError()
        if current.scope is ReportScope.TEAM and current.scope_user_id != request_scope_user_id:
            raise ReportingAccessDeniedError()
        return ReportAuthorization(
            scope=ReportScope.TEAM,
            scope_user_id=request_scope_user_id,
        )
    if current.scope is ReportScope.TEAM:
        return current
    return ReportAuthorization(scope=ReportScope.TENANT, scope_user_id=None)


def authorization_covers_artifact(
    *,
    current: ReportAuthorization,
    artifact_scope: ReportScope,
    artifact_scope_user_id: UUID | None,
) -> bool:
    if current.scope is ReportScope.TENANT:
        return True
    return (
        artifact_scope is ReportScope.TEAM
        and artifact_scope_user_id is not None
        and artifact_scope_user_id == current.scope_user_id
    )


def allowed_report_fields(
    report_type: ReportType,
    permissions: tuple[str, ...],
) -> tuple[str, ...]:
    if report_type is ReportType.EMPLOYEES:
        fields = [field.value for field in EmployeeReportField]
        if REPORT_WORK_EMAIL_PERMISSION not in permissions:
            fields.remove(EmployeeReportField.WORK_EMAIL.value)
        return tuple(fields)
    if report_type is ReportType.LEAVES:
        return tuple(field.value for field in LeaveReportField)
    if report_type is ReportType.MISSING_DOCUMENTS:
        return tuple(field.value for field in DocumentReportField)
    raise ReportingValidationError()


def enforce_requested_fields(
    *,
    report_type: ReportType,
    requested_fields: list[str] | tuple[str, ...],
    permissions: tuple[str, ...],
) -> tuple[str, ...]:
    allowed = frozenset(allowed_report_fields(report_type, permissions))
    requested = tuple(requested_fields)
    if not requested or len(set(requested)) != len(requested):
        raise ReportingValidationError()
    if not set(requested) <= allowed:
        raise ReportingAccessDeniedError()
    return requested


def reduce_requested_fields(
    *,
    report_type: ReportType,
    request_fields: list[str] | tuple[str, ...],
    permissions: tuple[str, ...],
) -> tuple[str, ...]:
    allowed = frozenset(allowed_report_fields(report_type, permissions))
    return tuple(field for field in request_fields if field in allowed)


async def require_reporting_feature(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    write: bool = False,
) -> None:
    tenant_statement = select(Tenant).where(Tenant.id == tenant_id)
    if write:
        tenant_statement = tenant_statement.with_for_update()
    tenant = await session.scalar(tenant_statement)
    if tenant is None:
        raise ReportingNotFoundError()
    access_mode = access_mode_for_status(TenantStatus(tenant.status))
    if access_mode in {TenantAccessMode.PLATFORM_ONLY, TenantAccessMode.DENIED}:
        raise ReportingFeatureUnavailableError()
    if write and access_mode is TenantAccessMode.READ_ONLY:
        raise ReportingConflictError()
    override = await session.scalar(
        select(TenantFeatureFlag.enabled).where(
            TenantFeatureFlag.tenant_id == tenant_id,
            TenantFeatureFlag.key == FeatureFlagKey.REPORTING.value,
        )
    )
    enabled = (
        default_feature_flag_enabled(FeatureFlagKey.REPORTING)
        if override is None
        else override
    )
    if not enabled:
        raise ReportingFeatureUnavailableError()


__all__ = [
    "EMPLOYEE_IMPORT_PERMISSION",
    "REPORT_EXPORT_TEAM_PERMISSION",
    "REPORT_EXPORT_TENANT_PERMISSION",
    "REPORT_READ_TEAM_PERMISSION",
    "REPORT_READ_TENANT_PERMISSION",
    "REPORT_WORK_EMAIL_PERMISSION",
    "ReportAuthorization",
    "ReportingAccessDeniedError",
    "ReportingConflictError",
    "ReportingFeatureUnavailableError",
    "ReportingNotFoundError",
    "ReportingStorageUnavailableError",
    "ReportingValidationError",
    "allowed_report_fields",
    "authorization_covers_artifact",
    "enforce_requested_fields",
    "reduce_report_authorization",
    "reduce_requested_fields",
    "require_reporting_feature",
    "resolve_report_authorization",
]
