from datetime import date
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
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
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    leave_type: Mapped[str] = mapped_column(String(64), nullable=False)
    start_date: Mapped[date] = mapped_column(nullable=False)
    end_date: Mapped[date] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=LeaveRequestStatus.PENDING.value
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
