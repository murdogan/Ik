"""Transactional guards for credential-derived authentication decisions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Identity, IdentityStatus, MembershipStatus, TenantMembership

_POSTGRES_GLOBAL_LOCK_FUNCTION = "lock_identity_credential"
_POSTGRES_TENANT_LOCK_FUNCTION = "lock_membership_identity_credential"


class IdentityCredentialLockService:
    """Revalidate and lock the credential row until the caller's transaction ends."""

    async def lock_global(
        self,
        session: AsyncSession,
        *,
        identity_id: UUID,
        verified_password_hash: str | None,
    ) -> bool:
        if verified_password_hash is None:
            return False
        if session.get_bind().dialect.name == "postgresql":
            return bool(
                await session.scalar(
                    text(
                        f"select public.{_POSTGRES_GLOBAL_LOCK_FUNCTION}("
                        ":identity_id, :verified_password_hash)"
                    ),
                    {
                        "identity_id": identity_id,
                        "verified_password_hash": verified_password_hash,
                    },
                )
            )
        identity = await session.scalar(
            select(Identity)
            .where(
                Identity.id == identity_id,
                Identity.status == IdentityStatus.ACTIVE.value,
                Identity.password_hash == verified_password_hash,
            )
            .with_for_update()
        )
        return identity is not None

    async def lock_tenant_membership(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        user_id: UUID,
        verified_password_hash: str | None,
    ) -> bool:
        if verified_password_hash is None:
            return False
        if session.get_bind().dialect.name == "postgresql":
            return bool(
                await session.scalar(
                    text(
                        f"select public.{_POSTGRES_TENANT_LOCK_FUNCTION}("
                        ":membership_id, :user_id, :verified_password_hash)"
                    ),
                    {
                        "membership_id": membership_id,
                        "user_id": user_id,
                        "verified_password_hash": verified_password_hash,
                    },
                )
            )
        identity = await session.scalar(
            select(Identity)
            .join(
                TenantMembership,
                and_(
                    TenantMembership.identity_id == Identity.id,
                    TenantMembership.tenant_id == tenant_id,
                ),
            )
            .where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.id == membership_id,
                TenantMembership.legacy_user_id == user_id,
                TenantMembership.status == MembershipStatus.ACTIVE.value,
                Identity.status == IdentityStatus.ACTIVE.value,
                Identity.password_hash == verified_password_hash,
            )
            .with_for_update()
        )
        return identity is not None


__all__ = ["IdentityCredentialLockService"]
