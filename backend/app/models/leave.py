"""Tenant leave configuration, immutable balance facts, and workflow history."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

_LEAVE_JSON = JSON().with_variant(JSONB(), "postgresql")


class LeaveType(Base, TimestampMixin):
    __tablename__ = "leave_types"
    __table_args__ = (
        CheckConstraint("length(trim(code)) > 0", name="ck_leave_types_code_not_blank"),
        CheckConstraint("code = lower(code)", name="ck_leave_types_code_lowercase"),
        CheckConstraint("length(trim(name)) > 0", name="ck_leave_types_name_not_blank"),
        CheckConstraint("version > 0", name="ck_leave_types_version_positive"),
        UniqueConstraint("tenant_id", "id", name="uq_leave_types_tenant_id_id"),
        UniqueConstraint("tenant_id", "code", name="uq_leave_types_tenant_code"),
        Index("ix_leave_types_tenant_active_code", "tenant_id", "is_active", "code"),
        {"implicit_returning": False},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_leave_types_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class HolidayCalendar(Base, TimestampMixin):
    __tablename__ = "holiday_calendars"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_holiday_calendars_name_not_blank"),
        CheckConstraint(
            "not is_default or is_active",
            name="ck_holiday_calendars_default_active",
        ),
        CheckConstraint("version > 0", name="ck_holiday_calendars_version_positive"),
        UniqueConstraint("tenant_id", "id", name="uq_holiday_calendars_tenant_id_id"),
        Index(
            "uq_holiday_calendars_tenant_default",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_default AND is_active"),
            sqlite_where=text("is_default = 1 AND is_active = 1"),
        ),
        Index(
            "ix_holiday_calendars_tenant_active_name",
            "tenant_id",
            "is_active",
            "name",
        ),
        {"implicit_returning": False},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_holiday_calendars_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    non_working_weekdays: Mapped[list[int]] = mapped_column(
        _LEAVE_JSON,
        nullable=False,
        default=lambda: [5, 6],
        server_default=text("'[5, 6]'"),
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class HolidayEntry(Base, TimestampMixin):
    __tablename__ = "holiday_entries"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_holiday_entries_name_not_blank"),
        CheckConstraint("version > 0", name="ck_holiday_entries_version_positive"),
        UniqueConstraint("tenant_id", "id", name="uq_holiday_entries_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "calendar_id",
            "holiday_date",
            name="uq_holiday_entries_tenant_calendar_date",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "calendar_id"),
            ("holiday_calendars.tenant_id", "holiday_calendars.id"),
            name="fk_holiday_entries_tenant_calendar",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_holiday_entries_tenant_calendar_date",
            "tenant_id",
            "calendar_id",
            "holiday_date",
            "is_active",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_holiday_entries_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    calendar_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class LeavePolicy(Base):
    """One immutable effective-dated policy version."""

    __tablename__ = "leave_policies"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_leave_policies_version_positive"),
        CheckConstraint(
            "accrual_days_per_month >= 0 and accrual_days_per_month <= 31",
            name="ck_leave_policies_accrual_range",
        ),
        CheckConstraint(
            "(accrual_enabled and accrual_days_per_month > 0) or "
            "(not accrual_enabled and accrual_days_per_month = 0)",
            name="ck_leave_policies_accrual_coherence",
        ),
        CheckConstraint(
            "carryover_limit_days is null or "
            "(carryover_limit_days >= 0 and carryover_limit_days <= 366)",
            name="ck_leave_policies_carryover_range",
        ),
        CheckConstraint(
            "carryover_enabled or carryover_limit_days is null",
            name="ck_leave_policies_carryover_coherence",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_leave_policies_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "leave_type_id",
            "id",
            name="uq_leave_policies_tenant_type_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "leave_type_id",
            "version",
            name="uq_leave_policies_tenant_type_version",
        ),
        UniqueConstraint(
            "tenant_id",
            "leave_type_id",
            "effective_from",
            name="uq_leave_policies_tenant_type_effective",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "leave_type_id"),
            ("leave_types.tenant_id", "leave_types.id"),
            name="fk_leave_policies_tenant_leave_type",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "created_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_leave_policies_tenant_created_by_user",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_leave_policies_tenant_type_effective",
            "tenant_id",
            "leave_type_id",
            "effective_from",
        ),
        {"implicit_returning": False},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_leave_policies_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    leave_type_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    paid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    document_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    negative_balance_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    accrual_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    accrual_days_per_month: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=Decimal("0")
    )
    carryover_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    carryover_limit_days: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class LeaveBalanceLedger(Base):
    """Append-only balance fact; releases are compensating entries."""

    __tablename__ = "leave_balance_ledger"
    __table_args__ = (
        CheckConstraint(
            "period_year >= 1900 and period_year <= 2200",
            name="ck_leave_balance_ledger_period_year",
        ),
        CheckConstraint(
            "entry_type in "
            "('earned','adjustment','planned','planned_release','used','used_release')",
            name="ck_leave_balance_ledger_entry_type",
        ),
        CheckConstraint("amount_days <> 0", name="ck_leave_balance_ledger_amount_nonzero"),
        CheckConstraint(
            "(entry_type in ('earned','planned','used') and amount_days > 0) or "
            "(entry_type in ('planned_release','used_release') and amount_days < 0) or "
            "(entry_type = 'adjustment' and amount_days <> 0)",
            name="ck_leave_balance_ledger_amount_direction",
        ),
        CheckConstraint(
            "(entry_type = 'adjustment' and reason is not null and length(trim(reason)) > 0) "
            "or (entry_type <> 'adjustment' and reason is null)",
            name="ck_leave_balance_ledger_adjustment_reason",
        ),
        CheckConstraint(
            "(entry_type in ('planned_release','used_release') "
            "and reversal_of_entry_id is not null) "
            "or (entry_type not in ('planned_release','used_release') "
            "and reversal_of_entry_id is null)",
            name="ck_leave_balance_ledger_reversal_link",
        ),
        CheckConstraint(
            "length(trim(source_type)) > 0 and length(trim(source_key)) > 0",
            name="ck_leave_balance_ledger_source_not_blank",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_leave_balance_ledger_tenant_id_id"),
        UniqueConstraint(
            "tenant_id", "source_key", name="uq_leave_balance_ledger_tenant_source_key"
        ),
        UniqueConstraint(
            "tenant_id",
            "reversal_of_entry_id",
            name="uq_leave_balance_ledger_tenant_reversal",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_leave_balance_ledger_tenant_employee",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "leave_type_id"),
            ("leave_types.tenant_id", "leave_types.id"),
            name="fk_leave_balance_ledger_tenant_leave_type",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "request_id"),
            ("leave_requests.tenant_id", "leave_requests.id"),
            name="fk_leave_balance_ledger_tenant_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "reversal_of_entry_id"),
            ("leave_balance_ledger.tenant_id", "leave_balance_ledger.id"),
            name="fk_leave_balance_ledger_tenant_reversal",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "created_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_leave_balance_ledger_tenant_created_by_user",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_leave_balance_ledger_tenant_employee_period_type",
            "tenant_id",
            "employee_id",
            "period_year",
            "leave_type_id",
            "created_at",
            "id",
        ),
        Index("ix_leave_balance_ledger_tenant_request", "tenant_id", "request_id"),
        Index(
            "ix_leave_balance_ledger_tenant_created_cursor",
            "tenant_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_leave_balance_ledger_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    employee_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    leave_type_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_days: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source_key: Mapped[str] = mapped_column(String(160), nullable=False)
    reversal_of_entry_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class LeaveRequestDay(Base):
    __tablename__ = "leave_request_days"
    __table_args__ = (
        CheckConstraint(
            "counted_days >= 0 and counted_days <= 1",
            name="ck_leave_request_days_counted_range",
        ),
        CheckConstraint(
            "not is_holiday or counted_days = 0",
            name="ck_leave_request_days_holiday_not_counted",
        ),
        CheckConstraint(
            "is_working_day or counted_days = 0",
            name="ck_leave_request_days_nonworking_not_counted",
        ),
        CheckConstraint(
            "(is_holiday and holiday_entry_id is not null) or "
            "(not is_holiday and holiday_entry_id is null)",
            name="ck_leave_request_days_holiday_link",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_leave_request_days_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "request_id",
            "leave_date",
            name="uq_leave_request_days_tenant_request_date",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "request_id"),
            ("leave_requests.tenant_id", "leave_requests.id"),
            name="fk_leave_request_days_tenant_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "holiday_entry_id"),
            ("holiday_entries.tenant_id", "holiday_entries.id"),
            name="fk_leave_request_days_tenant_holiday_entry",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_leave_request_days_tenant_date_request",
            "tenant_id",
            "leave_date",
            "request_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_leave_request_days_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    request_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    leave_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_working_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_holiday: Mapped[bool] = mapped_column(Boolean, nullable=False)
    counted_days: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    holiday_entry_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class LeaveRequestTimeline(Base):
    __tablename__ = "leave_request_timeline"
    __table_args__ = (
        CheckConstraint(
            "event_type in ('submitted','approved','rejected','cancelled')",
            name="ck_leave_request_timeline_event_type",
        ),
        CheckConstraint(
            "(event_type = 'submitted' and status = 'pending') or "
            "(event_type in ('approved','rejected','cancelled') and event_type = status)",
            name="ck_leave_request_timeline_event_status",
        ),
        CheckConstraint(
            "length(trim(source_key)) > 0",
            name="ck_leave_request_timeline_source_key_not_blank",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_leave_request_timeline_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "source_key",
            name="uq_leave_request_timeline_tenant_source_key",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "request_id"),
            ("leave_requests.tenant_id", "leave_requests.id"),
            name="fk_leave_request_timeline_tenant_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "actor_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_leave_request_timeline_tenant_actor_user",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_leave_request_timeline_tenant_request_occurred",
            "tenant_id",
            "request_id",
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_leave_request_timeline_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    request_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_key: Mapped[str] = mapped_column(String(160), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboxEvent(Base):
    """Immutable, redacted fact for a future Phase 7 delivery worker."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint(
            "event_type in "
            "('leave.requested','leave.approved','leave.rejected','leave.cancelled',"
            "'leave.balance_adjusted','announcement.published')",
            name="ck_outbox_events_event_type",
        ),
        CheckConstraint(
            "length(trim(aggregate_type)) > 0 and length(trim(source_key)) > 0",
            name="ck_outbox_events_fact_not_blank",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_outbox_events_tenant_id_id"),
        UniqueConstraint("tenant_id", "source_key", name="uq_outbox_events_tenant_source_key"),
        Index(
            "ix_outbox_events_tenant_created",
            "tenant_id",
            "created_at",
            "id",
        ),
        Index("ix_outbox_events_event_created", "event_type", "created_at", "id"),
        {"implicit_returning": False},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_outbox_events_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(96), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(_LEAVE_JSON, nullable=False)
    source_key: Mapped[str] = mapped_column(String(160), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


__all__ = [
    "HolidayCalendar",
    "HolidayEntry",
    "LeaveBalanceLedger",
    "LeavePolicy",
    "LeaveRequestDay",
    "LeaveRequestTimeline",
    "LeaveType",
    "OutboxEvent",
]
