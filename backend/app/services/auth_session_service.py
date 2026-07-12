"""Server-side refresh families, rotation, reuse detection, and session validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.auth import RefreshSessionFamily, RefreshSessionToken
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.db import SqlAlchemyUnitOfWork, configure_tenant_database_access
from app.platform.errors.application import ApplicationError
from app.platform.identity import (
    AccessPrincipal,
    AccessTokenCodec,
    InvalidRefreshTokenFormatError,
    RefreshTokenMaterial,
    issue_refresh_token,
    parse_refresh_token,
)
from app.services.authorization_service import (
    AssignedRole,
    AuthorizationSnapshot,
    load_authorization_snapshot,
)

_SESSION_TENANT_STATUSES = frozenset(
    {TenantStatus.TRIAL.value, TenantStatus.ACTIVE.value}
)


class InvalidSessionError(ApplicationError):
    """Generic failure for refresh and revoked/expired access sessions."""


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: UUID
    tenant_id: UUID
    email: str
    full_name: str
    tenant_slug: str
    tenant_name: str
    workspace_scope: str
    roles: tuple[AssignedRole, ...]
    permissions: tuple[str, ...]
    permission_version: int


@dataclass(frozen=True, slots=True)
class SessionGrant:
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_at: datetime
    session_family_id: UUID
    user: AuthenticatedUser


@dataclass(frozen=True, slots=True)
class _PersistedSessionGrant:
    family_id: UUID
    refresh_token: str
    refresh_expires_at: datetime
    user: AuthenticatedUser


class AuthSessionService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        access_tokens: AccessTokenCodec,
        refresh_ttl: timedelta,
    ) -> None:
        if refresh_ttl <= timedelta(0):
            raise ValueError("Refresh session TTL must be positive")
        self._session_factory = session_factory
        self._access_tokens = access_tokens
        self._refresh_ttl = refresh_ttl

    async def start_session(
        self,
        *,
        tenant_id: UUID,
        tenant_slug: str,
        user_id: UUID,
    ) -> SessionGrant:
        family_id = uuid4()
        refresh = issue_refresh_token(tenant_id)
        now = datetime.now(UTC)
        refresh_expires_at = now + self._refresh_ttl

        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> AuthenticatedUser:
                row = (
                    await session.execute(
                        select(User, Tenant)
                        .join(Tenant, Tenant.id == User.tenant_id)
                        .where(
                            User.tenant_id == tenant_id,
                            User.id == user_id,
                            Tenant.id == tenant_id,
                        )
                        .with_for_update(of=User)
                    )
                ).one_or_none()
                if row is None:
                    raise InvalidSessionError()
                user, tenant = row
                if (
                    user.status != UserStatus.ACTIVE.value
                    or tenant.status not in _SESSION_TENANT_STATUSES
                    or tenant.slug != tenant_slug
                ):
                    raise InvalidSessionError()

                session.add_all(
                    [
                        RefreshSessionFamily(
                            id=family_id,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            expires_at=refresh_expires_at,
                        ),
                        RefreshSessionToken(
                            id=refresh.token_id,
                            tenant_id=tenant_id,
                            family_id=family_id,
                            token_hash=refresh.token_hash,
                        ),
                    ]
                )
                await session.flush()
                authorization = await load_authorization_snapshot(
                    session,
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                )
                return _authenticated_user(user, tenant, authorization)

            user = await unit_of_work.execute(operation)

        return self._grant(
            _PersistedSessionGrant(
                family_id=family_id,
                refresh_token=refresh.raw_token,
                refresh_expires_at=refresh_expires_at,
                user=user,
            )
        )

    async def refresh(self, raw_token: str) -> SessionGrant:
        try:
            presented = parse_refresh_token(raw_token)
        except InvalidRefreshTokenFormatError as exc:
            raise InvalidSessionError() from exc
        replacement = issue_refresh_token(presented.tenant_id)

        async with self._session_factory() as session:
            configure_tenant_database_access(session, presented.tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> _PersistedSessionGrant | None:
                row = (
                    await session.execute(
                        select(RefreshSessionToken, RefreshSessionFamily, User, Tenant)
                        .join(
                            RefreshSessionFamily,
                            and_(
                                RefreshSessionFamily.tenant_id
                                == RefreshSessionToken.tenant_id,
                                RefreshSessionFamily.id == RefreshSessionToken.family_id,
                            ),
                        )
                        .join(
                            User,
                            and_(
                                User.tenant_id == RefreshSessionFamily.tenant_id,
                                User.id == RefreshSessionFamily.user_id,
                            ),
                        )
                        .join(Tenant, Tenant.id == RefreshSessionFamily.tenant_id)
                        .where(
                            RefreshSessionToken.tenant_id == presented.tenant_id,
                            RefreshSessionToken.id == presented.token_id,
                            RefreshSessionToken.token_hash == presented.token_hash,
                        )
                        .with_for_update(
                            of=(RefreshSessionToken, RefreshSessionFamily, User)
                        )
                    )
                ).one_or_none()
                if row is None:
                    return None

                token, family, user, tenant = row
                now = datetime.now(UTC)
                if token.consumed_at is not None:
                    if family.revoked_at is None:
                        family.revoked_at = now
                        await session.flush()
                    # Returning commits reuse-triggered family revocation. Raising here would
                    # roll it back and leave the stolen successor usable.
                    return None

                if (
                    family.revoked_at is not None
                    or _as_utc(family.expires_at) <= now
                    or user.status != UserStatus.ACTIVE.value
                    or tenant.status not in _SESSION_TENANT_STATUSES
                ):
                    if family.revoked_at is None:
                        family.revoked_at = now
                        await session.flush()
                    return None

                token.consumed_at = now
                session.add(
                    RefreshSessionToken(
                        id=replacement.token_id,
                        tenant_id=family.tenant_id,
                        family_id=family.id,
                        token_hash=replacement.token_hash,
                    )
                )
                await session.flush()
                authorization = await load_authorization_snapshot(
                    session,
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                )
                return _PersistedSessionGrant(
                    family_id=family.id,
                    refresh_token=replacement.raw_token,
                    refresh_expires_at=_as_utc(family.expires_at),
                    user=_authenticated_user(user, tenant, authorization),
                )

            persisted = await unit_of_work.execute(operation)

        if persisted is None:
            raise InvalidSessionError()
        return self._grant(persisted)

    async def current_user(self, principal: AccessPrincipal) -> AuthenticatedUser:
        family_id = principal.session_family_id
        async with self._session_factory() as session:
            configure_tenant_database_access(session, principal.tenant_id)
            async with session.begin():
                row = (
                    await session.execute(
                        select(RefreshSessionFamily, User, Tenant)
                        .join(
                            User,
                            and_(
                                User.tenant_id == RefreshSessionFamily.tenant_id,
                                User.id == RefreshSessionFamily.user_id,
                            ),
                        )
                        .join(Tenant, Tenant.id == RefreshSessionFamily.tenant_id)
                        .where(
                            RefreshSessionFamily.tenant_id == principal.tenant_id,
                            RefreshSessionFamily.id == family_id,
                            RefreshSessionFamily.user_id == principal.user_id,
                        )
                        .with_for_update(of=(RefreshSessionFamily, User))
                    )
                ).one_or_none()
                if row is None:
                    raise InvalidSessionError()
                family, user, tenant = row
                now = datetime.now(UTC)
                if (
                    family.revoked_at is not None
                    or _as_utc(family.expires_at) <= now
                    or user.status != UserStatus.ACTIVE.value
                    or tenant.status not in _SESSION_TENANT_STATUSES
                    or tenant.slug != principal.tenant_slug
                    or user.permission_version != principal.permission_version
                ):
                    raise InvalidSessionError()
                authorization = await load_authorization_snapshot(
                    session,
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                )
        return _authenticated_user(user, tenant, authorization)

    async def revoke(
        self,
        raw_token: str | None,
        *,
        principal: AccessPrincipal | None = None,
    ) -> None:
        if raw_token is not None:
            try:
                presented = parse_refresh_token(raw_token)
            except InvalidRefreshTokenFormatError:
                presented = None
            if presented is not None:
                await self._revoke_presented_token(presented)
        if principal is not None:
            await self._revoke_principal_family(principal)

    async def _revoke_presented_token(self, presented: RefreshTokenMaterial) -> None:
        async with self._session_factory() as session:
            configure_tenant_database_access(session, presented.tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> None:
                family = await session.scalar(
                    select(RefreshSessionFamily)
                    .join(
                        RefreshSessionToken,
                        and_(
                            RefreshSessionToken.tenant_id
                            == RefreshSessionFamily.tenant_id,
                            RefreshSessionToken.family_id == RefreshSessionFamily.id,
                        ),
                    )
                    .where(
                        RefreshSessionToken.tenant_id == presented.tenant_id,
                        RefreshSessionToken.id == presented.token_id,
                        RefreshSessionToken.token_hash == presented.token_hash,
                    )
                    .with_for_update()
                )
                if family is not None and family.revoked_at is None:
                    family.revoked_at = datetime.now(UTC)
                    await session.flush()

            await unit_of_work.execute(operation)

    async def _revoke_principal_family(self, principal: AccessPrincipal) -> None:
        async with self._session_factory() as session:
            configure_tenant_database_access(session, principal.tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> None:
                family = await session.scalar(
                    select(RefreshSessionFamily)
                    .where(
                        RefreshSessionFamily.tenant_id == principal.tenant_id,
                        RefreshSessionFamily.id == principal.session_family_id,
                        RefreshSessionFamily.user_id == principal.user_id,
                    )
                    .with_for_update()
                )
                if family is not None and family.revoked_at is None:
                    family.revoked_at = datetime.now(UTC)
                    await session.flush()

            await unit_of_work.execute(operation)

    def _grant(self, persisted: _PersistedSessionGrant) -> SessionGrant:
        issued = self._access_tokens.issue(
            AccessPrincipal(
                user_id=persisted.user.id,
                tenant_id=persisted.user.tenant_id,
                tenant_slug=persisted.user.tenant_slug,
                session_family_id=persisted.family_id,
                permission_version=persisted.user.permission_version,
            )
        )
        return SessionGrant(
            access_token=issued.token,
            expires_in=self._access_tokens.expires_in_seconds,
            refresh_token=persisted.refresh_token,
            refresh_expires_at=persisted.refresh_expires_at,
            session_family_id=persisted.family_id,
            user=persisted.user,
        )


def _authenticated_user(
    user: User,
    tenant: Tenant,
    authorization: AuthorizationSnapshot,
) -> AuthenticatedUser:
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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "AuthenticatedUser",
    "AuthSessionService",
    "InvalidSessionError",
    "SessionGrant",
]
