"""Authorized tenant user invitation and activation-token issuance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.auth import UserActivationToken
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.db import SqlAlchemyUnitOfWork, configure_tenant_database_access
from app.platform.errors.application import ApplicationError
from app.platform.identity import AccessPrincipal, issue_activation_token

_INVITABLE_TENANT_STATUSES = frozenset(
    {TenantStatus.TRIAL.value, TenantStatus.ACTIVE.value}
)


class InvitationAccessDeniedError(ApplicationError):
    pass


class InvitationConflictError(ApplicationError):
    pass


@dataclass(frozen=True, slots=True)
class InvitationResult:
    user_id: UUID
    email: str
    full_name: str
    activation_url: str
    expires_at: datetime


class UserInvitationService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        activation_ttl: timedelta,
        frontend_base_url: str,
    ) -> None:
        self._session_factory = session_factory
        self._activation_ttl = activation_ttl
        self._frontend_base_url = frontend_base_url.rstrip("/")

    async def invite(
        self,
        *,
        principal: AccessPrincipal,
        email: str,
        full_name: str,
    ) -> InvitationResult:
        token_material = issue_activation_token(principal.tenant_id)
        now = datetime.now(UTC)
        expires_at = now + self._activation_ttl

        async with self._session_factory() as session:
            configure_tenant_database_access(session, principal.tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> InvitationResult:
                inviter_row = (
                    await session.execute(
                        select(User, Tenant)
                        .join(Tenant, Tenant.id == User.tenant_id)
                        .where(
                            User.tenant_id == principal.tenant_id,
                            User.id == principal.user_id,
                            Tenant.id == principal.tenant_id,
                        )
                    )
                ).one_or_none()
                if inviter_row is None:
                    raise InvitationAccessDeniedError()
                inviter, tenant = inviter_row
                if (
                    inviter.status != UserStatus.ACTIVE.value
                    or not inviter.can_invite_users
                    or tenant.status not in _INVITABLE_TENANT_STATUSES
                    or tenant.slug != principal.tenant_slug
                ):
                    raise InvitationAccessDeniedError()

                user = await session.scalar(
                    select(User)
                    .where(
                        User.tenant_id == principal.tenant_id,
                        User.email_normalized == email,
                    )
                    .with_for_update()
                )
                if user is None:
                    user = User(
                        id=uuid4(),
                        tenant_id=principal.tenant_id,
                        email=email,
                        full_name=full_name,
                        status=UserStatus.INVITED.value,
                        password_hash=None,
                    )
                    session.add(user)
                    await session.flush()
                elif user.status == UserStatus.INVITED.value and user.password_hash is None:
                    user.email = email
                    user.full_name = full_name
                else:
                    raise InvitationConflictError()

                await session.execute(
                    update(UserActivationToken)
                    .where(
                        UserActivationToken.tenant_id == principal.tenant_id,
                        UserActivationToken.user_id == user.id,
                        UserActivationToken.consumed_at.is_(None),
                        UserActivationToken.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
                session.add(
                    UserActivationToken(
                        id=uuid4(),
                        tenant_id=principal.tenant_id,
                        user_id=user.id,
                        token_hash=token_material.token_hash,
                        expires_at=expires_at,
                    )
                )
                await session.flush()
                return InvitationResult(
                    user_id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    activation_url=(
                        f"{self._frontend_base_url}/activate#token="
                        f"{quote(token_material.raw_token, safe='.-_')}"
                    ),
                    expires_at=expires_at,
                )

            return await unit_of_work.execute(operation)


__all__ = [
    "InvitationAccessDeniedError",
    "InvitationConflictError",
    "InvitationResult",
    "UserInvitationService",
]
