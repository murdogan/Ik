"""User inbox, immutable outbox consumption, channel delivery, and local email capture."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"


class NotificationDeliveryStatus(StrEnum):
    PENDING = "pending"
    RETRY = "retry"
    DELIVERED = "delivered"
    FAILED = "failed"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_notifications_version_positive"),
        CheckConstraint("length(trim(notification_type)) > 0", name="ck_notifications_type"),
        CheckConstraint("length(trim(title)) > 0", name="ck_notifications_title"),
        CheckConstraint(
            "portal_path like '/%' and portal_path not like '//%'",
            name="ck_notifications_safe_portal_path",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "recipient_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_notifications_tenant_recipient_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "source_event_id"),
            ("outbox_events.tenant_id", "outbox_events.id"),
            name="fk_notifications_tenant_source_event",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_notifications_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "source_event_id",
            "recipient_user_id",
            name="uq_notifications_event_recipient",
        ),
        Index(
            "ix_notifications_recipient_cursor",
            "tenant_id",
            "recipient_user_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_notifications_recipient_unread",
            "tenant_id",
            "recipient_user_id",
            "read_at",
            "created_at",
            "id",
        ),
        {"implicit_returning": False},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_notifications_tenant", ondelete="CASCADE"),
        nullable=False,
    )
    recipient_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_key: Mapped[str] = mapped_column(String(160), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(96), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    portal_path: Mapped[str] = mapped_column(String(500), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __mapper_args__ = {"version_id_col": version}


class OutboxEventConsumption(Base):
    """Append-only marker proving that one immutable outbox fact was expanded once."""

    __tablename__ = "outbox_event_consumptions"
    __table_args__ = (
        CheckConstraint(
            "outcome in ('processed','skipped')",
            name="ck_outbox_event_consumptions_outcome",
        ),
        CheckConstraint(
            "recipient_count >= 0 and recipient_count <= 500",
            name="ck_outbox_event_consumptions_recipient_count",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "source_event_id"),
            ("outbox_events.tenant_id", "outbox_events.id"),
            name="fk_outbox_event_consumptions_tenant_event",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id", "source_event_id", name="uq_outbox_event_consumptions_event"
        ),
        Index(
            "ix_outbox_event_consumptions_tenant_created",
            "tenant_id",
            "created_at",
            "source_event_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id", name="fk_outbox_event_consumptions_tenant", ondelete="CASCADE"
        ),
        nullable=False,
    )
    source_event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        CheckConstraint(
            "channel in ('in_app','email')",
            name="ck_notification_deliveries_channel",
        ),
        CheckConstraint(
            "status in ('pending','retry','delivered','failed')",
            name="ck_notification_deliveries_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 and attempt_count <= 20",
            name="ck_notification_deliveries_attempt_count",
        ),
        CheckConstraint(
            "(status = 'delivered' and delivered_at is not null and next_attempt_at is null "
            "and terminal_error_code is null and terminal_error_message is null) or "
            "(status = 'failed' and delivered_at is null and next_attempt_at is null "
            "and terminal_error_code is not null and terminal_error_message is not null) or "
            "(status in ('pending','retry') and delivered_at is null "
            "and next_attempt_at is not null and terminal_error_code is null "
            "and terminal_error_message is null)",
            name="ck_notification_deliveries_lifecycle",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "notification_id"),
            ("notifications.tenant_id", "notifications.id"),
            name="fk_notification_deliveries_tenant_notification",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "source_event_id"),
            ("outbox_events.tenant_id", "outbox_events.id"),
            name="fk_notification_deliveries_tenant_source_event",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "recipient_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_notification_deliveries_tenant_recipient_user",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_notification_deliveries_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "source_event_id",
            "recipient_user_id",
            "channel",
            name="uq_notification_deliveries_event_recipient_channel",
        ),
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_notification_deliveries_idempotency"
        ),
        Index(
            "ix_notification_deliveries_due",
            "tenant_id",
            "channel",
            "status",
            "next_attempt_at",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    notification_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    recipient_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminal_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    terminal_error_message: Mapped[str | None] = mapped_column(String(200), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class EmailCapture(Base):
    """Staging/dev-only local adapter output; never exposed by a product API."""

    __tablename__ = "email_captures"
    __table_args__ = (
        CheckConstraint("length(trim(subject)) > 0", name="ck_email_captures_subject"),
        CheckConstraint(
            "portal_url like 'http://%' or portal_url like 'https://%'",
            name="ck_email_captures_portal_url",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "delivery_id"),
            ("notification_deliveries.tenant_id", "notification_deliveries.id"),
            name="fk_email_captures_tenant_delivery",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "recipient_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_email_captures_tenant_recipient_user",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "delivery_id", name="uq_email_captures_delivery"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_email_captures_idempotency"),
        Index(
            "ix_email_captures_tenant_created", "tenant_id", "created_at", "id"
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_email_captures_tenant", ondelete="CASCADE"),
        nullable=False,
    )
    delivery_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    recipient_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    portal_url: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


__all__ = [
    "EmailCapture",
    "Notification",
    "NotificationChannel",
    "NotificationDelivery",
    "NotificationDeliveryStatus",
    "OutboxEventConsumption",
]
