from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

_NORMALIZATION_WHITESPACE = (
    " \t\n\r\f\v\x1c\x1d\x1e\x1f\u0085\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)


def _normalized_text_sql(column_name: str) -> str:
    return (
        f"lower(ltrim(rtrim({column_name}, '{_NORMALIZATION_WHITESPACE}'), "
        f"'{_NORMALIZATION_WHITESPACE}'))"
    )


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
        CheckConstraint(
            "employee_number_normalized <> ''",
            name="ck_employees_employee_number_not_blank",
        ),
        CheckConstraint(
            "email_normalized is null or email_normalized <> ''",
            name="ck_employees_email_not_blank",
        ),
        CheckConstraint("version > 0", name="ck_employees_version_positive"),
        UniqueConstraint(
            "tenant_id",
            "employee_number",
            name="uq_employees_tenant_employee_number",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_employees_tenant_id_id"),
        Index("ix_employees_tenant_status", "tenant_id", "status"),
        Index("ix_employees_tenant_archived_at", "tenant_id", "archived_at"),
        Index(
            "ix_employees_tenant_directory_cursor",
            "tenant_id",
            "id",
            postgresql_where=text("archived_at IS NULL"),
            sqlite_where=text("archived_at IS NULL"),
        ),
        Index(
            "ix_employees_tenant_status_directory_cursor",
            "tenant_id",
            "status",
            "id",
            postgresql_where=text("archived_at IS NULL"),
            sqlite_where=text("archived_at IS NULL"),
        ),
        Index(
            "uq_employees_tenant_employee_number_normalized",
            "tenant_id",
            "employee_number_normalized",
            unique=True,
        ),
        Index(
            "uq_employees_tenant_email_normalized",
            "tenant_id",
            "email_normalized",
            unique=True,
        ),
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
        Index(
            "ix_employees_full_name_normalized_trgm",
            "full_name_normalized",
            postgresql_using="gin",
            postgresql_ops={"full_name_normalized": "gin_trgm_ops"},
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
    employee_number_normalized: Mapped[str] = mapped_column(
        String(64),
        Computed(_normalized_text_sql("employee_number")),
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    full_name_normalized: Mapped[str] = mapped_column(
        Text,
        Computed(
            f"{_normalized_text_sql('first_name')} || ' ' || "
            f"{_normalized_text_sql('last_name')}"
        ),
        nullable=False,
    )
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_normalized: Mapped[str | None] = mapped_column(
        String(320),
        Computed(
            "case when email is null then null else "
            f"{_normalized_text_sql('email')} end"
        ),
        nullable=True,
    )
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
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    employment_start_date: Mapped[date] = mapped_column(nullable=False)
    employment_end_date: Mapped[date | None] = mapped_column(nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __mapper_args__ = {"version_id_col": version}
