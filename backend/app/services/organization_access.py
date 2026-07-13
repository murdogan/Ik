"""Shared tenant, feature, and permission guards for organization services."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant, TenantFeatureFlag
from app.modules.core.domain.feature_flags import (
    FeatureFlagKey,
    default_feature_flag_enabled,
)
from app.modules.core.domain.tenant import (
    TenantAccessMode,
    TenantStatus,
    access_mode_for_status,
)
from app.platform.authorization import DenyByDefaultPolicy
from app.platform.errors.application import ApplicationError
from app.platform.request_context import RequestContext
from app.services.tenant_service import (
    TenantClosedError,
    TenantNotFoundError,
    TenantNotReadyError,
    TenantReadOnlyError,
)

ORGANIZATION_READ_PERMISSION = "organization:read:tenant"
ORGANIZATION_UPDATE_PERMISSION = "organization:update:tenant"

_authorization_policy = DenyByDefaultPolicy()


class OrganizationAccessDeniedError(ApplicationError):
    pass


class OrganizationFeatureUnavailableError(ApplicationError):
    pass


def organization_scope_from_context(request_context: RequestContext) -> tuple[UUID, UUID]:
    tenant_id = request_context.require_tenant().tenant_id
    actor_id = request_context.actor_id
    if actor_id is None:
        raise OrganizationAccessDeniedError()
    return tenant_id, actor_id


def require_organization_permission(
    granted_permissions: tuple[str, ...],
    permission: str,
) -> None:
    if not _authorization_policy.allows(permission, granted_permissions):
        raise OrganizationAccessDeniedError()


async def require_organization_tenant_access(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    write: bool,
) -> None:
    tenant_statement = select(Tenant).where(Tenant.id == tenant_id)
    if write:
        # This tenant row is the application-level hierarchy write lock as well as the lifecycle
        # lock. Every organization command takes it before inspecting mutable tenant-owned state.
        tenant_statement = tenant_statement.with_for_update()
    tenant = await session.scalar(tenant_statement)
    if tenant is None:
        raise TenantNotFoundError()
    access_mode = access_mode_for_status(TenantStatus(tenant.status))
    if access_mode is TenantAccessMode.PLATFORM_ONLY:
        raise TenantNotReadyError()
    if access_mode is TenantAccessMode.DENIED:
        raise TenantClosedError()
    if write and access_mode is TenantAccessMode.READ_ONLY:
        raise TenantReadOnlyError()

    organization_enabled = await session.scalar(
        select(TenantFeatureFlag.enabled).where(
            TenantFeatureFlag.tenant_id == tenant_id,
            TenantFeatureFlag.key == FeatureFlagKey.ORGANIZATION.value,
        )
    )
    if organization_enabled is None:
        organization_enabled = default_feature_flag_enabled(FeatureFlagKey.ORGANIZATION)
    if not organization_enabled:
        raise OrganizationFeatureUnavailableError()


__all__ = [
    "ORGANIZATION_READ_PERMISSION",
    "ORGANIZATION_UPDATE_PERMISSION",
    "OrganizationAccessDeniedError",
    "OrganizationFeatureUnavailableError",
    "organization_scope_from_context",
    "require_organization_permission",
    "require_organization_tenant_access",
]
