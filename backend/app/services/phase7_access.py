"""Shared fail-closed feature and public-safe Phase 7 application errors."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import TenantFeatureFlag
from app.modules.core.domain.feature_flags import FeatureFlagKey, default_feature_flag_enabled
from app.platform.errors.application import ApplicationError


class Phase7AccessDeniedError(ApplicationError):
    pass


class Phase7NotFoundError(ApplicationError):
    pass


class Phase7ValidationError(ApplicationError, ValueError):
    pass


class Phase7ConflictError(ApplicationError):
    pass


class Phase7VersionConflictError(Phase7ConflictError):
    pass


class Phase7FeatureUnavailableError(ApplicationError):
    pass


async def require_phase7_feature(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    feature: FeatureFlagKey,
) -> None:
    enabled = await session.scalar(
        select(TenantFeatureFlag.enabled).where(
            TenantFeatureFlag.tenant_id == tenant_id,
            TenantFeatureFlag.key == feature.value,
        )
    )
    effective = default_feature_flag_enabled(feature) if enabled is None else enabled
    if not effective:
        raise Phase7FeatureUnavailableError


__all__ = [
    "Phase7AccessDeniedError",
    "Phase7ConflictError",
    "Phase7FeatureUnavailableError",
    "Phase7NotFoundError",
    "Phase7ValidationError",
    "Phase7VersionConflictError",
    "require_phase7_feature",
]
