"""Expand-contract synchronization from legacy users into P3 identity projections."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.authorization import UserRole
from app.models.identity import (
    Identity,
    IdentityStatus,
    MembershipRole,
    TenantMembership,
)
from app.models.user import User, UserStatus
from app.platform.db import sqlstate_from_error

_POSTGRES_SYNC_FUNCTION = "sync_current_tenant_identity_membership"
_IDENTITY_ACTIVATION_CONFLICT_SQLSTATE = "WF001"


class IdentityProjectionConflictError(RuntimeError):
    """The canonical credential changed before activation projection committed."""


async def sync_identity_membership_projection(
    session: AsyncSession,
    user: User,
    *,
    require_pending_identity: bool = False,
) -> None:
    """Synchronize one current-tenant user without granting tenant code global reads."""

    if session.get_bind().dialect.name == "postgresql":
        try:
            await session.execute(
                text(
                    f"select public.{_POSTGRES_SYNC_FUNCTION}("
                    ":user_id, :require_pending_identity)"
                ),
                {
                    "user_id": user.id,
                    "require_pending_identity": require_pending_identity,
                },
            )
        except DBAPIError as exc:
            if (
                require_pending_identity
                and sqlstate_from_error(exc) == _IDENTITY_ACTIVATION_CONFLICT_SQLSTATE
            ):
                raise IdentityProjectionConflictError() from exc
            raise
        return

    identity = await session.scalar(
        select(Identity).where(
            Identity.email_normalized == user.email.strip().lower()
        )
    )
    if identity is None:
        identity = Identity(
            id=user.id,
            email=user.email,
            status=(
                IdentityStatus.PENDING.value
                if user.status == UserStatus.INVITED.value
                else user.status
            ),
            password_hash=user.password_hash,
        )
        session.add(identity)
        await session.flush()
    elif (
        require_pending_identity
        and user.status == UserStatus.ACTIVE.value
        and identity.status != IdentityStatus.PENDING.value
    ):
        raise IdentityProjectionConflictError()
    elif (
        identity.status == IdentityStatus.PENDING.value
        and user.status == UserStatus.ACTIVE.value
    ):
        identity.email = user.email
        identity.status = IdentityStatus.ACTIVE.value
        identity.password_hash = user.password_hash

    membership = await session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == user.tenant_id,
            TenantMembership.identity_id == identity.id,
        )
    )
    if membership is None:
        membership = TenantMembership(
            id=user.id,
            tenant_id=user.tenant_id,
            identity_id=identity.id,
            legacy_user_id=user.id,
            full_name=user.full_name,
            status=user.status,
            permission_version=user.permission_version,
        )
        session.add(membership)
    else:
        membership.full_name = user.full_name
        membership.status = user.status
        membership.permission_version = user.permission_version
    await session.flush()

    assignments = tuple(
        await session.scalars(
            select(UserRole).where(
                UserRole.tenant_id == user.tenant_id,
                UserRole.user_id == user.id,
            )
        )
    )
    existing_roles = {
        assignment.role_id: assignment
        for assignment in await session.scalars(
            select(MembershipRole).where(
                MembershipRole.tenant_id == user.tenant_id,
                MembershipRole.membership_id == membership.id,
            )
        )
    }
    for assignment in assignments:
        projected = existing_roles.get(assignment.role_id)
        if projected is None:
            session.add(
                MembershipRole(
                    tenant_id=user.tenant_id,
                    membership_id=membership.id,
                    role_id=assignment.role_id,
                    role_scope_type=assignment.role_scope_type,
                    active=assignment.active,
                )
            )
        else:
            projected.active = assignment.active
    await session.flush()


__all__ = [
    "IdentityProjectionConflictError",
    "sync_identity_membership_projection",
]
