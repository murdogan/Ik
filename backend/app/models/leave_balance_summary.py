from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class LeaveBalanceSummary(Base, TimestampMixin):
    __tablename__ = "leave_balance_summaries"
    __table_args__ = (
        CheckConstraint(
            "period_year >= 1900 and period_year <= 2200",
            name="ck_leave_balance_summaries_period_year",
        ),
        CheckConstraint(
            "opening_balance_days >= 0",
            name="ck_leave_balance_summaries_opening_non_negative",
        ),
        CheckConstraint("used_days >= 0", name="ck_leave_balance_summaries_used_non_negative"),
        CheckConstraint(
            "planned_days >= 0",
            name="ck_leave_balance_summaries_planned_non_negative",
        ),
        UniqueConstraint(
            "tenant_id",
            "employee_id",
            "leave_type",
            "period_year",
            name="uq_leave_balance_summaries_tenant_employee_type_period",
        ),
        Index(
            "ix_leave_balance_summaries_tenant_employee_period",
            "tenant_id",
            "employee_id",
            "period_year",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_leave_balance_summaries_tenant_employee_id_employees",
            ondelete="CASCADE",
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
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    opening_balance_days: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    used_days: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    planned_days: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    @property
    def remaining_days(self) -> float:
        return self.opening_balance_days - self.used_days - self.planned_days
