from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class LeaveRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class LeaveRequest(Base, TimestampMixin):
    __tablename__ = "leave_requests"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending','approved','rejected','cancelled')",
            name="ck_leave_requests_status",
        ),
        CheckConstraint("end_date >= start_date", name="ck_leave_requests_date_order"),
        CheckConstraint(
            "start_date >= '1900-01-01' and end_date <= '2200-12-31'",
            name="ck_leave_requests_supported_dates",
        ),
        CheckConstraint(
            "counted_days >= 0",
            name="ck_leave_requests_counted_days_non_negative",
        ),
        CheckConstraint("version > 0", name="ck_leave_requests_version_positive"),
        CheckConstraint(
            "(status = 'pending' and decided_by_user_id is null and decided_at is null) or "
            "(status <> 'pending' and decided_by_user_id is not null and decided_at is not null)",
            name="ck_leave_requests_decision_state",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_leave_requests_tenant_id_id",
        ),
        Index(
            "ix_leave_requests_tenant_employee_start_date",
            "tenant_id",
            "employee_id",
            "start_date",
        ),
        Index(
            "ix_leave_requests_tenant_status_created_at",
            "tenant_id",
            "status",
            "created_at",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_leave_requests_tenant_employee_id_employees",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "requested_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_leave_requests_tenant_requested_by_user_id_users",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "decided_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_leave_requests_tenant_decided_by_user_id_users",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "leave_type_id"],
            ["leave_types.tenant_id", "leave_types.id"],
            name="fk_leave_requests_tenant_leave_type",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "leave_type_id", "policy_id"],
            [
                "leave_policies.tenant_id",
                "leave_policies.leave_type_id",
                "leave_policies.id",
            ],
            name="fk_leave_requests_tenant_type_policy",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "requested_by_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            name="fk_leave_requests_tenant_requested_by_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "routed_manager_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_leave_requests_tenant_routed_manager_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id", "document_id"],
            [
                "employee_documents.tenant_id",
                "employee_documents.employee_id",
                "employee_documents.id",
            ],
            name="fk_leave_requests_tenant_document",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_leave_requests_tenant_manager_status_created",
            "tenant_id",
            "routed_manager_user_id",
            "status",
            "created_at",
            "id",
        ),
        Index(
            "ix_leave_requests_tenant_employee_status_dates",
            "tenant_id",
            "employee_id",
            "status",
            "start_date",
            "end_date",
        ),
        Index(
            "ix_leave_requests_tenant_type_start",
            "tenant_id",
            "leave_type_id",
            "start_date",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    leave_type: Mapped[str] = mapped_column(String(64), nullable=False)
    leave_type_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    policy_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    start_date: Mapped[date] = mapped_column(nullable=False)
    end_date: Mapped[date] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=LeaveRequestStatus.PENDING.value
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    requested_by_membership_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    routed_manager_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    document_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    employee_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    counted_days: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=0, server_default=text("0")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __mapper_args__ = {"version_id_col": version}


Index(
    "ix_leave_requests_tenant_created_cursor",
    LeaveRequest.tenant_id,
    LeaveRequest.created_at.desc(),
    LeaveRequest.start_date.asc(),
    LeaveRequest.id.asc(),
)
