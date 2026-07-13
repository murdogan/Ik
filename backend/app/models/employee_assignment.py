"""Effective-dated tenant employee organization assignments."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EmployeeAssignment(Base, TimestampMixin):
    """One immutable organization/reporting-line interval in an employee's history.

    Intervals use an exclusive ``effective_to`` boundary. A change closes the prior row at the
    successor's ``effective_from`` and inserts a new open-ended row; structural history is never
    overwritten in place.
    """

    __tablename__ = "employee_assignments"
    __table_args__ = (
        CheckConstraint(
            "effective_to is null or effective_to >= effective_from",
            name="ck_employee_assignments_effective_range",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_employee_assignments_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "supersedes_assignment_id",
            name="uq_employee_assignments_tenant_supersedes_assignment_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_employee_assignments_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_employee_assignments_tenant_employee_id_employees",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "legal_entity_id"],
            ["legal_entities.tenant_id", "legal_entities.id"],
            name="fk_employee_assignments_tenant_legal_entity_id_legal_entities",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "branch_id"],
            ["branches.tenant_id", "branches.id"],
            name="fk_employee_assignments_tenant_branch_id_branches",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["departments.tenant_id", "departments.id"],
            name="fk_employee_assignments_tenant_department_id_departments",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "position_id"],
            ["positions.tenant_id", "positions.id"],
            name="fk_employee_assignments_tenant_position_id_positions",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "manager_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_employee_assignments_tenant_manager_user_id_users",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "created_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_employee_assignments_tenant_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "supersedes_assignment_id"],
            ["employee_assignments.tenant_id", "employee_assignments.id"],
            name="fk_employee_assignments_tenant_supersedes_employee_assignments",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_employee_assignments_tenant_employee_open",
            "tenant_id",
            "employee_id",
            unique=True,
            postgresql_where=text("effective_to IS NULL"),
            sqlite_where=text("effective_to IS NULL"),
        ),
        Index(
            "ix_employee_assignments_tenant_employee_history",
            "tenant_id",
            "employee_id",
            "effective_from",
            "id",
        ),
        Index(
            "ix_employee_assignments_tenant_manager_scope",
            "tenant_id",
            "manager_user_id",
            "effective_from",
            "effective_to",
            "employee_id",
        ),
        Index(
            "ix_employee_assignments_tenant_department_effective",
            "tenant_id",
            "department_id",
            "effective_from",
        ),
        Index(
            "ix_employee_assignments_tenant_branch_effective",
            "tenant_id",
            "branch_id",
            "effective_from",
        ),
        Index(
            "ix_employee_assignments_tenant_legal_entity_effective",
            "tenant_id",
            "legal_entity_id",
            "effective_from",
            "effective_to",
            "employee_id",
        ),
        Index(
            "ix_employee_assignments_tenant_position_effective",
            "tenant_id",
            "position_id",
            "effective_from",
            "effective_to",
            "employee_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    legal_entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    department_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    position_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    manager_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    supersedes_assignment_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    change_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )


__all__ = ["EmployeeAssignment"]
