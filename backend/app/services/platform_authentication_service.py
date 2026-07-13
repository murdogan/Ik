"""Credential verification for the separate platform authentication realm."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.identity import Identity, IdentityStatus
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
from app.platform.db import SqlAlchemyUnitOfWork, configure_authentication_database_access
from app.platform.errors.application import ApplicationError
from app.platform.identity import PasswordManager, PlatformAccessTokenCodec
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.platform_auth_session_service import (
    InvalidPlatformSessionError,
    PlatformAuthSessionService,
    PlatformSessionGrant,
)


class InvalidPlatformCredentialsError(ApplicationError):
    """Publicly generic platform credential failure."""


@dataclass(frozen=True, slots=True)
class _CredentialIdentity:
    id: UUID
    status: str
    password_hash: str | None


class PlatformAuthenticationService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        password_manager: PasswordManager,
        access_tokens: PlatformAccessTokenCodec,
        refresh_ttl: timedelta,
        audit_recorder_factory: Callable[[AsyncSession], AuditRecorder] = SqlAlchemyAuditRecorder,
    ) -> None:
        self._session_factory = session_factory
        self._password_manager = password_manager
        self._audit_recorder_factory = audit_recorder_factory
        self._sessions = PlatformAuthSessionService(
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
    ) -> PlatformSessionGrant:
        context = audit_context or AuditContext.internal()
        identity = await self._find_identity(email)
        password_hash = identity.password_hash if identity is not None else None
        valid_password = await self._password_manager.verify_async(password, password_hash)
        if (
            identity is None
            or identity.status != IdentityStatus.ACTIVE.value
            or password_hash is None
            or not valid_password
        ):
            await self.record_login_failure(context)
            raise InvalidPlatformCredentialsError()
        try:
            return await self._sessions.start_session(
                identity_id=identity.id,
                verified_password_hash=password_hash,
                audit_context=context,
            )
        except InvalidPlatformSessionError as exc:
            await self.record_login_failure(context)
            raise InvalidPlatformCredentialsError() from exc

    async def record_login_failure(self, context: AuditContext) -> None:
        async with self._session_factory() as session:
            configure_authentication_database_access(session)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> None:
                await self._audit_recorder_factory(session).record(
                    AuditEventDraft(
                        scope_type=AuditScopeType.PLATFORM,
                        tenant_id=None,
                        actor_type=AuditActorType.SYSTEM,
                        event_type=AuditEventType.PLATFORM_LOGIN_FAILED,
                        category=AuditCategory.PLATFORM_OPERATIONS,
                        resource_type="authentication",
                        resource_id=None,
                        action="login",
                        result=AuditResult.FAILURE,
                        context=context,
                        data_classification=AuditDataClassification.SECURITY_METADATA,
                        visibility_class=AuditVisibilityClass.PLATFORM_OPS,
                    )
                )

            await unit_of_work.execute(operation)

    async def _find_identity(self, email: str) -> _CredentialIdentity | None:
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
        return _CredentialIdentity(
            id=row.id,
            status=row.status,
            password_hash=row.password_hash,
        )


__all__ = ["InvalidPlatformCredentialsError", "PlatformAuthenticationService"]
