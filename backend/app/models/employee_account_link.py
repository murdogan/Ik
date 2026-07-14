"""Canonical tenant employee-to-membership account links."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EmployeeAccountLink(Base, TimestampMixin):
    """The current one-to-one link between an employee and a canonical membership."""

    __tablename__ = "employee_account_links"
    __table_args__ = (
        CheckConstraint(
            "version > 0",
            name="ck_employee_account_links_version_positive",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_employee_account_links_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "employee_id",
            name="uq_employee_account_links_tenant_employee_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "membership_id",
            name="uq_employee_account_links_tenant_membership_id",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_employee_account_links_tenant_employee_id_employees",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            name="fk_employee_account_links_tenant_membership_id_memberships",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_employee_account_links_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    employee_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    membership_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    __mapper_args__ = {"version_id_col": version}


__all__ = ["EmployeeAccountLink"]
