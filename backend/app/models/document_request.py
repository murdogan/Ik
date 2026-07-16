"""Fixed employee-to-HR requests for HR-produced documents."""

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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EmployeeDocumentRequestType(StrEnum):
    EMPLOYMENT_LETTER = "employment_letter"


class EmployeeDocumentRequestStatus(StrEnum):
    SUBMITTED = "submitted"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class EmployeeDocumentRequest(Base, TimestampMixin):
    __tablename__ = "employee_document_requests"
    __table_args__ = (
        CheckConstraint(
            "request_type = 'employment_letter'",
            name="ck_employee_document_requests_type",
        ),
        CheckConstraint(
            "status in ('submitted','resolved','rejected')",
            name="ck_employee_document_requests_status",
        ),
        CheckConstraint("version > 0", name="ck_employee_document_requests_version_positive"),
        CheckConstraint(
            "(status = 'submitted' and decided_at is null and decided_by_user_id is null "
            "and resolution_reason is null) or "
            "(status in ('resolved','rejected') and decided_at is not null "
            "and decided_by_user_id is not null and resolution_reason is not null "
            "and length(trim(resolution_reason)) > 0)",
            name="ck_employee_document_requests_lifecycle",
        ),
        UniqueConstraint(
            "tenant_id", "id", name="uq_employee_document_requests_tenant_id_id"
        ),
        ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_employee_document_requests_tenant_employee",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "requester_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_employee_document_requests_tenant_requester_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "requester_membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            name="fk_employee_document_requests_tenant_requester_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "decided_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_employee_document_requests_tenant_decider_user",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_employee_document_requests_own_cursor",
            "tenant_id",
            "requester_user_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_employee_document_requests_hr_queue",
            "tenant_id",
            "status",
            "created_at",
            "id",
        ),
        {"implicit_returning": False},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id", name="fk_employee_document_requests_tenant", ondelete="CASCADE"
        ),
        nullable=False,
    )
    employee_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    requester_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    requester_membership_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    request_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EmployeeDocumentRequestStatus.SUBMITTED.value
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __mapper_args__ = {"version_id_col": version}


class EmployeeDocumentRequestTimeline(Base):
    __tablename__ = "employee_document_request_timeline"
    __table_args__ = (
        CheckConstraint(
            "event_type in ('submitted','resolved','rejected')",
            name="ck_employee_document_request_timeline_event",
        ),
        CheckConstraint(
            "event_type = status",
            name="ck_employee_document_request_timeline_status",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "request_id"),
            ("employee_document_requests.tenant_id", "employee_document_requests.id"),
            name="fk_employee_document_request_timeline_tenant_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "actor_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_employee_document_request_timeline_tenant_actor",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id", "source_key", name="uq_employee_document_request_timeline_source"
        ),
        Index(
            "ix_employee_document_request_timeline_request",
            "tenant_id",
            "request_id",
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    request_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_key: Mapped[str] = mapped_column(String(160), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = [
    "EmployeeDocumentRequest",
    "EmployeeDocumentRequestStatus",
    "EmployeeDocumentRequestTimeline",
    "EmployeeDocumentRequestType",
]
