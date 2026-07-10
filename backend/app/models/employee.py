from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EmployeeStatus(StrEnum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    TERMINATED = "terminated"


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint(
            "status in ('active','on_leave','terminated')",
            name="ck_employees_status",
        ),
        CheckConstraint(
            "employment_end_date is null or employment_end_date >= employment_start_date",
            name="ck_employees_date_order",
        ),
        CheckConstraint(
            "("
            "status = 'terminated' and employment_end_date is not null"
            ") or ("
            "status in ('active','on_leave') and employment_end_date is null"
            ")",
            name="ck_employees_lifecycle_status_dates",
        ),
        UniqueConstraint(
            "tenant_id",
            "employee_number",
            name="uq_employees_tenant_employee_number",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_employees_tenant_id_id"),
        Index("ix_employees_tenant_status", "tenant_id", "status"),
        Index("ix_employees_tenant_archived_at", "tenant_id", "archived_at"),
        Index(
            "ix_employees_tenant_department_normalized",
            "tenant_id",
            "department_normalized",
            postgresql_where=text("archived_at IS NULL"),
        ),
        Index(
            "ix_employees_employee_number_trgm",
            "employee_number",
            postgresql_using="gin",
            postgresql_ops={"employee_number": "gin_trgm_ops"},
            postgresql_where=text("archived_at IS NULL"),
        ),
        Index(
            "ix_employees_email_trgm",
            "email",
            postgresql_using="gin",
            postgresql_ops={"email": "gin_trgm_ops"},
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_number: Mapped[str] = mapped_column(String(64), nullable=False)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    department_normalized: Mapped[str | None] = mapped_column(
        Text,
        Computed("lower(ltrim(rtrim(department)))", persisted=True),
        nullable=True,
    )
    position: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EmployeeStatus.ACTIVE.value
    )
    employment_start_date: Mapped[date] = mapped_column(nullable=False)
    employment_end_date: Mapped[date | None] = mapped_column(nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
