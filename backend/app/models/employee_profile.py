from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EmployeePersonalProfile(Base, TimestampMixin):
    """Focused, non-sensitive employee personal data owned by a tenant."""

    __tablename__ = "employee_profiles"
    __table_args__ = (
        CheckConstraint(
            "version > 0",
            name="ck_employee_profiles_version_positive",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_employee_profiles_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "employee_id",
            name="uq_employee_profiles_tenant_employee_id",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_employee_profiles_tenant_employee_id_employees",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_employee_profiles_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    employee_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    preferred_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    __mapper_args__ = {"version_id_col": version}


class EmployeeEmploymentProfile(Base, TimestampMixin):
    """Focused employee employment presentation data owned by a tenant."""

    __tablename__ = "employee_employments"
    __table_args__ = (
        CheckConstraint(
            "version > 0",
            name="ck_employee_employments_version_positive",
        ),
        CheckConstraint(
            "contract_type is null or contract_type in ('indefinite','fixed_term')",
            name="ck_employee_employments_contract_type",
        ),
        CheckConstraint(
            "work_type is null or work_type in ('full_time','part_time')",
            name="ck_employee_employments_work_type",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_employee_employments_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "employee_id",
            name="uq_employee_employments_tenant_employee_id",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_employee_employments_tenant_employee_id_employees",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_employee_employments_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    employee_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    contract_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    work_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    __mapper_args__ = {"version_id_col": version}
