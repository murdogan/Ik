"""Enumeration-resistant global identity password recovery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import quote
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.auth import (
    OrganizationSelectionTransaction,
    PasswordResetToken,
    PlatformRefreshSessionFamily,
    RefreshSessionFamily,
)
from app.models.identity import Identity, IdentityStatus, TenantMembership
from app.models.user import User
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
from app.platform.identity import (
    InvalidPasswordResetTokenFormatError,
    PasswordManager,
    issue_password_reset_token,
    parse_password_reset_token,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder

_POSTGRES_COMPLETE_FUNCTION = "complete_identity_password_reset"
_POSTGRES_ISSUE_FUNCTION = "issue_identity_password_reset"
_RECOVERABLE_IDENTITY_STATUSES = frozenset({IdentityStatus.ACTIVE.value})


class InvalidPasswordResetError(ApplicationError):
    pass


@dataclass(frozen=True, slots=True)
class PasswordResetDeliveryMessage:
    email: str
    reset_url: str
    expires_at: datetime


class PasswordResetDelivery(Protocol):
    async def deliver(self, message: PasswordResetDeliveryMessage, /) -> None: ...


class DiscardPasswordResetDelivery:
    """Safe default until an approved mail adapter is configured outside P3E."""

    async def deliver(self, _message: PasswordResetDeliveryMessage, /) -> None:
        return None


class LocalConsolePasswordResetDelivery:
    """Local/dev fake mail adapter for a manually usable recovery flow."""

    async def deliver(self, message: PasswordResetDeliveryMessage, /) -> None:
        print(
            "LOCAL_PASSWORD_RESET_DELIVERY "
            f"email={message.email} reset_url={message.reset_url} "
            f"expires_at={message.expires_at.isoformat()}"
        )


class PasswordRecoveryService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        password_manager: PasswordManager,
        reset_ttl: timedelta,
        frontend_base_url: str,
        delivery: PasswordResetDelivery | None = None,
        audit_recorder_factory: Callable[[AsyncSession], AuditRecorder] = SqlAlchemyAuditRecorder,
    ) -> None:
        if reset_ttl <= timedelta(0):
            raise ValueError("Password-reset TTL must be positive")
        self._session_factory = session_factory
        self._password_manager = password_manager
        self._reset_ttl = reset_ttl
        self._frontend_base_url = frontend_base_url.rstrip("/")
        self._delivery = delivery or DiscardPasswordResetDelivery()
        self._audit_recorder_factory = audit_recorder_factory

    async def request_reset(
        self,
        *,
        email: str,
        audit_context: AuditContext | None = None,
    ) -> None:
        """Always complete the same public flow, regardless of identity existence."""

        context = audit_context or AuditContext.internal()
        now = datetime.now(UTC)
        expires_at = now + self._reset_ttl

        async with self._session_factory() as session:
            configure_authentication_database_access(session)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> PasswordResetDeliveryMessage:
                identity_statement = select(Identity).where(
                    Identity.email_normalized == email,
                    Identity.status.in_(_RECOVERABLE_IDENTITY_STATUSES),
                )
                is_postgresql = session.get_bind().dialect.name == "postgresql"
                if not is_postgresql:
                    identity_statement = identity_statement.with_for_update()
                identity = await session.scalar(identity_statement)
                token = issue_password_reset_token(identity.id if identity is not None else uuid4())
                if identity is not None and is_postgresql:
                    issued = await session.scalar(
                        text(
                            f"select public.{_POSTGRES_ISSUE_FUNCTION}("
                            ":identity_id, :reset_id, :token_hash, :expires_at)"
                        ),
                        {
                            "identity_id": identity.id,
                            "reset_id": uuid4(),
                            "token_hash": token.token_hash,
                            "expires_at": expires_at,
                        },
                    )
                    if not issued:
                        identity = None
                elif identity is not None:
                    await session.execute(
                        update(PasswordResetToken)
                        .where(
                            PasswordResetToken.identity_id == identity.id,
                            PasswordResetToken.consumed_at.is_(None),
                            PasswordResetToken.revoked_at.is_(None),
                        )
                        .values(revoked_at=now)
                    )
                    session.add(
                        PasswordResetToken(
                            id=uuid4(),
                            identity_id=identity.id,
                            token_hash=token.token_hash,
                            expires_at=expires_at,
                        )
                    )
                await self._audit_recorder_factory(session).record(
                    AuditEventDraft(
                        scope_type=AuditScopeType.PLATFORM,
                        tenant_id=None,
                        actor_type=AuditActorType.SYSTEM,
                        event_type=AuditEventType.PASSWORD_RESET_REQUESTED,
                        category=AuditCategory.PLATFORM_OPERATIONS,
                        resource_type="authentication",
                        resource_id=None,
                        action="request_password_reset",
                        result=AuditResult.SUCCESS,
                        context=context,
                        data_classification=AuditDataClassification.SECURITY_METADATA,
                        visibility_class=AuditVisibilityClass.PLATFORM_OPS,
                    )
                )
                return PasswordResetDeliveryMessage(
                    email=email,
                    reset_url=(
                        f"{self._frontend_base_url}/reset-password#token="
                        f"{quote(token.raw_token, safe='.-_')}"
                    ),
                    expires_at=expires_at,
                )

            delivery_message = await unit_of_work.execute(operation)

        # Delivery failures must not turn the public response into an identity oracle.
        try:
            await self._delivery.deliver(delivery_message)
        except Exception:
            pass

    async def confirm_reset(
        self,
        *,
        raw_token: str,
        password: str,
        audit_context: AuditContext | None = None,
    ) -> None:
        context = audit_context or AuditContext.internal()
        try:
            token = parse_password_reset_token(raw_token)
        except InvalidPasswordResetTokenFormatError as exc:
            raise InvalidPasswordResetError() from exc
        replacement_hash = await self._password_manager.hash_async(password)

        async with self._session_factory() as session:
            configure_authentication_database_access(session)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> None:
                if session.get_bind().dialect.name == "postgresql":
                    completed = await session.scalar(
                        text(
                            f"select public.{_POSTGRES_COMPLETE_FUNCTION}("
                            ":identity_id, :token_hash, :replacement_hash)"
                        ),
                        {
                            "identity_id": token.identity_id,
                            "token_hash": token.token_hash,
                            "replacement_hash": replacement_hash,
                        },
                    )
                else:
                    completed = await self._complete_sqlite_reset(
                        session,
                        identity_id=token.identity_id,
                        token_hash=token.token_hash,
                        replacement_hash=replacement_hash,
                    )
                if not completed:
                    raise InvalidPasswordResetError()
                await self._audit_recorder_factory(session).record(
                    AuditEventDraft(
                        scope_type=AuditScopeType.PLATFORM,
                        tenant_id=None,
                        actor_type=AuditActorType.SYSTEM,
                        event_type=AuditEventType.PASSWORD_RESET_COMPLETED,
                        category=AuditCategory.PLATFORM_OPERATIONS,
                        resource_type="identity",
                        resource_id=token.identity_id,
                        action="complete_password_reset",
                        result=AuditResult.SUCCESS,
                        context=context,
                        data_classification=AuditDataClassification.SECURITY_METADATA,
                        visibility_class=AuditVisibilityClass.PLATFORM_OPS,
                    )
                )

            await unit_of_work.execute(operation)

    async def _complete_sqlite_reset(
        self,
        session: AsyncSession,
        *,
        identity_id: UUID,
        token_hash: str,
        replacement_hash: str,
    ) -> bool:
        row = (
            await session.execute(
                select(PasswordResetToken, Identity)
                .join(Identity, Identity.id == PasswordResetToken.identity_id)
                .where(
                    PasswordResetToken.identity_id == identity_id,
                    PasswordResetToken.token_hash == token_hash,
                    PasswordResetToken.consumed_at.is_(None),
                    PasswordResetToken.revoked_at.is_(None),
                    Identity.status.in_(_RECOVERABLE_IDENTITY_STATUSES),
                )
                .with_for_update()
            )
        ).one_or_none()
        if row is None:
            return False
        reset_token, identity = row
        now = datetime.now(UTC)
        if _as_utc(reset_token.expires_at) <= now:
            return False

        identity.password_hash = replacement_hash
        reset_token.consumed_at = now
        membership_user_ids = select(TenantMembership.legacy_user_id).where(
            TenantMembership.identity_id == identity.id
        )
        await session.execute(
            update(User)
            .where(User.id.in_(membership_user_ids))
            .values(password_hash=replacement_hash)
        )
        await session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.identity_id == identity.id,
                PasswordResetToken.id != reset_token.id,
                PasswordResetToken.consumed_at.is_(None),
                PasswordResetToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await session.execute(
            update(RefreshSessionFamily)
            .where(
                RefreshSessionFamily.membership_id.in_(
                    select(TenantMembership.id).where(TenantMembership.identity_id == identity.id)
                ),
                RefreshSessionFamily.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await session.execute(
            update(PlatformRefreshSessionFamily)
            .where(
                PlatformRefreshSessionFamily.identity_id == identity.id,
                PlatformRefreshSessionFamily.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await session.execute(
            update(OrganizationSelectionTransaction)
            .where(
                OrganizationSelectionTransaction.identity_id == identity.id,
                OrganizationSelectionTransaction.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        await session.flush()
        return True


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "DiscardPasswordResetDelivery",
    "InvalidPasswordResetError",
    "LocalConsolePasswordResetDelivery",
    "PasswordRecoveryService",
    "PasswordResetDelivery",
    "PasswordResetDeliveryMessage",
]
