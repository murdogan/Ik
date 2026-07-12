"""Authorized tenant user invitation and activation-token issuance."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.auth import UserActivationToken
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditRecorder,
    AuditResult,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.authorization import DenyByDefaultPolicy
from app.platform.db import SqlAlchemyUnitOfWork, configure_tenant_database_access
from app.platform.errors.application import ApplicationError
from app.platform.identity import AccessPrincipal, issue_activation_token
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.authorization_service import (
    assign_system_role,
    load_authorization_snapshot,
)
from app.services.identity_projection_service import sync_identity_membership_projection

_INVITABLE_TENANT_STATUSES = frozenset({TenantStatus.TRIAL.value, TenantStatus.ACTIVE.value})
_authorization_policy = DenyByDefaultPolicy()


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
        audit_recorder_factory: Callable[[AsyncSession], AuditRecorder] = SqlAlchemyAuditRecorder,
    ) -> None:
        self._session_factory = session_factory
        self._activation_ttl = activation_ttl
        self._frontend_base_url = frontend_base_url.rstrip("/")
        self._audit_recorder_factory = audit_recorder_factory

    async def invite(
        self,
        *,
        principal: AccessPrincipal,
        email: str,
        full_name: str,
        audit_context: AuditContext | None = None,
    ) -> InvitationResult:
        context = audit_context or AuditContext.internal()
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
                authorization = await load_authorization_snapshot(
                    session,
                    tenant_id=inviter.tenant_id,
                    user_id=inviter.id,
                )
                if (
                    inviter.status != UserStatus.ACTIVE.value
                    or tenant.status not in _INVITABLE_TENANT_STATUSES
                    or tenant.slug != principal.tenant_slug
                    or not _authorization_policy.allows(
                        "user:invite:tenant",
                        authorization.permissions,
                    )
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
                is_new_user = user is None
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

                if is_new_user:
                    await assign_system_role(
                        session,
                        tenant_id=principal.tenant_id,
                        user_id=user.id,
                        role_code="employee",
                    )

                await sync_identity_membership_projection(session, user)

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
                await self._audit_recorder_factory(session).record(
                    AuditEventDraft(
                        scope_type=AuditScopeType.TENANT,
                        tenant_id=principal.tenant_id,
                        actor_type=AuditActorType.USER,
                        actor_user_id=principal.user_id,
                        event_type=AuditEventType.INVITATION_CREATED,
                        category=AuditCategory.TENANT_ADMIN,
                        resource_type="user",
                        resource_id=user.id,
                        action="invite",
                        result=AuditResult.SUCCESS,
                        context=context,
                        session_id=principal.session_family_id,
                        changed_fields=("status", "roles") if is_new_user else (),
                        metadata={
                            "is_reinvite": not is_new_user,
                            **({"initial_role": "employee"} if is_new_user else {}),
                        },
                        data_classification=AuditDataClassification.TENANT_ADMINISTRATION,
                        visibility_class=AuditVisibilityClass.TENANT_ADMIN,
                    )
                )
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
