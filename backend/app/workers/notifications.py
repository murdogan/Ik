"""Bounded PostgreSQL outbox expansion and notification email delivery worker."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from time import monotonic
from urllib.parse import quote, urlsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import create_database_runtime
from app.models.announcement import Announcement, AnnouncementRecipient
from app.models.auth import UserActivationToken
from app.models.employee_assignment import EmployeeAssignment
from app.models.leave import OutboxEvent
from app.models.leave_request import LeaveRequest
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    OutboxEventConsumption,
)
from app.models.tenant import Tenant
from app.models.user import User, UserStatus
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditResult,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.db import configure_platform_database_access, configure_tenant_database_access
from app.platform.identity import (
    ActivationDeliveryTokenCodec,
    is_manual_activation_delivery_event,
)
from app.platform.observability.operational import (
    configure_operational_logger,
    log_worker_failed,
    log_worker_heartbeat,
    log_worker_started,
    log_worker_stopped,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.notification_email_provider import (
    EmailDeliveryError,
    EmailMessage,
    EmailProvider,
    LocalCaptureEmailProvider,
    SmtpEmailProvider,
    UnavailableEmailProvider,
)
from app.services.phase7_access import Phase7FeatureUnavailableError, require_phase7_feature

_INITIAL_ADMIN_INVITATION_EVENT_TYPE = "identity.initial_admin_invited"
_FEATURE_INDEPENDENT_EVENT_TYPES = (_INITIAL_ADMIN_INVITATION_EVENT_TYPE,)
_EVENT_TYPES = (
    "leave.requested",
    "leave.approved",
    "leave.rejected",
    "leave.cancelled",
    "leave.balance_adjusted",
    "announcement.published",
    _INITIAL_ADMIN_INVITATION_EVENT_TYPE,
)
_ANNOUNCEMENT_RECIPIENT_LIMIT = 500
_DELIVERY_LEASE_DURATION = timedelta(minutes=5)
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _RecipientNotification:
    user_id: UUID
    notification_type: str
    title: str
    body: str
    portal_path: str
    email_enabled: bool


@dataclass(frozen=True, slots=True)
class _ClaimedEmailDelivery:
    tenant_id: UUID
    delivery_id: UUID
    lease_id: UUID
    attempt_number: int
    message: EmailMessage


class NotificationWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self._tenant_cursor: UUID | None = None
        configured_key = settings.auth_signing_key
        if configured_key is None and settings.notification_email_backend != "disabled":
            raise RuntimeError("IK_AUTH_SIGNING_KEY is required for activation email delivery")
        self._activation_delivery_tokens = (
            ActivationDeliveryTokenCodec(configured_key.get_secret_value().encode("utf-8"))
            if configured_key is not None
            else None
        )

    async def run_once(self) -> int:
        tenant_ids = await self._discover_tenants()
        processed = 0
        for tenant_id in tenant_ids:
            try:
                processed += await self._process_tenant(tenant_id)
            except Exception as exc:
                _LOGGER.error(
                    "Notification tenant batch failed error_class=%s",
                    type(exc).__name__,
                )
        return processed

    async def _discover_tenants(self) -> list[UUID]:
        async with self.session_factory() as session:
            configure_platform_database_access(session)
            async with session.begin():
                statement = select(Tenant.id).where(Tenant.status.in_(("trial", "active")))
                if self._tenant_cursor is not None:
                    statement = statement.where(Tenant.id > self._tenant_cursor)
                tenant_ids = list(
                    await session.scalars(
                        statement.order_by(Tenant.id).limit(
                            self.settings.notification_worker_tenant_batch_size
                        )
                    )
                )
                if not tenant_ids and self._tenant_cursor is not None:
                    self._tenant_cursor = None
                    tenant_ids = list(
                        await session.scalars(
                            select(Tenant.id)
                            .where(Tenant.status.in_(("trial", "active")))
                            .order_by(Tenant.id)
                            .limit(self.settings.notification_worker_tenant_batch_size)
                        )
                    )
        if tenant_ids:
            self._tenant_cursor = tenant_ids[-1]
        return tenant_ids

    async def _process_tenant(self, tenant_id: UUID) -> int:
        async with self.session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                notifications_enabled = True
                try:
                    await require_phase7_feature(
                        session,
                        tenant_id=tenant_id,
                        feature=FeatureFlagKey.NOTIFICATIONS,
                    )
                except Phase7FeatureUnavailableError:
                    notifications_enabled = False
                event_types = (
                    _EVENT_TYPES if notifications_enabled else _FEATURE_INDEPENDENT_EVENT_TYPES
                )
                expanded = await self._expand_outbox(
                    session,
                    tenant_id,
                    event_types=event_types,
                )
        delivered = await self._deliver_email(
            tenant_id,
            event_types=event_types,
        )
        return expanded + delivered

    async def _expand_outbox(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        *,
        event_types: tuple[str, ...],
    ) -> int:
        events = list(
            await session.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.tenant_id == tenant_id,
                    OutboxEvent.event_type.in_(event_types),
                    ~exists(
                        select(OutboxEventConsumption.id).where(
                            OutboxEventConsumption.tenant_id == OutboxEvent.tenant_id,
                            OutboxEventConsumption.source_event_id == OutboxEvent.id,
                        )
                    ),
                )
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
                .limit(self.settings.notification_worker_event_batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        for event in events:
            recipients = await self._recipients(session, event)
            for recipient in recipients:
                self._add_notification(session, event, recipient)
            session.add(
                OutboxEventConsumption(
                    id=_stable_uuid("consumption", tenant_id, event.id),
                    tenant_id=tenant_id,
                    source_event_id=event.id,
                    outcome="processed" if recipients else "skipped",
                    recipient_count=len(recipients),
                )
            )
        if events:
            await session.flush()
        return len(events)

    async def _recipients(
        self, session: AsyncSession, event: OutboxEvent
    ) -> list[_RecipientNotification]:
        if event.event_type == "identity.initial_admin_invited":
            invitation = _initial_admin_invitation(event)
            if invitation is None:
                return []
            recipient_user_id, activation_id = invitation
            if is_manual_activation_delivery_event(event.id, activation_id):
                return []
            return [
                _RecipientNotification(
                    user_id=recipient_user_id,
                    notification_type="initial_admin_invitation",
                    title="Your organization access is ready",
                    body="Set up access to your organization.",
                    portal_path="/activate",
                    email_enabled=True,
                )
            ]
        portal_path = f"/requests/{event.aggregate_id}"
        if event.event_type == "leave.requested":
            manager_id = await session.scalar(
                select(EmployeeAssignment.manager_user_id)
                .join(
                    LeaveRequest,
                    and_(
                        LeaveRequest.tenant_id == EmployeeAssignment.tenant_id,
                        LeaveRequest.employee_id == EmployeeAssignment.employee_id,
                    ),
                )
                .join(
                    User,
                    and_(
                        User.tenant_id == EmployeeAssignment.tenant_id,
                        User.id == EmployeeAssignment.manager_user_id,
                    ),
                )
                .where(
                    LeaveRequest.tenant_id == event.tenant_id,
                    LeaveRequest.id == event.aggregate_id,
                    LeaveRequest.status == "pending",
                    EmployeeAssignment.manager_user_id.is_not(None),
                    User.status == UserStatus.ACTIVE.value,
                    EmployeeAssignment.effective_from <= date.today(),
                    or_(
                        EmployeeAssignment.effective_to.is_(None),
                        EmployeeAssignment.effective_to > date.today(),
                    ),
                )
                .order_by(EmployeeAssignment.effective_from.desc(), EmployeeAssignment.id.desc())
                .limit(1)
            )
            if manager_id is None:
                return []
            return [
                _RecipientNotification(
                    user_id=manager_id,
                    notification_type="leave_action_required",
                    title="Leave request awaiting action",
                    body="A leave request is waiting for your action.",
                    portal_path=portal_path,
                    email_enabled=True,
                )
            ]
        if event.event_type in {
            "leave.approved",
            "leave.rejected",
            "leave.cancelled",
        }:
            requester_id = await session.scalar(
                select(LeaveRequest.requested_by_user_id).where(
                    LeaveRequest.tenant_id == event.tenant_id,
                    LeaveRequest.id == event.aggregate_id,
                )
            )
            if requester_id is None:
                return []
            status = event.event_type.removeprefix("leave.")
            return [
                _RecipientNotification(
                    user_id=requester_id,
                    notification_type="leave_status_changed",
                    title="Leave request updated",
                    body=f"Your leave request was {status}.",
                    portal_path=portal_path,
                    email_enabled=True,
                )
            ]
        if event.event_type == "announcement.published":
            recipient_rows = (
                await session.execute(
                    select(
                        AnnouncementRecipient.recipient_user_id,
                        Announcement.is_critical,
                    )
                    .join(
                        Announcement,
                        and_(
                            Announcement.tenant_id == AnnouncementRecipient.tenant_id,
                            Announcement.id == AnnouncementRecipient.announcement_id,
                        ),
                    )
                    .where(
                        AnnouncementRecipient.tenant_id == event.tenant_id,
                        AnnouncementRecipient.announcement_id == event.aggregate_id,
                        Announcement.status == "published",
                    )
                    .order_by(AnnouncementRecipient.recipient_user_id)
                    .limit(_ANNOUNCEMENT_RECIPIENT_LIMIT)
                )
            ).all()
            return [
                _RecipientNotification(
                    user_id=recipient_id,
                    notification_type="announcement_published",
                    title="New announcement",
                    body="A new announcement is available.",
                    portal_path=f"/announcements/{event.aggregate_id}",
                    email_enabled=is_critical,
                )
                for recipient_id, is_critical in recipient_rows
            ]
        return []

    def _add_notification(
        self,
        session: AsyncSession,
        event: OutboxEvent,
        recipient: _RecipientNotification,
    ) -> None:
        notification_id = _stable_uuid("notification", event.tenant_id, event.id, recipient.user_id)
        now = datetime.now(UTC)
        session.add(
            Notification(
                id=notification_id,
                tenant_id=event.tenant_id,
                recipient_user_id=recipient.user_id,
                source_event_id=event.id,
                source_key=event.source_key,
                notification_type=recipient.notification_type,
                title=recipient.title,
                body=recipient.body,
                portal_path=recipient.portal_path,
                read_at=None,
                version=1,
            )
        )
        session.add(
            NotificationDelivery(
                id=_stable_uuid("delivery-in-app", event.tenant_id, event.id, recipient.user_id),
                tenant_id=event.tenant_id,
                notification_id=notification_id,
                source_event_id=event.id,
                recipient_user_id=recipient.user_id,
                channel=NotificationChannel.IN_APP.value,
                status=NotificationDeliveryStatus.DELIVERED.value,
                attempt_count=1,
                next_attempt_at=None,
                delivered_at=now,
                terminal_error_code=None,
                terminal_error_message=None,
                idempotency_key=f"{event.id}:{recipient.user_id}:in_app",
            )
        )
        if recipient.email_enabled:
            session.add(
                NotificationDelivery(
                    id=_stable_uuid("delivery-email", event.tenant_id, event.id, recipient.user_id),
                    tenant_id=event.tenant_id,
                    notification_id=notification_id,
                    source_event_id=event.id,
                    recipient_user_id=recipient.user_id,
                    channel=NotificationChannel.EMAIL.value,
                    status=NotificationDeliveryStatus.PENDING.value,
                    attempt_count=0,
                    next_attempt_at=now,
                    delivered_at=None,
                    terminal_error_code=None,
                    terminal_error_message=None,
                    idempotency_key=f"{event.id}:{recipient.user_id}:email",
                )
            )

    async def _deliver_email(
        self,
        tenant_id: UUID,
        *,
        event_types: tuple[str, ...],
    ) -> int:
        processed = 0
        for _ in range(self.settings.notification_worker_delivery_batch_size):
            handled, claim = await self._claim_email_delivery(
                tenant_id,
                event_types=event_types,
            )
            if not handled:
                break
            processed += 1
            if claim is not None:
                await self._send_and_finalize(claim)
        return processed

    async def _claim_email_delivery(
        self,
        tenant_id: UUID,
        *,
        event_types: tuple[str, ...],
    ) -> tuple[bool, _ClaimedEmailDelivery | None]:
        async with self.session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                now = datetime.now(UTC)
                delivery = await session.scalar(
                    select(NotificationDelivery)
                    .where(
                        NotificationDelivery.tenant_id == tenant_id,
                        NotificationDelivery.channel == NotificationChannel.EMAIL.value,
                        NotificationDelivery.status.in_(
                            (
                                NotificationDeliveryStatus.PENDING.value,
                                NotificationDeliveryStatus.RETRY.value,
                            )
                        ),
                        or_(
                            NotificationDelivery.next_attempt_at.is_(None),
                            NotificationDelivery.next_attempt_at <= now,
                        ),
                        or_(
                            NotificationDelivery.lease_id.is_(None),
                            NotificationDelivery.lease_expires_at <= now,
                        ),
                        exists(
                            select(OutboxEvent.id).where(
                                OutboxEvent.tenant_id == NotificationDelivery.tenant_id,
                                OutboxEvent.id == NotificationDelivery.source_event_id,
                                OutboxEvent.event_type.in_(event_types),
                            )
                        ),
                    )
                    .order_by(NotificationDelivery.next_attempt_at, NotificationDelivery.id)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                if delivery is None:
                    return False, None
                delivery.lease_id = None
                delivery.lease_expires_at = None
                delivery.lease_attempt = None
                if delivery.attempt_count >= self.settings.notification_worker_max_attempts:
                    await self._record_failure(
                        session,
                        delivery,
                        delivery.attempt_count,
                        EmailDeliveryError("provider_unavailable"),
                    )
                    return True, None
                attempt = delivery.attempt_count + 1
                delivery.attempt_count = attempt
                delivery.updated_at = now
                message = await self._prepare_email_message(session, delivery)
                if isinstance(message, EmailDeliveryError):
                    await self._record_failure(session, delivery, attempt, message)
                    return True, None
                lease_id = uuid4()
                delivery.lease_id = lease_id
                delivery.lease_expires_at = now + _DELIVERY_LEASE_DURATION
                delivery.lease_attempt = attempt
                await session.flush()
                return (
                    True,
                    _ClaimedEmailDelivery(
                        tenant_id=tenant_id,
                        delivery_id=delivery.id,
                        lease_id=lease_id,
                        attempt_number=attempt,
                        message=message,
                    ),
                )

    async def _prepare_email_message(
        self,
        session: AsyncSession,
        delivery: NotificationDelivery,
    ) -> EmailMessage | EmailDeliveryError:
        row = (
            await session.execute(
                select(Notification, User)
                .join(
                    User,
                    and_(
                        User.tenant_id == Notification.tenant_id,
                        User.id == Notification.recipient_user_id,
                    ),
                )
                .where(
                    Notification.tenant_id == delivery.tenant_id,
                    Notification.id == delivery.notification_id,
                    or_(
                        and_(
                            Notification.notification_type == "initial_admin_invitation",
                            User.status == UserStatus.INVITED.value,
                        ),
                        and_(
                            Notification.notification_type != "initial_admin_invitation",
                            User.status == UserStatus.ACTIVE.value,
                        ),
                    ),
                )
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            return EmailDeliveryError("recipient_unavailable")
        notification, user = row
        prepared = delivery.prepared_recipient_email is not None
        activation_id = delivery.prepared_activation_id
        if notification.notification_type == "initial_admin_invitation":
            invitation_event = await session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.tenant_id == delivery.tenant_id,
                    OutboxEvent.id == delivery.source_event_id,
                )
            )
            invitation = (
                _initial_admin_invitation(invitation_event)
                if invitation_event is not None
                else None
            )
            if invitation is None or invitation[0] != delivery.recipient_user_id:
                return EmailDeliveryError("recipient_unavailable")
            if is_manual_activation_delivery_event(delivery.source_event_id, invitation[1]):
                return EmailDeliveryError("recipient_unavailable")
            activation = await session.scalar(
                select(UserActivationToken)
                .where(
                    UserActivationToken.tenant_id == delivery.tenant_id,
                    UserActivationToken.id == invitation[1],
                    UserActivationToken.user_id == delivery.recipient_user_id,
                    UserActivationToken.consumed_at.is_(None),
                    UserActivationToken.revoked_at.is_(None),
                )
                .with_for_update()
            )
            if activation is None:
                return EmailDeliveryError("recipient_unavailable")
            if self._activation_delivery_tokens is None:
                return EmailDeliveryError("provider_unavailable")
            token = self._activation_delivery_tokens.issue(
                delivery.tenant_id,
                activation.id,
            )
            if activation.token_hash == token.token_hash:
                activation_expires_at = activation.expires_at
                if activation_expires_at.tzinfo is None:
                    activation_expires_at = activation_expires_at.replace(tzinfo=UTC)
                if activation_expires_at <= datetime.now(UTC):
                    return EmailDeliveryError("recipient_unavailable")
            if not prepared:
                if activation.token_hash != token.token_hash:
                    activation.token_hash = token.token_hash
                    activation.expires_at = datetime.now(UTC) + timedelta(
                        hours=self.settings.auth_activation_token_ttl_hours
                    )
            elif activation.token_hash != token.token_hash:
                return EmailDeliveryError("provider_unavailable")
            if not prepared:
                delivery.prepared_activation_id = activation.id
                activation_id = activation.id
            elif activation_id != activation.id:
                return EmailDeliveryError("provider_unavailable")
        elif activation_id is not None:
            return EmailDeliveryError("provider_unavailable")

        if not prepared:
            delivery.prepared_recipient_email = user.email
            delivery.prepared_subject = notification.title
            delivery.prepared_body_prefix = f"{notification.body} Open the HR portal: "
            delivery.prepared_frontend_base_url = self.settings.frontend_base_url
            delivery.prepared_portal_path = notification.portal_path
            delivery.prepared_message_id = self._prepare_message_id(delivery.id)

        if (
            delivery.prepared_recipient_email is None
            or delivery.prepared_subject is None
            or delivery.prepared_body_prefix is None
            or delivery.prepared_frontend_base_url is None
            or delivery.prepared_portal_path is None
            or delivery.prepared_message_id is None
        ):  # pragma: no cover - protected by the prepared-message constraint
            return EmailDeliveryError("provider_unavailable")
        if (
            activation_id is not None
            and self.settings.environment in {"staging", "prod"}
            and urlsplit(delivery.prepared_frontend_base_url).scheme != "https"
        ):
            return EmailDeliveryError("provider_unavailable")

        portal_url = f"{delivery.prepared_frontend_base_url}{delivery.prepared_portal_path}"
        if activation_id is not None:
            if self._activation_delivery_tokens is None:
                return EmailDeliveryError("provider_unavailable")
            token = self._activation_delivery_tokens.issue(
                delivery.tenant_id,
                activation_id,
            )
            portal_url = f"{portal_url}#token={quote(token.raw_token, safe='.-_')}"
        return EmailMessage(
            tenant_id=delivery.tenant_id,
            delivery_id=delivery.id,
            recipient_user_id=delivery.recipient_user_id,
            recipient_email=delivery.prepared_recipient_email,
            subject=delivery.prepared_subject,
            body=f"{delivery.prepared_body_prefix}{portal_url}",
            portal_url=portal_url,
            idempotency_key=delivery.idempotency_key,
            attempt_number=delivery.attempt_count,
            message_id=delivery.prepared_message_id,
        )

    async def _send_and_finalize(self, claim: _ClaimedEmailDelivery) -> None:
        error: EmailDeliveryError | None = None
        async with self.session_factory() as provider_session:
            configure_tenant_database_access(provider_session, claim.tenant_id)
            provider = self._provider(provider_session)
            try:
                await provider.send(claim.message)
                await provider_session.commit()
            except EmailDeliveryError as exc:
                error = exc
                await provider_session.rollback()
            except BaseException:
                await provider_session.rollback()
                raise
        await self._finalize_email_delivery(claim, error=error)

    async def _finalize_email_delivery(
        self,
        claim: _ClaimedEmailDelivery,
        *,
        error: EmailDeliveryError | None,
    ) -> bool:
        async with self.session_factory() as session:
            configure_tenant_database_access(session, claim.tenant_id)
            async with session.begin():
                delivery = await session.scalar(
                    select(NotificationDelivery)
                    .where(
                        NotificationDelivery.tenant_id == claim.tenant_id,
                        NotificationDelivery.id == claim.delivery_id,
                        NotificationDelivery.channel == NotificationChannel.EMAIL.value,
                        NotificationDelivery.status.in_(
                            (
                                NotificationDeliveryStatus.PENDING.value,
                                NotificationDeliveryStatus.RETRY.value,
                            )
                        ),
                        NotificationDelivery.lease_id == claim.lease_id,
                        NotificationDelivery.lease_attempt == claim.attempt_number,
                        NotificationDelivery.attempt_count == claim.attempt_number,
                    )
                    .with_for_update()
                )
                if delivery is None:
                    return False
                delivery.lease_id = None
                delivery.lease_expires_at = None
                delivery.lease_attempt = None
                if error is not None:
                    await self._record_failure(
                        session,
                        delivery,
                        claim.attempt_number,
                        error,
                    )
                    return True
                now = datetime.now(UTC)
                delivery.status = NotificationDeliveryStatus.DELIVERED.value
                delivery.attempt_count = claim.attempt_number
                delivery.next_attempt_at = None
                delivery.delivered_at = now
                delivery.terminal_error_code = None
                delivery.terminal_error_message = None
                delivery.updated_at = now
                return True

    async def _record_failure(
        self,
        session: AsyncSession,
        delivery: NotificationDelivery,
        attempt: int,
        error: EmailDeliveryError,
    ) -> None:
        now = datetime.now(UTC)
        delivery.attempt_count = attempt
        delivery.lease_id = None
        delivery.lease_expires_at = None
        delivery.lease_attempt = None
        delivery.updated_at = now
        if attempt < self.settings.notification_worker_max_attempts:
            delay = min(
                self.settings.notification_worker_backoff_base_seconds * (2 ** (attempt - 1)),
                self.settings.notification_worker_backoff_max_seconds,
            )
            delivery.status = NotificationDeliveryStatus.RETRY.value
            delivery.next_attempt_at = now + timedelta(seconds=delay)
            return
        delivery.status = NotificationDeliveryStatus.FAILED.value
        delivery.next_attempt_at = None
        delivery.terminal_error_code = error.code
        delivery.terminal_error_message = error.safe_message
        await SqlAlchemyAuditRecorder(session).record(
            AuditEventDraft(
                scope_type=AuditScopeType.TENANT,
                tenant_id=delivery.tenant_id,
                actor_type=AuditActorType.WORKER,
                event_type=AuditEventType.NOTIFICATION_DELIVERY_FAILED,
                category=AuditCategory.HR_OPERATIONS,
                resource_type="notification_delivery",
                resource_id=delivery.id,
                action="terminal_failure",
                result=AuditResult.FAILURE,
                changed_fields=("status", "attempt_count"),
                metadata={
                    "channel": "email",
                    "delivery_error_code": error.code,
                    "attempt_count": attempt,
                },
                data_classification=AuditDataClassification.HR_METADATA,
                visibility_class=AuditVisibilityClass.HR_OPERATIONS,
                context=AuditContext.internal(),
            )
        )

    def _prepare_message_id(self, delivery_id: UUID) -> str:
        local_part = sha256(str(delivery_id).encode("ascii")).hexdigest()
        from_address = self.settings.notification_smtp_from_address
        sender_domain = (
            from_address.rpartition("@")[2] if from_address is not None else "notifications.local"
        )
        return f"<{local_part}@{sender_domain}>"

    def _provider(self, session: AsyncSession) -> EmailProvider:
        if self.settings.notification_email_backend == "fake":
            return LocalCaptureEmailProvider(
                session,
                failures_before_success=(
                    self.settings.notification_fake_email_failures_before_success
                ),
            )
        if self.settings.notification_email_backend == "smtp":
            host = self.settings.notification_smtp_host
            from_address = self.settings.notification_smtp_from_address
            if host is None or from_address is None:  # pragma: no cover - Settings invariant
                raise RuntimeError("SMTP settings were not validated")
            password = self.settings.notification_smtp_password
            return SmtpEmailProvider(
                host=host,
                port=self.settings.notification_smtp_port,
                from_address=from_address,
                username=self.settings.notification_smtp_username,
                password=password.get_secret_value() if password is not None else None,
                tls_mode=self.settings.notification_smtp_tls_mode,
                timeout_seconds=self.settings.notification_smtp_timeout_seconds,
            )
        return UnavailableEmailProvider()


def _stable_uuid(namespace: str, *values: UUID) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        "wealthy-falcon:" + namespace + ":" + ":".join(str(value) for value in values),
    )


def _initial_admin_invitation(event: OutboxEvent) -> tuple[UUID, UUID] | None:
    if event.event_type != "identity.initial_admin_invited":
        return None
    payload = event.payload
    if set(payload) != {"recipient_user_id", "activation_id"}:
        return None
    recipient_value = payload["recipient_user_id"]
    activation_value = payload["activation_id"]
    if not isinstance(recipient_value, str) or not isinstance(activation_value, str):
        return None
    try:
        recipient_user_id = UUID(recipient_value)
        activation_id = UUID(activation_value)
    except ValueError:
        return None
    if (
        recipient_user_id.int == 0
        or activation_id.int == 0
        or recipient_user_id != event.aggregate_id
    ):
        return None
    return recipient_user_id, activation_id


async def run_worker() -> None:
    operational_logger = configure_operational_logger()
    try:
        settings = get_settings()
    except Exception as exc:
        log_worker_failed(
            operational_logger,
            worker="notifications",
            error=exc,
        )
        raise
    log_worker_started(
        operational_logger,
        service=settings.app_name,
        version=settings.app_version,
        commit_sha=settings.release_commit_sha,
        worker="notifications",
    )
    try:
        last_heartbeat_at = monotonic()
        aggregate_processed_count = 0
        runtime = create_database_runtime(settings)
        try:
            worker = NotificationWorker(
                session_factory=runtime.session_factory,
                settings=settings,
            )
            while True:
                cycle_started_at = monotonic()
                processed_count = await worker.run_once()
                cycle_finished_at = monotonic()
                cycle_duration_ms = max(
                    0.0,
                    (cycle_finished_at - cycle_started_at) * 1000,
                )
                aggregate_processed_count += processed_count
                if (
                    cycle_finished_at - last_heartbeat_at
                    >= settings.worker_heartbeat_interval_seconds
                ):
                    log_worker_heartbeat(
                        operational_logger,
                        service=settings.app_name,
                        version=settings.app_version,
                        commit_sha=settings.release_commit_sha,
                        worker="notifications",
                        cycle_duration_ms=cycle_duration_ms,
                        processed_count=aggregate_processed_count,
                    )
                    aggregate_processed_count = 0
                    last_heartbeat_at = monotonic()
                await asyncio.sleep(settings.notification_worker_poll_seconds)
        finally:
            await runtime.dispose()
    except Exception as exc:
        log_worker_failed(
            operational_logger,
            worker="notifications",
            error=exc,
        )
        raise
    finally:
        log_worker_stopped(
            operational_logger,
            service=settings.app_name,
            version=settings.app_version,
            commit_sha=settings.release_commit_sha,
            worker="notifications",
        )


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()


__all__ = ["NotificationWorker", "main", "run_worker"]
