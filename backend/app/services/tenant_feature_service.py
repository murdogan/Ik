"""Tenant-aware feature rollout queries and platform commands."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant, TenantFeatureFlag
from app.modules.core.domain.feature_flags import (
    FeatureFlagKey,
    default_feature_flag_enabled,
    is_feature_flag_override,
)
from app.modules.core.domain.tenant import TenantStatus
from app.schemas.tenant import TenantFeaturesUpdate
from app.services.tenant_service import (
    TenantClosedError,
    TenantLifecycleConflictError,
    TenantNotFoundError,
    TenantNotReadyError,
)


@dataclass(frozen=True, slots=True)
class TenantFeatureSnapshot:
    key: FeatureFlagKey
    enabled: bool
    source: str


@dataclass(frozen=True, slots=True)
class TenantFeatureChange:
    key: FeatureFlagKey
    previous_enabled: bool
    enabled: bool


@dataclass(frozen=True, slots=True)
class TenantFeaturesMutation:
    features: tuple[TenantFeatureSnapshot, ...]
    changes: tuple[TenantFeatureChange, ...]


class TenantFeatureService:
    """Resolve effective flags from one global catalog plus tenant-scoped overrides."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_tenant_features(
        self,
        tenant_id: UUID,
        *,
        enforce_tenant_lifecycle: bool,
    ) -> tuple[TenantFeatureSnapshot, ...]:
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None:
            raise TenantNotFoundError
        if enforce_tenant_lifecycle:
            _ensure_tenant_feature_read_access(TenantStatus(tenant.status))
        overrides = await self._override_map(tenant_id)
        return _effective_features(overrides)

    async def update_tenant_features(
        self,
        tenant_id: UUID,
        payload: TenantFeaturesUpdate,
    ) -> TenantFeaturesMutation:
        tenant = await self.session.scalar(
            select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        )
        if tenant is None:
            raise TenantNotFoundError
        status = TenantStatus(tenant.status)
        if status is TenantStatus.CLOSED:
            raise TenantLifecycleConflictError("Closed tenants are immutable")
        if status is TenantStatus.OFFBOARDING:
            raise TenantLifecycleConflictError(
                "Offboarding tenants can only transition to closed"
            )

        existing_rows = list(
            await self.session.scalars(
                select(TenantFeatureFlag)
                .where(TenantFeatureFlag.tenant_id == tenant_id)
                .with_for_update()
            )
        )
        overrides = {
            FeatureFlagKey(row.key): row
            for row in existing_rows
        }
        changes: list[TenantFeatureChange] = []
        for update in payload.features:
            existing = overrides.get(update.key)
            previous_enabled = (
                existing.enabled
                if existing is not None
                else default_feature_flag_enabled(update.key)
            )
            if previous_enabled is update.enabled:
                continue
            if existing is None:
                existing = TenantFeatureFlag(
                    tenant_id=tenant_id,
                    key=update.key.value,
                    enabled=update.enabled,
                )
                self.session.add(existing)
                overrides[update.key] = existing
            else:
                existing.enabled = update.enabled
            changes.append(
                TenantFeatureChange(
                    key=update.key,
                    previous_enabled=previous_enabled,
                    enabled=update.enabled,
                )
            )

        await self.session.flush()
        return TenantFeaturesMutation(
            features=_effective_features(overrides),
            changes=tuple(changes),
        )

    async def _override_map(
        self,
        tenant_id: UUID,
    ) -> dict[FeatureFlagKey, TenantFeatureFlag]:
        rows = await self.session.scalars(
            select(TenantFeatureFlag).where(TenantFeatureFlag.tenant_id == tenant_id)
        )
        return {FeatureFlagKey(row.key): row for row in rows}


def _effective_features(
    overrides: dict[FeatureFlagKey, TenantFeatureFlag],
) -> tuple[TenantFeatureSnapshot, ...]:
    features: list[TenantFeatureSnapshot] = []
    for key in FeatureFlagKey:
        enabled = (
            overrides[key].enabled
            if key in overrides
            else default_feature_flag_enabled(key)
        )
        features.append(
            TenantFeatureSnapshot(
                key=key,
                enabled=enabled,
                source=(
                    "override"
                    if is_feature_flag_override(key, enabled)
                    else "default"
                ),
            )
        )
    return tuple(features)


def _ensure_tenant_feature_read_access(status: TenantStatus) -> None:
    if status is TenantStatus.PROVISIONING:
        raise TenantNotReadyError
    if status is TenantStatus.CLOSED:
        raise TenantClosedError


__all__ = [
    "TenantFeatureChange",
    "TenantFeatureService",
    "TenantFeatureSnapshot",
    "TenantFeaturesMutation",
]
