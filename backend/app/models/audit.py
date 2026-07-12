"""Append-only tenant and platform audit-event persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_AUDIT_JSON = JSON().with_variant(JSONB(), "postgresql")


class AuditEvent(Base):
    """One immutable security or administration fact.

    The normal runtime roles receive only ``SELECT`` and ``INSERT`` at the PostgreSQL boundary.
    The ORM intentionally exposes no updated timestamp or mutation-oriented helper.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "(scope_type = 'tenant' and tenant_id is not null) or "
            "(scope_type = 'platform' and tenant_id is null)",
            name="ck_audit_events_scope_tenant",
        ),
        CheckConstraint(
            "scope_type in ('platform','tenant')",
            name="ck_audit_events_scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'platform' and category = 'platform_operations') or "
            "(scope_type = 'tenant' and category <> 'platform_operations')",
            name="ck_audit_events_scope_category",
        ),
        CheckConstraint(
            "actor_type in ('user','system','worker','platform_admin','support_session')",
            name="ck_audit_events_actor_type",
        ),
        CheckConstraint(
            "severity in ('info','warning','critical')",
            name="ck_audit_events_severity",
        ),
        CheckConstraint(
            "result in ('success','failure','denied')",
            name="ck_audit_events_result",
        ),
        Index(
            "ix_audit_events_tenant_occurred_at_id",
            "tenant_id",
            "occurred_at",
            "id",
        ),
        Index(
            "ix_audit_events_tenant_event_occurred_at",
            "tenant_id",
            "event_type",
            "occurred_at",
        ),
        Index(
            "ix_audit_events_tenant_resource_occurred_at",
            "tenant_id",
            "resource_type",
            "resource_id",
            "occurred_at",
        ),
        Index(
            "ix_audit_events_actor_occurred_at",
            "actor_user_id",
            "occurred_at",
        ),
        Index(
            "ix_audit_events_scope_occurred_at_id",
            "scope_type",
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_audit_events_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    impersonator_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(32), nullable=False)
    session_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    support_ticket_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    changed_fields: Mapped[list[str]] = mapped_column(_AUDIT_JSON, nullable=False)
    before_data: Mapped[dict[str, Any]] = mapped_column(_AUDIT_JSON, nullable=False)
    after_data: Mapped[dict[str, Any]] = mapped_column(_AUDIT_JSON, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        _AUDIT_JSON,
        nullable=False,
    )
    data_classification: Mapped[str] = mapped_column(String(64), nullable=False)
    visibility_class: Mapped[str] = mapped_column(String(64), nullable=False)
    integrity_hash: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["AuditEvent"]
