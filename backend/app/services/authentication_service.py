"""Email-first global identity login and one-time activation application service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.auth import (
    OrganizationSelectionChoice,
    OrganizationSelectionTransaction,
    UserActivationToken,
)
from app.models.identity import Identity, IdentityStatus, MembershipStatus, TenantMembership
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
from app.platform.db import (
    SqlAlchemyUnitOfWork,
    configure_authentication_database_access,
    configure_tenant_database_access,
)
from app.platform.errors.application import ApplicationError
from app.platform.identity import (
    AccessTokenCodec,
    ActivationTokenMaterial,
    InvalidActivationTokenFormatError,
    PasswordManager,
    issue_organization_selection_token,
    parse_activation_token,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.auth_session_service import (
    AuthenticatedUser,
    AuthSessionService,
    InvalidSessionError,
    SessionGrant,
)
from app.services.authorization_service import load_authorization_snapshot
from app.services.identity_projection_service import (
    IdentityProjectionConflictError,
    sync_identity_membership_projection,
)

_LOGIN_TENANT_STATUSES = frozenset({TenantStatus.TRIAL.value, TenantStatus.ACTIVE.value})


class InvalidCredentialsError(ApplicationError):
    pass


class InvalidActivationError(ApplicationError):
    pass


@dataclass(frozen=True, slots=True)
class CredentialIdentity:
    id: UUID
    status: str
    password_hash: str | None


@dataclass(frozen=True, slots=True)
class EligibleMembership:
    membership_id: UUID
    tenant_id: UUID
    tenant_slug: str
    tenant_name: str
    legacy_user_id: UUID


@dataclass(frozen=True, slots=True)
class OrganizationChoice:
    selection_key: UUID
    display_name: str


@dataclass(frozen=True, slots=True)
class OrganizationSelectionRequired:
    selection_transaction: str
    expires_in: int
    organizations: tuple[OrganizationChoice, ...]


LoginResult = SessionGrant | OrganizationSelectionRequired


class AuthenticationService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        password_manager: PasswordManager,
        access_tokens: AccessTokenCodec,
        refresh_ttl: timedelta = timedelta(days=14),
        organization_selection_ttl: timedelta = timedelta(minutes=5),
        audit_recorder_factory: Callable[[AsyncSession], AuditRecorder] = SqlAlchemyAuditRecorder,
    ) -> None:
        self._session_factory = session_factory
        self._password_manager = password_manager
        self._audit_recorder_factory = audit_recorder_factory
        if organization_selection_ttl <= timedelta(0):
            raise ValueError("Organization selection TTL must be positive")
        self._organization_selection_ttl = organization_selection_ttl
        self._sessions = AuthSessionService(
            session_factory=session_factory,
            access_tokens=access_tokens,
            refresh_ttl=refresh_ttl,
            audit_recorder_factory=audit_recorder_factory,
        )

    async def login(
        self,
        *,
        email: str,
        password: str,
        audit_context: AuditContext | None = None,
    ) -> LoginResult:
        context = audit_context or AuditContext.internal()
        identity = await self._find_identity(email)
        password_hash = identity.password_hash if identity is not None else None
        valid_password = await self._password_manager.verify_async(
            password,
            password_hash,
        )
        if (
            identity is None
            or identity.status != IdentityStatus.ACTIVE.value
            or not valid_password
        ):
            await self.record_global_login_failure(context)
            raise InvalidCredentialsError()

        discovery = await self._resolve_eligible_memberships(
            identity_id=identity.id,
            verified_password_hash=password_hash,
        )
        if discovery is None:
            await self.record_global_login_failure(context)
            raise InvalidCredentialsError()
        if isinstance(discovery, OrganizationSelectionRequired):
            return discovery

        membership = discovery

        try:
            return await self._sessions.start_session(
                tenant_id=membership.tenant_id,
                tenant_slug=membership.tenant_slug,
                user_id=membership.legacy_user_id,
                membership_id=membership.membership_id,
                audit_context=context,
            )
        except InvalidSessionError as exc:
            # Preserve login's one generic credential/account failure contract even if account
            # state changes between password verification and transactional session creation.
            await self.record_global_login_failure(context)
            raise InvalidCredentialsError() from exc

    async def record_global_login_failure(self, context: AuditContext) -> None:
        """Record a pre-tenant failure without resolving or naming any membership."""

        async with self._session_factory() as session:
            configure_authentication_database_access(session)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> None:
                await self._audit_recorder_factory(session).record(
                    AuditEventDraft(
                        scope_type=AuditScopeType.PLATFORM,
                        tenant_id=None,
                        actor_type=AuditActorType.SYSTEM,
                        event_type=AuditEventType.LOGIN_FAILED,
                        category=AuditCategory.PLATFORM_OPERATIONS,
                        resource_type="authentication",
                        resource_id=None,
                        action="login",
                        result=AuditResult.FAILURE,
                        context=context,
                        metadata={"failure_reason": "authentication_failed"},
                        data_classification=AuditDataClassification.PLATFORM_METADATA,
                        visibility_class=AuditVisibilityClass.PLATFORM_OPS,
                    )
                )

            await unit_of_work.execute(operation)

    async def activate(
        self,
        *,
        raw_token: str,
        password: str,
        audit_context: AuditContext | None = None,
    ) -> AuthenticatedUser:
        context = audit_context or AuditContext.internal()
        try:
            token_material = parse_activation_token(raw_token)
        except InvalidActivationTokenFormatError as exc:
            raise InvalidActivationError() from exc

        target_email = await self._find_activation_target_email(token_material)
        if target_email is None:
            raise InvalidActivationError()
        identity = await self._find_identity(target_email)
        if identity is not None and identity.status != IdentityStatus.PENDING.value:
            # A tenant invitation is not proof of control over an existing global identity.
            # Membership acceptance for an already-active identity must happen behind a later
            # identity-authenticated flow; never turn this activation token into a password reset.
            raise InvalidActivationError()
        activation_password_hash = await self._password_manager.hash_async(password)

        async with self._session_factory() as session:
            configure_tenant_database_access(session, token_material.tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> AuthenticatedUser:
                row = (
                    await session.execute(
                        select(UserActivationToken, User, Tenant)
                        .join(
                            User,
                            and_(
                                User.tenant_id == UserActivationToken.tenant_id,
                                User.id == UserActivationToken.user_id,
                            ),
                        )
                        .join(Tenant, Tenant.id == UserActivationToken.tenant_id)
                        .where(
                            UserActivationToken.tenant_id == token_material.tenant_id,
                            UserActivationToken.token_hash == token_material.token_hash,
                            UserActivationToken.consumed_at.is_(None),
                            UserActivationToken.revoked_at.is_(None),
                        )
                        .with_for_update()
                    )
                ).one_or_none()
                if row is None:
                    raise InvalidActivationError()

                activation, user, tenant = row
                now = datetime.now(UTC)
                if (
                    _as_utc(activation.expires_at) <= now
                    or user.status != UserStatus.INVITED.value
                    or tenant.status not in _LOGIN_TENANT_STATUSES
                    or user.email_normalized != target_email
                ):
                    raise InvalidActivationError()

                user.password_hash = activation_password_hash
                user.status = UserStatus.ACTIVE.value
                activation.consumed_at = now
                await session.flush()
                try:
                    await sync_identity_membership_projection(
                        session,
                        user,
                        require_pending_identity=True,
                    )
                except IdentityProjectionConflictError as exc:
                    raise InvalidActivationError() from exc
                authorization = await load_authorization_snapshot(
                    session,
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                )
                await self._audit_recorder_factory(session).record(
                    AuditEventDraft(
                        scope_type=AuditScopeType.TENANT,
                        tenant_id=user.tenant_id,
                        actor_type=AuditActorType.USER,
                        actor_user_id=user.id,
                        event_type=AuditEventType.ACTIVATION_COMPLETED,
                        category=AuditCategory.TENANT_SECURITY,
                        resource_type="user",
                        resource_id=user.id,
                        action="activate",
                        result=AuditResult.SUCCESS,
                        context=context,
                        changed_fields=("status",),
                        metadata={
                            "before_status": UserStatus.INVITED.value,
                            "after_status": UserStatus.ACTIVE.value,
                        },
                        data_classification=AuditDataClassification.SECURITY_METADATA,
                        visibility_class=AuditVisibilityClass.TENANT_SECURITY,
                    )
                )
                return AuthenticatedUser(
                    id=user.id,
                    tenant_id=user.tenant_id,
                    email=user.email,
                    full_name=user.full_name,
                    tenant_slug=tenant.slug,
                    tenant_name=tenant.name,
                    workspace_scope=authorization.workspace_scope,
                    roles=authorization.roles,
                    permissions=authorization.permissions,
                    permission_version=user.permission_version,
                )

            return await unit_of_work.execute(operation)

    async def _find_activation_target_email(
        self,
        token_material: ActivationTokenMaterial,
    ) -> str | None:
        async with self._session_factory() as session:
            configure_tenant_database_access(session, token_material.tenant_id)
            async with session.begin():
                row = (
                    await session.execute(
                        select(UserActivationToken, User, Tenant)
                        .join(
                            User,
                            and_(
                                User.tenant_id == UserActivationToken.tenant_id,
                                User.id == UserActivationToken.user_id,
                            ),
                        )
                        .join(Tenant, Tenant.id == UserActivationToken.tenant_id)
                        .where(
                            UserActivationToken.tenant_id == token_material.tenant_id,
                            UserActivationToken.token_hash == token_material.token_hash,
                            UserActivationToken.consumed_at.is_(None),
                            UserActivationToken.revoked_at.is_(None),
                        )
                    )
                ).one_or_none()
                if row is None:
                    return None
                activation, user, tenant = row
                if (
                    _as_utc(activation.expires_at) <= datetime.now(UTC)
                    or user.status != UserStatus.INVITED.value
                    or tenant.status not in _LOGIN_TENANT_STATUSES
                ):
                    return None
                return user.email_normalized

    async def _find_identity(self, email: str) -> CredentialIdentity | None:
        async with self._session_factory() as session:
            configure_authentication_database_access(session)
            async with session.begin():
                row = (
                    await session.execute(
                        select(
                            Identity.id,
                            Identity.status,
                            Identity.password_hash,
                        ).where(Identity.email_normalized == email)
                    )
                ).one_or_none()
                if row is None:
                    return None
                return CredentialIdentity(
                    id=row.id,
                    status=row.status,
                    password_hash=row.password_hash,
                )

    async def _resolve_eligible_memberships(
        self,
        *,
        identity_id: UUID,
        verified_password_hash: str | None,
    ) -> EligibleMembership | OrganizationSelectionRequired | None:
        async with self._session_factory() as session:
            configure_authentication_database_access(session)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> EligibleMembership | OrganizationSelectionRequired | None:
                rows = list(
                    (
                        await session.execute(
                            select(
                                TenantMembership.id,
                                TenantMembership.tenant_id,
                                Tenant.slug,
                                Tenant.name,
                                TenantMembership.legacy_user_id,
                            )
                            .join(
                                Identity,
                                Identity.id == TenantMembership.identity_id,
                            )
                            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
                            .join(
                                User,
                                and_(
                                    User.tenant_id == TenantMembership.tenant_id,
                                    User.id == TenantMembership.legacy_user_id,
                                ),
                            )
                            .where(
                                TenantMembership.identity_id == identity_id,
                                Identity.status == IdentityStatus.ACTIVE.value,
                                Identity.password_hash == verified_password_hash,
                                TenantMembership.status == MembershipStatus.ACTIVE.value,
                                Tenant.status.in_(_LOGIN_TENANT_STATUSES),
                                User.status == UserStatus.ACTIVE.value,
                            )
                            .order_by(Tenant.name, Tenant.id)
                        )
                    ).all()
                )
                memberships = tuple(
                    EligibleMembership(
                        membership_id=row.id,
                        tenant_id=row.tenant_id,
                        tenant_slug=row.slug,
                        tenant_name=row.name,
                        legacy_user_id=row.legacy_user_id,
                    )
                    for row in rows
                )
                if not memberships:
                    return None
                if len(memberships) == 1:
                    return memberships[0]

                token = issue_organization_selection_token()
                now = datetime.now(UTC)
                expires_at = now + self._organization_selection_ttl
                choices = tuple(
                    OrganizationChoice(
                        selection_key=uuid4(),
                        display_name=membership.tenant_name,
                    )
                    for membership in memberships
                )
                session.add(
                    OrganizationSelectionTransaction(
                        id=token.transaction_id,
                        identity_id=identity_id,
                        token_hash=token.token_hash,
                        expires_at=expires_at,
                    )
                )
                # Persist the transaction before its opaque choices. The models deliberately
                # expose no navigation relationship, so the Unit of Work has no mapper-level
                # dependency edge from which to infer this FK ordering.
                await session.flush()
                session.add_all(
                    OrganizationSelectionChoice(
                        selection_key=choice.selection_key,
                        transaction_id=token.transaction_id,
                        tenant_id=membership.tenant_id,
                    )
                    for choice, membership in zip(choices, memberships, strict=True)
                )
                await session.flush()
                return OrganizationSelectionRequired(
                    selection_transaction=token.raw_token,
                    expires_in=max(
                        1,
                        int((expires_at - datetime.now(UTC)).total_seconds()),
                    ),
                    organizations=choices,
                )

            return await unit_of_work.execute(operation)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "AuthenticatedUser",
    "AuthenticationService",
    "InvalidActivationError",
    "InvalidCredentialsError",
    "LoginResult",
    "OrganizationChoice",
    "OrganizationSelectionRequired",
    "SessionGrant",
]
