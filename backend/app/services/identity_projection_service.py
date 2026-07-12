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
_POSTGRES_ACCEPT_EXISTING_FUNCTION = "accept_existing_identity_membership"
_IDENTITY_ACTIVATION_CONFLICT_SQLSTATE = "WF001"
_IDENTITY_CREDENTIAL_CONFLICT_SQLSTATE = "WF002"


class IdentityProjectionConflictError(RuntimeError):
    """The canonical credential changed before activation projection committed."""


class IdentityCredentialConflictError(RuntimeError):
    """The verified existing credential changed before membership acceptance."""


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
                if user.status == UserStatus.INVITED.value or user.password_hash is None
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
        and user.password_hash is not None
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


async def accept_existing_identity_membership_projection(
    session: AsyncSession,
    user: User,
    *,
    verified_password_hash: str,
) -> None:
    """Promote one invited membership only if the verified global hash is unchanged."""

    if session.get_bind().dialect.name == "postgresql":
        try:
            await session.execute(
                text(
                    f"select public.{_POSTGRES_ACCEPT_EXISTING_FUNCTION}("
                    ":user_id, :verified_password_hash)"
                ),
                {
                    "user_id": user.id,
                    "verified_password_hash": verified_password_hash,
                },
            )
        except DBAPIError as exc:
            if sqlstate_from_error(exc) == _IDENTITY_CREDENTIAL_CONFLICT_SQLSTATE:
                raise IdentityCredentialConflictError() from exc
            raise
        return

    identity = await session.scalar(
        select(Identity)
        .where(Identity.email_normalized == user.email.strip().lower())
        .with_for_update()
    )
    if (
        identity is None
        or identity.status != IdentityStatus.ACTIVE.value
        or identity.password_hash != verified_password_hash
    ):
        raise IdentityCredentialConflictError()
    await sync_identity_membership_projection(session, user)


async def sync_existing_membership_projection(
    session: AsyncSession,
    user: User,
) -> None:
    """Keep an already-canonical membership aligned without creating global identity state."""

    membership = await session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == user.tenant_id,
            TenantMembership.legacy_user_id == user.id,
        )
    )
    if membership is None:
        # Expand-contract compatibility: legacy fixtures/users without a canonical projection
        # remain manageable, but they cannot authenticate through the membership-bound path.
        return
    if session.get_bind().dialect.name == "postgresql":
        # P3B's narrow SECURITY DEFINER function is the only tenant-authorized write path for
        # canonical membership projections. The normal tenant role remains SELECT-only.
        await sync_identity_membership_projection(session, user)
        return
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
    assigned_role_ids = {assignment.role_id for assignment in assignments}
    for role_id, projected in existing_roles.items():
        if role_id not in assigned_role_ids:
            projected.active = False
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
    "IdentityCredentialConflictError",
    "IdentityProjectionConflictError",
    "accept_existing_identity_membership_projection",
    "sync_existing_membership_projection",
    "sync_identity_membership_projection",
]
