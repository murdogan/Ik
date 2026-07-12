"""Tenant-aware login and one-time activation application service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.auth import UserActivationToken
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.db import (
    SqlAlchemyUnitOfWork,
    configure_platform_database_access,
    configure_tenant_database_access,
)
from app.platform.errors.application import ApplicationError
from app.platform.identity import (
    AccessTokenCodec,
    InvalidActivationTokenFormatError,
    PasswordManager,
    parse_activation_token,
)
from app.services.auth_session_service import (
    AuthenticatedUser,
    AuthSessionService,
    InvalidSessionError,
    SessionGrant,
)
from app.services.authorization_service import load_authorization_snapshot

_LOGIN_TENANT_STATUSES = frozenset(
    {TenantStatus.TRIAL.value, TenantStatus.ACTIVE.value}
)
LoginResult = SessionGrant


class InvalidCredentialsError(ApplicationError):
    pass


class InvalidActivationError(ApplicationError):
    pass


@dataclass(frozen=True, slots=True)
class TenantDiscovery:
    id: UUID
    slug: str
    name: str
    status: str


class AuthenticationService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        password_manager: PasswordManager,
        access_tokens: AccessTokenCodec,
        refresh_ttl: timedelta = timedelta(days=14),
    ) -> None:
        self._session_factory = session_factory
        self._password_manager = password_manager
        self._sessions = AuthSessionService(
            session_factory=session_factory,
            access_tokens=access_tokens,
            refresh_ttl=refresh_ttl,
        )

    async def login(self, *, tenant_slug: str, email: str, password: str) -> SessionGrant:
        tenant = await self._discover_tenant(tenant_slug)
        if tenant is None or tenant.status not in _LOGIN_TENANT_STATUSES:
            await self._password_manager.verify_async(password, None)
            raise InvalidCredentialsError()

        user = await self._find_login_user(tenant.id, email)
        password_hash = user.password_hash if user is not None else None
        valid_password = await self._password_manager.verify_async(password, password_hash)
        if (
            user is None
            or user.status != UserStatus.ACTIVE.value
            or not valid_password
        ):
            raise InvalidCredentialsError()

        try:
            return await self._sessions.start_session(
                tenant_id=tenant.id,
                tenant_slug=tenant.slug,
                user_id=user.id,
            )
        except InvalidSessionError as exc:
            # Preserve login's one generic credential/account failure contract even if account
            # state changes between password verification and transactional session creation.
            raise InvalidCredentialsError() from exc

    async def activate(self, *, raw_token: str, password: str) -> AuthenticatedUser:
        try:
            token_material = parse_activation_token(raw_token)
        except InvalidActivationTokenFormatError as exc:
            raise InvalidActivationError() from exc

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
                ):
                    raise InvalidActivationError()

                user.password_hash = await self._password_manager.hash_async(password)
                user.status = UserStatus.ACTIVE.value
                activation.consumed_at = now
                await session.flush()
                authorization = await load_authorization_snapshot(
                    session,
                    tenant_id=user.tenant_id,
                    user_id=user.id,
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

    async def _discover_tenant(self, tenant_slug: str) -> TenantDiscovery | None:
        async with self._session_factory() as session:
            configure_platform_database_access(session)
            async with session.begin():
                row = (
                    await session.execute(
                        select(
                            Tenant.id,
                            Tenant.slug,
                            Tenant.name,
                            Tenant.status,
                        ).where(Tenant.slug == tenant_slug)
                    )
                ).one_or_none()
            return TenantDiscovery(*row) if row is not None else None

    async def _find_login_user(self, tenant_id: UUID, email: str) -> User | None:
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                return await session.scalar(
                    select(User).where(
                        User.tenant_id == tenant_id,
                        User.email_normalized == email,
                    )
                )


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
    "SessionGrant",
]
