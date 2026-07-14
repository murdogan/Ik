"""Strongly typed employee-owned personal-profile change requests."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EmployeeProfileChangeRequestStatus(StrEnum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class EmployeeProfileChangeRequest(Base, TimestampMixin):
    """One immutable-after-decision request for the three P4E personal fields."""

    __tablename__ = "employee_profile_change_requests"
    __table_args__ = (
        CheckConstraint(
            "status in ('submitted','approved','rejected','cancelled')",
            name="ck_employee_profile_change_requests_status",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_employee_profile_change_requests_version_positive",
        ),
        CheckConstraint(
            "base_profile_version > 0",
            name="ck_employee_profile_change_requests_base_version_positive",
        ),
        CheckConstraint(
            "preferred_name_changed or phone_changed or birth_date_changed",
            name="ck_employee_profile_change_requests_has_change",
        ),
        CheckConstraint(
            "(preferred_name_changed and previous_preferred_name is distinct from "
            "proposed_preferred_name) or (not preferred_name_changed and "
            "previous_preferred_name is null and proposed_preferred_name is null)",
            name="ck_employee_profile_change_requests_preferred_snapshot",
        ),
        CheckConstraint(
            "(phone_changed and previous_phone is distinct from proposed_phone) or "
            "(not phone_changed and previous_phone is null and proposed_phone is null)",
            name="ck_employee_profile_change_requests_phone_snapshot",
        ),
        CheckConstraint(
            "(birth_date_changed and previous_birth_date is distinct from proposed_birth_date) "
            "or (not birth_date_changed and previous_birth_date is null and "
            "proposed_birth_date is null)",
            name="ck_employee_profile_change_requests_birth_snapshot",
        ),
        CheckConstraint(
            "(decided_at is null or decided_at >= submitted_at) and "
            "(cancelled_at is null or cancelled_at >= submitted_at)",
            name="ck_employee_profile_change_requests_timestamp_order",
        ),
        CheckConstraint(
            "(status = 'submitted' and decided_at is null and cancelled_at is null "
            "and decided_by_membership_id is null and decided_by_user_id is null "
            "and rejection_reason is null) or "
            "(status = 'approved' and decided_at is not null and cancelled_at is null "
            "and decided_by_membership_id is not null and decided_by_user_id is not null "
            "and rejection_reason is null) or "
            "(status = 'rejected' and decided_at is not null and cancelled_at is null "
            "and decided_by_membership_id is not null and decided_by_user_id is not null "
            "and rejection_reason is not null and length(trim(rejection_reason)) > 0) or "
            "(status = 'cancelled' and decided_at is null and cancelled_at is not null "
            "and decided_by_membership_id is null and decided_by_user_id is null "
            "and rejection_reason is null)",
            name="ck_employee_profile_change_requests_state",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_employee_profile_change_requests_tenant_id_id",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_epcr_tenant_employee_employees",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "requester_membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            name="fk_epcr_requester_membership_memberships",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "requester_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_epcr_requester_user_users",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "decided_by_membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            name="fk_epcr_decider_membership_memberships",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "decided_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_epcr_decider_user_users",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_employee_profile_change_requests_active_employee",
            "tenant_id",
            "employee_id",
            unique=True,
            postgresql_where=text("status = 'submitted'"),
            sqlite_where=text("status = 'submitted'"),
        ),
        Index(
            "ix_employee_profile_change_requests_tenant_queue_cursor",
            "tenant_id",
            "status",
            "submitted_at",
            "id",
        ),
        Index(
            "ix_employee_profile_change_requests_own_cursor",
            "tenant_id",
            "employee_id",
            "requester_membership_id",
            "submitted_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_employee_profile_change_requests_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    employee_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    requester_membership_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    requester_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=EmployeeProfileChangeRequestStatus.SUBMITTED.value,
        server_default=EmployeeProfileChangeRequestStatus.SUBMITTED.value,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    base_profile_version: Mapped[int] = mapped_column(Integer, nullable=False)

    preferred_name_changed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    previous_preferred_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    proposed_preferred_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone_changed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    previous_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    proposed_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    birth_date_changed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    previous_birth_date: Mapped[date | None] = mapped_column(nullable=True)
    proposed_birth_date: Mapped[date | None] = mapped_column(nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_membership_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    decided_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __mapper_args__ = {"version_id_col": version}


__all__ = ["EmployeeProfileChangeRequest", "EmployeeProfileChangeRequestStatus"]
