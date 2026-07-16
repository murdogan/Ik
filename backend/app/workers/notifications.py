"""Bounded PostgreSQL outbox expansion and notification email delivery worker."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import create_database_runtime
from app.models.announcement import Announcement, AnnouncementRecipient
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
from app.modules.notifications import (
    EmailDeliveryError,
    EmailMessage,
    EmailProvider,
    LocalCaptureEmailProvider,
    UnavailableEmailProvider,
)
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
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.phase7_access import Phase7FeatureUnavailableError, require_phase7_feature

_EVENT_TYPES = (
    "leave.requested",
    "leave.approved",
    "leave.rejected",
    "leave.cancelled",
    "leave.balance_adjusted",
    "announcement.published",
)
_ANNOUNCEMENT_RECIPIENT_LIMIT = 500
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _RecipientNotification:
    user_id: UUID
    notification_type: str
    title: str
    body: str
    portal_path: str
    email_enabled: bool


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

    async def run_once(self) -> int:
        tenant_ids = await self._discover_tenants()
        processed = 0
        for tenant_id in tenant_ids:
            try:
                processed += await self._process_tenant(tenant_id)
            except Exception as exc:
                _LOGGER.error(
                    "Notification tenant batch failed tenant_id=%s error_class=%s",
                    tenant_id,
                    type(exc).__name__,
                )
        return processed

    async def _discover_tenants(self) -> list[UUID]:
        async with self.session_factory() as session:
            configure_platform_database_access(session)
            async with session.begin():
                statement = select(Tenant.id).where(
                    Tenant.status.in_(("trial", "active"))
                )
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
            try:
                async with session.begin():
                    await require_phase7_feature(
                        session,
                        tenant_id=tenant_id,
                        feature=FeatureFlagKey.NOTIFICATIONS,
                    )
                    expanded = await self._expand_outbox(session, tenant_id)
            except Phase7FeatureUnavailableError:
                return 0
            async with session.begin():
                delivered = await self._deliver_email(session, tenant_id)
        return expanded + delivered

    async def _expand_outbox(self, session: AsyncSession, tenant_id: UUID) -> int:
        events = list(
            await session.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.tenant_id == tenant_id,
                    OutboxEvent.event_type.in_(_EVENT_TYPES),
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

    async def _deliver_email(self, session: AsyncSession, tenant_id: UUID) -> int:
        now = datetime.now(UTC)
        deliveries = list(
            await session.scalars(
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
                )
                .order_by(NotificationDelivery.next_attempt_at, NotificationDelivery.id)
                .limit(self.settings.notification_worker_delivery_batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        provider = self._provider(session)
        for delivery in deliveries:
            await self._attempt_delivery(session, provider, delivery)
        if deliveries:
            await session.flush()
        return len(deliveries)

    async def _attempt_delivery(
        self,
        session: AsyncSession,
        provider: EmailProvider,
        delivery: NotificationDelivery,
    ) -> None:
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
                    User.status == UserStatus.ACTIVE.value,
                )
                .limit(1)
            )
        ).one_or_none()
        attempt = delivery.attempt_count + 1
        if row is None:
            error = EmailDeliveryError("recipient_unavailable")
            await self._record_failure(session, delivery, attempt, error)
            return
        notification, user = row
        portal_url = f"{self.settings.frontend_base_url}{notification.portal_path}"
        message = EmailMessage(
            tenant_id=delivery.tenant_id,
            delivery_id=delivery.id,
            recipient_user_id=delivery.recipient_user_id,
            recipient_email=user.email,
            subject=notification.title,
            body=f"{notification.body} Open the HR portal: {portal_url}",
            portal_url=portal_url,
            idempotency_key=delivery.idempotency_key,
            attempt_number=attempt,
        )
        try:
            await provider.send(message)
        except EmailDeliveryError as error:
            await self._record_failure(session, delivery, attempt, error)
            return
        now = datetime.now(UTC)
        delivery.status = NotificationDeliveryStatus.DELIVERED.value
        delivery.attempt_count = attempt
        delivery.next_attempt_at = None
        delivery.delivered_at = now
        delivery.terminal_error_code = None
        delivery.terminal_error_message = None
        delivery.updated_at = now

    async def _record_failure(
        self,
        session: AsyncSession,
        delivery: NotificationDelivery,
        attempt: int,
        error: EmailDeliveryError,
    ) -> None:
        now = datetime.now(UTC)
        delivery.attempt_count = attempt
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

    def _provider(self, session: AsyncSession) -> EmailProvider:
        if self.settings.notification_email_backend == "fake":
            return LocalCaptureEmailProvider(
                session,
                failures_before_success=(
                    self.settings.notification_fake_email_failures_before_success
                ),
            )
        return UnavailableEmailProvider()


def _stable_uuid(namespace: str, *values: UUID) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        "wealthy-falcon:" + namespace + ":" + ":".join(str(value) for value in values),
    )


async def run_worker() -> None:
    settings = get_settings()
    runtime = create_database_runtime(settings)
    worker = NotificationWorker(session_factory=runtime.session_factory, settings=settings)
    try:
        while True:
            await worker.run_once()
            await asyncio.sleep(settings.notification_worker_poll_seconds)
    finally:
        await runtime.dispose()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()


__all__ = ["NotificationWorker", "main", "run_worker"]
