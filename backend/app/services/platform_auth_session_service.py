"""Tenantless platform refresh families and live platform-principal validation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.auth import PlatformRefreshSessionFamily, PlatformRefreshSessionToken
from app.models.authorization import Permission, Role, RolePermission
from app.models.identity import Identity, IdentityStatus, PlatformIdentityRole
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
    AuditSeverity,
    AuditVisibilityClass,
)
from app.platform.db import SqlAlchemyUnitOfWork, configure_authentication_database_access
from app.platform.errors.application import ApplicationError
from app.platform.identity import (
    InvalidPlatformRefreshTokenFormatError,
    PlatformAccessPrincipal,
    PlatformAccessTokenCodec,
    PlatformRefreshTokenMaterial,
    issue_platform_refresh_token,
    parse_platform_refresh_token,
)
from app.platform.request_context import AuthenticationStrength
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.authorization_service import AssignedRole, AuthorizationSnapshot
from app.services.identity_credential_lock_service import IdentityCredentialLockService


class InvalidPlatformSessionError(ApplicationError):
    """Generic failure for expired, revoked, or wrong-realm platform sessions."""


class PlatformRoleRequiredError(ApplicationError):
    """Credentials were valid, but the identity has no active platform role."""


@dataclass(frozen=True, slots=True)
class PlatformAuthenticatedUser:
    id: UUID
    email: str
    full_name: str | None
    workspace_scope: str
    roles: tuple[AssignedRole, ...]
    permissions: tuple[str, ...]
    permission_version: int
    authentication_strength: AuthenticationStrength


@dataclass(frozen=True, slots=True)
class PlatformSessionGrant:
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_at: datetime
    session_family_id: UUID
    user: PlatformAuthenticatedUser


@dataclass(frozen=True, slots=True)
class _PersistedPlatformGrant:
    family_id: UUID
    refresh_token: str
    refresh_expires_at: datetime
    user: PlatformAuthenticatedUser


class PlatformAuthSessionService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        access_tokens: PlatformAccessTokenCodec,
        refresh_ttl: timedelta,
        audit_recorder_factory: Callable[[AsyncSession], AuditRecorder] = SqlAlchemyAuditRecorder,
    ) -> None:
        if refresh_ttl <= timedelta(0):
            raise ValueError("Platform refresh session TTL must be positive")
        self._session_factory = session_factory
        self._access_tokens = access_tokens
        self._refresh_ttl = refresh_ttl
        self._audit_recorder_factory = audit_recorder_factory
        self._credential_locks = IdentityCredentialLockService()

    async def start_session(
        self,
        *,
        identity_id: UUID,
        verified_password_hash: str,
        authentication_strength: AuthenticationStrength = AuthenticationStrength.SINGLE_FACTOR,
        audit_context: AuditContext | None = None,
    ) -> PlatformSessionGrant:
        context = audit_context or AuditContext.internal()
        family_id = uuid4()
        refresh = issue_platform_refresh_token()
        now = datetime.now(UTC)
        refresh_expires_at = now + self._refresh_ttl

        async with self._session_factory() as session:
            configure_authentication_database_access(session)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> PlatformAuthenticatedUser | None:
                credential_current = await self._credential_locks.lock_global(
                    session,
                    identity_id=identity_id,
                    verified_password_hash=verified_password_hash,
                )
                if not credential_current:
                    raise InvalidPlatformSessionError()
                identity = await session.scalar(
                    select(Identity).where(Identity.id == identity_id)
                )
                if identity is None or identity.status != IdentityStatus.ACTIVE.value:
                    return None
                authorization = await load_platform_authorization_snapshot(
                    session,
                    identity_id=identity.id,
                )
                if not authorization.roles:
                    await self._audit_recorder_factory(session).record(
                        _platform_login_event(
                            event_type=AuditEventType.PLATFORM_LOGIN_DENIED,
                            action="login",
                            context=context,
                            result=AuditResult.DENIED,
                        )
                    )
                    return None

                session.add(
                    PlatformRefreshSessionFamily(
                        id=family_id,
                        identity_id=identity.id,
                        permission_version=identity.platform_permission_version,
                        authentication_strength=authentication_strength.value,
                        expires_at=refresh_expires_at,
                    )
                )
                session.add(
                    PlatformRefreshSessionToken(
                        id=refresh.token_id,
                        family_id=family_id,
                        token_hash=refresh.token_hash,
                    )
                )
                await session.flush()
                recorder = self._audit_recorder_factory(session)
                await recorder.record(
                    _platform_login_event(
                        event_type=AuditEventType.PLATFORM_LOGIN_SUCCEEDED,
                        action="login",
                        context=context,
                        result=AuditResult.SUCCESS,
                        identity_id=identity.id,
                        family_id=family_id,
                    )
                )
                await recorder.record(
                    _platform_session_event(
                        event_type=AuditEventType.PLATFORM_SESSION_STARTED,
                        action="start",
                        context=context,
                        identity_id=identity.id,
                        family_id=family_id,
                    )
                )
                return _platform_authenticated_user(
                    identity,
                    authorization,
                    authentication_strength=authentication_strength,
                )

            user = await unit_of_work.execute(operation)

        if user is None:
            raise PlatformRoleRequiredError()
        return self._grant(
            _PersistedPlatformGrant(
                family_id=family_id,
                refresh_token=refresh.raw_token,
                refresh_expires_at=refresh_expires_at,
                user=user,
            )
        )

    async def refresh(
        self,
        raw_token: str,
        *,
        audit_context: AuditContext | None = None,
    ) -> PlatformSessionGrant:
        context = audit_context or AuditContext.internal()
        try:
            presented = parse_platform_refresh_token(raw_token)
        except InvalidPlatformRefreshTokenFormatError as exc:
            raise InvalidPlatformSessionError() from exc
        replacement = issue_platform_refresh_token()

        async with self._session_factory() as session:
            configure_authentication_database_access(session)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> _PersistedPlatformGrant | None:
                row = (
                    await session.execute(
                        select(
                            PlatformRefreshSessionToken,
                            PlatformRefreshSessionFamily,
                            Identity,
                        )
                        .join(
                            PlatformRefreshSessionFamily,
                            PlatformRefreshSessionFamily.id
                            == PlatformRefreshSessionToken.family_id,
                        )
                        .join(
                            Identity,
                            Identity.id == PlatformRefreshSessionFamily.identity_id,
                        )
                        .where(
                            PlatformRefreshSessionToken.id == presented.token_id,
                            PlatformRefreshSessionToken.token_hash == presented.token_hash,
                        )
                        .with_for_update(
                            of=(
                                PlatformRefreshSessionToken,
                                PlatformRefreshSessionFamily,
                            )
                        )
                    )
                ).one_or_none()
                if row is None:
                    return None
                token, family, identity = row
                now = datetime.now(UTC)
                if token.consumed_at is not None:
                    if family.revoked_at is None:
                        family.revoked_at = now
                    await self._audit_recorder_factory(session).record(
                        _platform_session_event(
                            event_type=AuditEventType.PLATFORM_SESSION_REUSE_DETECTED,
                            action="detect_reuse",
                            context=context,
                            identity_id=identity.id,
                            family_id=family.id,
                            result=AuditResult.DENIED,
                            severity=AuditSeverity.WARNING,
                        )
                    )
                    return None

                authorization = await load_platform_authorization_snapshot(
                    session,
                    identity_id=identity.id,
                )
                if (
                    family.revoked_at is not None
                    or _as_utc(family.expires_at) <= now
                    or identity.status != IdentityStatus.ACTIVE.value
                    or family.permission_version != identity.platform_permission_version
                    or not authorization.roles
                ):
                    if family.revoked_at is None:
                        family.revoked_at = now
                        await self._audit_recorder_factory(session).record(
                            _platform_session_event(
                                event_type=AuditEventType.PLATFORM_SESSION_REVOKED,
                                action="revoke",
                                context=context,
                                identity_id=identity.id,
                                family_id=family.id,
                            )
                        )
                    return None

                token.consumed_at = now
                session.add(
                    PlatformRefreshSessionToken(
                        id=replacement.token_id,
                        family_id=family.id,
                        token_hash=replacement.token_hash,
                    )
                )
                await session.flush()
                strength = AuthenticationStrength(family.authentication_strength)
                await self._audit_recorder_factory(session).record(
                    _platform_session_event(
                        event_type=AuditEventType.PLATFORM_SESSION_REFRESHED,
                        action="refresh",
                        context=context,
                        identity_id=identity.id,
                        family_id=family.id,
                    )
                )
                return _PersistedPlatformGrant(
                    family_id=family.id,
                    refresh_token=replacement.raw_token,
                    refresh_expires_at=_as_utc(family.expires_at),
                    user=_platform_authenticated_user(
                        identity,
                        authorization,
                        authentication_strength=strength,
                    ),
                )

            persisted = await unit_of_work.execute(operation)

        if persisted is None:
            raise InvalidPlatformSessionError()
        return self._grant(persisted)

    async def current_user(
        self,
        principal: PlatformAccessPrincipal,
    ) -> PlatformAuthenticatedUser:
        async with self._session_factory() as session:
            configure_authentication_database_access(session)
            async with session.begin():
                row = (
                    await session.execute(
                        select(PlatformRefreshSessionFamily, Identity)
                        .join(
                            Identity,
                            Identity.id == PlatformRefreshSessionFamily.identity_id,
                        )
                        .where(
                            PlatformRefreshSessionFamily.id == principal.session_family_id,
                            PlatformRefreshSessionFamily.identity_id == principal.identity_id,
                        )
                    )
                ).one_or_none()
                if row is None:
                    raise InvalidPlatformSessionError()
                family, identity = row
                authorization = await load_platform_authorization_snapshot(
                    session,
                    identity_id=identity.id,
                )
                if (
                    family.revoked_at is not None
                    or _as_utc(family.expires_at) <= datetime.now(UTC)
                    or identity.status != IdentityStatus.ACTIVE.value
                    or identity.platform_permission_version != principal.permission_version
                    or family.permission_version != principal.permission_version
                    or family.authentication_strength
                    != principal.authentication_strength.value
                    or not authorization.roles
                ):
                    raise InvalidPlatformSessionError()
        return _platform_authenticated_user(
            identity,
            authorization,
            authentication_strength=principal.authentication_strength,
        )

    async def revoke(
        self,
        raw_token: str | None,
        *,
        principal: PlatformAccessPrincipal | None = None,
        audit_context: AuditContext | None = None,
    ) -> None:
        context = audit_context or AuditContext.internal()
        presented: PlatformRefreshTokenMaterial | None = None
        if raw_token is not None:
            try:
                presented = parse_platform_refresh_token(raw_token)
            except InvalidPlatformRefreshTokenFormatError:
                pass
        if presented is not None:
            await self._revoke_presented_token(presented, context)
        if principal is not None:
            await self._revoke_family(
                family_id=principal.session_family_id,
                identity_id=principal.identity_id,
                context=context,
                source="access_session",
            )

    async def _revoke_presented_token(
        self,
        presented: PlatformRefreshTokenMaterial,
        context: AuditContext,
    ) -> None:
        async with self._session_factory() as session:
            configure_authentication_database_access(session)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> None:
                family = await session.scalar(
                    select(PlatformRefreshSessionFamily)
                    .join(
                        PlatformRefreshSessionToken,
                        PlatformRefreshSessionToken.family_id
                        == PlatformRefreshSessionFamily.id,
                    )
                    .where(
                        PlatformRefreshSessionToken.id == presented.token_id,
                        PlatformRefreshSessionToken.token_hash == presented.token_hash,
                    )
                    .with_for_update()
                )
                if family is not None:
                    await self._revoke_locked_family(
                        session,
                        family,
                        context=context,
                        source="refresh_cookie",
                    )

            await unit_of_work.execute(operation)

    async def _revoke_family(
        self,
        *,
        family_id: UUID,
        identity_id: UUID,
        context: AuditContext,
        source: str,
    ) -> None:
        async with self._session_factory() as session:
            configure_authentication_database_access(session)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> None:
                family = await session.scalar(
                    select(PlatformRefreshSessionFamily)
                    .where(
                        PlatformRefreshSessionFamily.id == family_id,
                        PlatformRefreshSessionFamily.identity_id == identity_id,
                    )
                    .with_for_update()
                )
                if family is not None:
                    await self._revoke_locked_family(
                        session,
                        family,
                        context=context,
                        source=source,
                    )

            await unit_of_work.execute(operation)

    async def _revoke_locked_family(
        self,
        session: AsyncSession,
        family: PlatformRefreshSessionFamily,
        *,
        context: AuditContext,
        source: str,
    ) -> None:
        if family.revoked_at is not None:
            return
        family.revoked_at = datetime.now(UTC)
        await self._audit_recorder_factory(session).record(
            _platform_session_event(
                event_type=AuditEventType.PLATFORM_SESSION_REVOKED,
                action="revoke",
                context=context,
                identity_id=family.identity_id,
                family_id=family.id,
                metadata={"revocation_reason": "logout", "source": source},
            )
        )

    def _grant(self, persisted: _PersistedPlatformGrant) -> PlatformSessionGrant:
        issued = self._access_tokens.issue(
            PlatformAccessPrincipal(
                identity_id=persisted.user.id,
                session_family_id=persisted.family_id,
                permission_version=persisted.user.permission_version,
                authentication_strength=persisted.user.authentication_strength,
            )
        )
        return PlatformSessionGrant(
            access_token=issued.token,
            expires_in=self._access_tokens.expires_in_seconds,
            refresh_token=persisted.refresh_token,
            refresh_expires_at=persisted.refresh_expires_at,
            session_family_id=persisted.family_id,
            user=persisted.user,
        )


async def load_platform_authorization_snapshot(
    session: AsyncSession,
    *,
    identity_id: UUID,
) -> AuthorizationSnapshot:
    rows = (
        await session.execute(
            select(Role, Permission.code)
            .join(
                PlatformIdentityRole,
                and_(
                    PlatformIdentityRole.role_id == Role.id,
                    PlatformIdentityRole.role_scope_type == Role.scope_type,
                ),
            )
            .outerjoin(RolePermission, RolePermission.role_id == Role.id)
            .outerjoin(Permission, Permission.id == RolePermission.permission_id)
            .where(
                PlatformIdentityRole.identity_id == identity_id,
                PlatformIdentityRole.active.is_(True),
                Role.scope_type == "platform",
            )
            .order_by(Role.code, Permission.code)
        )
    ).all()
    roles: dict[UUID, AssignedRole] = {}
    permissions: set[str] = set()
    for role, permission_code in rows:
        roles[role.id] = AssignedRole(
            id=role.id,
            code=role.code,
            name=role.name,
            scope_type=role.scope_type,
        )
        if permission_code is not None:
            permissions.add(permission_code)
    return AuthorizationSnapshot(
        roles=tuple(sorted(roles.values(), key=lambda role: role.code)),
        permissions=tuple(sorted(permissions)),
        workspace_scope="platform",
    )


def _platform_authenticated_user(
    identity: Identity,
    authorization: AuthorizationSnapshot,
    *,
    authentication_strength: AuthenticationStrength,
) -> PlatformAuthenticatedUser:
    return PlatformAuthenticatedUser(
        id=identity.id,
        email=identity.email,
        full_name=None,
        workspace_scope="platform",
        roles=authorization.roles,
        permissions=authorization.permissions,
        permission_version=identity.platform_permission_version,
        authentication_strength=authentication_strength,
    )


def _platform_login_event(
    *,
    event_type: AuditEventType,
    action: str,
    context: AuditContext,
    result: AuditResult,
    identity_id: UUID | None = None,
    family_id: UUID | None = None,
) -> AuditEventDraft:
    succeeded = event_type is AuditEventType.PLATFORM_LOGIN_SUCCEEDED
    return AuditEventDraft(
        scope_type=AuditScopeType.PLATFORM,
        tenant_id=None,
        actor_type=(AuditActorType.PLATFORM_ADMIN if succeeded else AuditActorType.SYSTEM),
        actor_user_id=identity_id if succeeded else None,
        event_type=event_type,
        category=AuditCategory.PLATFORM_OPERATIONS,
        resource_type="identity" if succeeded else "authentication",
        resource_id=identity_id if succeeded else None,
        action=action,
        result=result,
        context=context,
        session_id=family_id if succeeded else None,
        data_classification=AuditDataClassification.SECURITY_METADATA,
        visibility_class=AuditVisibilityClass.PLATFORM_OPS,
    )


def _platform_session_event(
    *,
    event_type: AuditEventType,
    action: str,
    context: AuditContext,
    identity_id: UUID,
    family_id: UUID,
    result: AuditResult = AuditResult.SUCCESS,
    severity: AuditSeverity = AuditSeverity.INFO,
    metadata: Mapping[str, object] | None = None,
) -> AuditEventDraft:
    return AuditEventDraft(
        scope_type=AuditScopeType.PLATFORM,
        tenant_id=None,
        actor_type=AuditActorType.PLATFORM_ADMIN,
        actor_user_id=identity_id,
        event_type=event_type,
        category=AuditCategory.PLATFORM_OPERATIONS,
        resource_type="session",
        resource_id=family_id,
        action=action,
        result=result,
        context=context,
        session_id=family_id,
        severity=severity,
        metadata=metadata or {},
        data_classification=AuditDataClassification.SECURITY_METADATA,
        visibility_class=AuditVisibilityClass.PLATFORM_OPS,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "InvalidPlatformSessionError",
    "PlatformAuthSessionService",
    "PlatformAuthenticatedUser",
    "PlatformRoleRequiredError",
    "PlatformSessionGrant",
    "load_platform_authorization_snapshot",
]
