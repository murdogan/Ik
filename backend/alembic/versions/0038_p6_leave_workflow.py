"""P6 tenant leave policies, ledger, and approval workflow.

Revision ID: 0038_p6_leave_workflow
Revises: 0037_p5_employee_documents
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    create_tenant_isolation_policy,
    create_unrestricted_insert_policy,
    disable_forced_row_security,
    enable_forced_row_security,
    grant_column_privilege,
    grant_table_privileges,
    revoke_all_column_privileges,
    revoke_all_table_privileges,
)
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy.dialects import postgresql

revision: str = "0038_p6_leave_workflow"
down_revision: str | None = "0037_p5_employee_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
_TENANT_POLICY = "tenant_isolation_app"
_PLATFORM_BOOTSTRAP_POLICY = "platform_leave_bootstrap_insert"
_IMMUTABILITY_FUNCTION = "prevent_p6_leave_fact_mutation"
_OVERLAP_CONSTRAINT = "ex_leave_requests_tenant_employee_active_overlap"
_LEGACY_MAX_SPAN_DAYS = 3660

_NEW_TABLES = (
    "leave_types",
    "holiday_calendars",
    "holiday_entries",
    "leave_policies",
    "leave_balance_ledger",
    "leave_request_days",
    "leave_request_timeline",
    "outbox_events",
)
_IMMUTABLE_TABLES = (
    "leave_policies",
    "leave_balance_ledger",
    "leave_request_days",
    "leave_request_timeline",
    "outbox_events",
)
_PLATFORM_BOOTSTRAP_TABLES = (
    "leave_types",
    "holiday_calendars",
    "leave_policies",
)
_EXISTING_RLS_SCAN_TABLES = (
    "tenants",
    "users",
    "employees",
    "leave_requests",
    "leave_balance_summaries",
    "tenant_memberships",
    "employee_account_links",
    "employee_assignments",
    "employee_documents",
)

_STARTER_TYPES = (
    ("annual", "Annual leave", True, False),
    ("excuse", "Excuse leave", True, False),
    ("unpaid", "Unpaid leave", False, False),
    ("medical_report", "Medical/report leave", True, True),
)
_CANONICAL_CODES = frozenset(item[0] for item in _STARTER_TYPES)
_POLICY_EFFECTIVE_FROM = date(1900, 1, 1)
_CONFIGURATION_LIMIT = 200

_ROLE_IDS = {
    "hr_director": UUID("d2000000-0000-4000-8000-000000000003"),
    "hr_specialist": UUID("d2000000-0000-4000-8000-000000000004"),
    "manager": UUID("d2000000-0000-4000-8000-000000000007"),
    "employee": UUID("d2000000-0000-4000-8000-000000000008"),
}
_PERMISSIONS = (
    (
        UUID("d3000000-0000-4000-8000-000000000037"),
        "leave:create:own",
        "leave",
        "create",
        "own",
        "Create leave requests for the current employee.",
        ("hr_director", "hr_specialist", "manager", "employee"),
    ),
    (
        UUID("d3000000-0000-4000-8000-000000000038"),
        "leave:cancel:own",
        "leave",
        "cancel",
        "own",
        "Cancel the current employee's leave requests.",
        ("hr_director", "hr_specialist", "manager", "employee"),
    ),
    (
        UUID("d3000000-0000-4000-8000-000000000039"),
        "leave:adjust:tenant",
        "leave",
        "adjust",
        "tenant",
        "Record reason-backed leave balance adjustments across the current tenant.",
        ("hr_director", "hr_specialist"),
    ),
    (
        UUID("d3000000-0000-4000-8000-000000000040"),
        "employee_document:upload:own",
        "employee_document",
        "upload",
        "own",
        "Upload employee documents linked to the current membership.",
        ("hr_director", "hr_specialist", "manager", "employee"),
    ),
)
_OWN_DOCUMENT_READ_PERMISSION_ID = UUID("d3000000-0000-4000-8000-000000000036")
_OWN_DOCUMENT_READ_PERMISSION_CODE = "employee_document:read:own"


def upgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        for table_name in _EXISTING_RLS_SCAN_TABLES:
            disable_forced_row_security(op, table_name=table_name)

    _assert_legacy_preflight()
    _add_document_employee_composite_key()
    _create_configuration_tables()
    _add_request_expansion_columns()
    _create_workflow_fact_tables()
    type_mapping, policy_mapping = _seed_tenant_defaults_and_legacy_types()
    request_facts = _backfill_requests(type_mapping, policy_mapping)
    _backfill_ledger(type_mapping, request_facts)
    _contract_leave_requests()
    _seed_permissions()
    _seed_manager_own_document_read_grant()

    if is_postgresql:
        _create_immutability_triggers()
        _configure_postgresql_security()
        _create_overlap_constraint()
        for table_name in _EXISTING_RLS_SCAN_TABLES:
            enable_forced_row_security(op, table_name=table_name)


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        for table_name in (*_NEW_TABLES, "leave_requests", "employee_documents"):
            disable_forced_row_security(op, table_name=table_name)
    _assert_downgrade_is_safe()

    if is_postgresql:
        op.execute(
            sa.text(
                f'ALTER TABLE "leave_requests" DROP CONSTRAINT IF EXISTS "{_OVERLAP_CONSTRAINT}"'
            )
        )
        _drop_immutability_triggers()
    _remove_manager_own_document_read_grant()
    _remove_permissions()
    for table_name in (
        "outbox_events",
        "leave_request_timeline",
        "leave_request_days",
        "leave_balance_ledger",
    ):
        op.drop_table(table_name)
    _drop_request_expansion()
    _drop_document_employee_composite_key()
    for table_name in (
        "leave_policies",
        "holiday_entries",
        "holiday_calendars",
        "leave_types",
    ):
        op.drop_table(table_name)
    if is_postgresql:
        _restore_legacy_postgresql_security()


def _create_configuration_tables() -> None:
    op.create_table(
        "leave_types",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(code)) > 0", name="ck_leave_types_code_not_blank"),
        sa.CheckConstraint("code = lower(code)", name="ck_leave_types_code_lowercase"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_leave_types_name_not_blank"),
        sa.CheckConstraint("version > 0", name="ck_leave_types_version_positive"),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_leave_types_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_leave_types"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_leave_types_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_leave_types_tenant_code"),
    )
    op.create_index(
        "ix_leave_types_tenant_active_code",
        "leave_types",
        ("tenant_id", "is_active", "code"),
    )

    op.create_table(
        "holiday_calendars",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "non_working_weekdays",
            _JSON,
            server_default=sa.text("'[5, 6]'"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_holiday_calendars_name_not_blank"),
        sa.CheckConstraint(
            "not is_default or is_active",
            name="ck_holiday_calendars_default_active",
        ),
        sa.CheckConstraint("version > 0", name="ck_holiday_calendars_version_positive"),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_holiday_calendars_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_holiday_calendars"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_holiday_calendars_tenant_id_id"),
    )
    op.create_index(
        "uq_holiday_calendars_tenant_default",
        "holiday_calendars",
        ("tenant_id",),
        unique=True,
        postgresql_where=sa.text("is_default AND is_active"),
        sqlite_where=sa.text("is_default = 1 AND is_active = 1"),
    )
    op.create_index(
        "ix_holiday_calendars_tenant_active_name",
        "holiday_calendars",
        ("tenant_id", "is_active", "name"),
    )

    op.create_table(
        "holiday_entries",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("calendar_id", _UUID, nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_holiday_entries_name_not_blank"),
        sa.CheckConstraint("version > 0", name="ck_holiday_entries_version_positive"),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_holiday_entries_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "calendar_id"),
            ("holiday_calendars.tenant_id", "holiday_calendars.id"),
            name="fk_holiday_entries_tenant_calendar",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_holiday_entries"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_holiday_entries_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "calendar_id",
            "holiday_date",
            name="uq_holiday_entries_tenant_calendar_date",
        ),
    )
    op.create_index(
        "ix_holiday_entries_tenant_calendar_date",
        "holiday_entries",
        ("tenant_id", "calendar_id", "holiday_date", "is_active"),
    )

    op.create_table(
        "leave_policies",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("leave_type_id", _UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("paid", sa.Boolean(), nullable=False),
        sa.Column("document_required", sa.Boolean(), nullable=False),
        sa.Column("negative_balance_allowed", sa.Boolean(), nullable=False),
        sa.Column("accrual_enabled", sa.Boolean(), nullable=False),
        sa.Column("accrual_days_per_month", sa.Numeric(8, 2), nullable=False),
        sa.Column("carryover_enabled", sa.Boolean(), nullable=False),
        sa.Column("carryover_limit_days", sa.Numeric(8, 2), nullable=True),
        sa.Column("created_by_user_id", _UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("version > 0", name="ck_leave_policies_version_positive"),
        sa.CheckConstraint(
            "accrual_days_per_month >= 0 and accrual_days_per_month <= 31",
            name="ck_leave_policies_accrual_range",
        ),
        sa.CheckConstraint(
            "(accrual_enabled and accrual_days_per_month > 0) or "
            "(not accrual_enabled and accrual_days_per_month = 0)",
            name="ck_leave_policies_accrual_coherence",
        ),
        sa.CheckConstraint(
            "carryover_limit_days is null or "
            "(carryover_limit_days >= 0 and carryover_limit_days <= 366)",
            name="ck_leave_policies_carryover_range",
        ),
        sa.CheckConstraint(
            "carryover_enabled or carryover_limit_days is null",
            name="ck_leave_policies_carryover_coherence",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_leave_policies_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "leave_type_id"),
            ("leave_types.tenant_id", "leave_types.id"),
            name="fk_leave_policies_tenant_leave_type",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "created_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_leave_policies_tenant_created_by_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_leave_policies"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_leave_policies_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "leave_type_id",
            "id",
            name="uq_leave_policies_tenant_type_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "leave_type_id",
            "version",
            name="uq_leave_policies_tenant_type_version",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "leave_type_id",
            "effective_from",
            name="uq_leave_policies_tenant_type_effective",
        ),
    )
    op.create_index(
        "ix_leave_policies_tenant_type_effective",
        "leave_policies",
        ("tenant_id", "leave_type_id", "effective_from"),
    )


def _add_document_employee_composite_key() -> None:
    with op.batch_alter_table("employee_documents") as batch_op:
        batch_op.create_unique_constraint(
            "uq_employee_documents_tenant_employee_id",
            ("tenant_id", "employee_id", "id"),
        )


def _drop_document_employee_composite_key() -> None:
    with op.batch_alter_table("employee_documents") as batch_op:
        batch_op.drop_constraint(
            "uq_employee_documents_tenant_employee_id",
            type_="unique",
        )


def _add_request_expansion_columns() -> None:
    op.add_column("leave_requests", sa.Column("leave_type_id", _UUID, nullable=True))
    op.add_column("leave_requests", sa.Column("policy_id", _UUID, nullable=True))
    op.add_column(
        "leave_requests",
        sa.Column("requested_by_membership_id", _UUID, nullable=True),
    )
    op.add_column(
        "leave_requests",
        sa.Column("routed_manager_user_id", _UUID, nullable=True),
    )
    op.add_column("leave_requests", sa.Column("document_id", _UUID, nullable=True))
    op.add_column("leave_requests", sa.Column("employee_note", sa.Text(), nullable=True))
    op.add_column(
        "leave_requests",
        sa.Column("counted_days", sa.Numeric(8, 2), server_default=sa.text("0"), nullable=True),
    )
    op.add_column(
        "leave_requests",
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=True),
    )
    op.add_column(
        "leave_requests",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.batch_alter_table("leave_requests") as batch_op:
        batch_op.create_unique_constraint("uq_leave_requests_tenant_id_id", ("tenant_id", "id"))


def _create_workflow_fact_tables() -> None:
    _create_leave_balance_ledger_table()
    _create_leave_request_days_table()
    _create_leave_request_timeline_table()
    _create_outbox_events_table()


def _create_leave_balance_ledger_table() -> None:
    op.create_table(
        "leave_balance_ledger",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("employee_id", _UUID, nullable=False),
        sa.Column("leave_type_id", _UUID, nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("amount_days", sa.Numeric(10, 2), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("request_id", _UUID, nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", _UUID, nullable=True),
        sa.Column("source_key", sa.String(length=160), nullable=False),
        sa.Column("reversal_of_entry_id", _UUID, nullable=True),
        sa.Column("created_by_user_id", _UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "period_year >= 1900 and period_year <= 2200",
            name="ck_leave_balance_ledger_period_year",
        ),
        sa.CheckConstraint(
            "entry_type in "
            "('earned','adjustment','planned','planned_release','used','used_release')",
            name="ck_leave_balance_ledger_entry_type",
        ),
        sa.CheckConstraint("amount_days <> 0", name="ck_leave_balance_ledger_amount_nonzero"),
        sa.CheckConstraint(
            "(entry_type in ('earned','planned','used') and amount_days > 0) or "
            "(entry_type in ('planned_release','used_release') and amount_days < 0) or "
            "(entry_type = 'adjustment' and amount_days <> 0)",
            name="ck_leave_balance_ledger_amount_direction",
        ),
        sa.CheckConstraint(
            "(entry_type = 'adjustment' and reason is not null and length(trim(reason)) > 0) "
            "or (entry_type <> 'adjustment' and reason is null)",
            name="ck_leave_balance_ledger_adjustment_reason",
        ),
        sa.CheckConstraint(
            "(entry_type in ('planned_release','used_release') "
            "and reversal_of_entry_id is not null) "
            "or (entry_type not in ('planned_release','used_release') "
            "and reversal_of_entry_id is null)",
            name="ck_leave_balance_ledger_reversal_link",
        ),
        sa.CheckConstraint(
            "length(trim(source_type)) > 0 and length(trim(source_key)) > 0",
            name="ck_leave_balance_ledger_source_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_leave_balance_ledger_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_leave_balance_ledger_tenant_employee",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "leave_type_id"),
            ("leave_types.tenant_id", "leave_types.id"),
            name="fk_leave_balance_ledger_tenant_leave_type",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "request_id"),
            ("leave_requests.tenant_id", "leave_requests.id"),
            name="fk_leave_balance_ledger_tenant_request",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "reversal_of_entry_id"),
            ("leave_balance_ledger.tenant_id", "leave_balance_ledger.id"),
            name="fk_leave_balance_ledger_tenant_reversal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "created_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_leave_balance_ledger_tenant_created_by_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_leave_balance_ledger"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_leave_balance_ledger_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_key",
            name="uq_leave_balance_ledger_tenant_source_key",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "reversal_of_entry_id",
            name="uq_leave_balance_ledger_tenant_reversal",
        ),
    )
    op.create_index(
        "ix_leave_balance_ledger_tenant_employee_period_type",
        "leave_balance_ledger",
        (
            "tenant_id",
            "employee_id",
            "period_year",
            "leave_type_id",
            "created_at",
            "id",
        ),
    )
    op.create_index(
        "ix_leave_balance_ledger_tenant_request",
        "leave_balance_ledger",
        ("tenant_id", "request_id"),
    )
    op.create_index(
        "ix_leave_balance_ledger_tenant_created_cursor",
        "leave_balance_ledger",
        ("tenant_id", "created_at", "id"),
    )


def _create_leave_request_days_table() -> None:
    op.create_table(
        "leave_request_days",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("request_id", _UUID, nullable=False),
        sa.Column("leave_date", sa.Date(), nullable=False),
        sa.Column("is_working_day", sa.Boolean(), nullable=False),
        sa.Column("is_holiday", sa.Boolean(), nullable=False),
        sa.Column("counted_days", sa.Numeric(8, 2), nullable=False),
        sa.Column("holiday_entry_id", _UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "counted_days >= 0 and counted_days <= 1",
            name="ck_leave_request_days_counted_range",
        ),
        sa.CheckConstraint(
            "not is_holiday or counted_days = 0",
            name="ck_leave_request_days_holiday_not_counted",
        ),
        sa.CheckConstraint(
            "is_working_day or counted_days = 0",
            name="ck_leave_request_days_nonworking_not_counted",
        ),
        sa.CheckConstraint(
            "(is_holiday and holiday_entry_id is not null) or "
            "(not is_holiday and holiday_entry_id is null)",
            name="ck_leave_request_days_holiday_link",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_leave_request_days_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "request_id"),
            ("leave_requests.tenant_id", "leave_requests.id"),
            name="fk_leave_request_days_tenant_request",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "holiday_entry_id"),
            ("holiday_entries.tenant_id", "holiday_entries.id"),
            name="fk_leave_request_days_tenant_holiday_entry",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_leave_request_days"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_leave_request_days_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "request_id",
            "leave_date",
            name="uq_leave_request_days_tenant_request_date",
        ),
    )
    op.create_index(
        "ix_leave_request_days_tenant_date_request",
        "leave_request_days",
        ("tenant_id", "leave_date", "request_id"),
    )


def _create_leave_request_timeline_table() -> None:
    op.create_table(
        "leave_request_timeline",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("request_id", _UUID, nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", _UUID, nullable=False),
        sa.Column("source_key", sa.String(length=160), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type in ('submitted','approved','rejected','cancelled')",
            name="ck_leave_request_timeline_event_type",
        ),
        sa.CheckConstraint(
            "(event_type = 'submitted' and status = 'pending') or "
            "(event_type in ('approved','rejected','cancelled') and event_type = status)",
            name="ck_leave_request_timeline_event_status",
        ),
        sa.CheckConstraint(
            "length(trim(source_key)) > 0",
            name="ck_leave_request_timeline_source_key_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_leave_request_timeline_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "request_id"),
            ("leave_requests.tenant_id", "leave_requests.id"),
            name="fk_leave_request_timeline_tenant_request",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "actor_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_leave_request_timeline_tenant_actor_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_leave_request_timeline"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_leave_request_timeline_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_key",
            name="uq_leave_request_timeline_tenant_source_key",
        ),
    )
    op.create_index(
        "ix_leave_request_timeline_tenant_request_occurred",
        "leave_request_timeline",
        ("tenant_id", "request_id", "occurred_at", "id"),
    )


def _create_outbox_events_table() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", _UUID, nullable=False),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("payload", _JSON, nullable=False),
        sa.Column("source_key", sa.String(length=160), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type in "
            "('leave.requested','leave.approved','leave.rejected','leave.cancelled',"
            "'leave.balance_adjusted')",
            name="ck_outbox_events_event_type",
        ),
        sa.CheckConstraint(
            "length(trim(aggregate_type)) > 0 and length(trim(source_key)) > 0",
            name="ck_outbox_events_fact_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_outbox_events_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_events"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_outbox_events_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "source_key", name="uq_outbox_events_tenant_source_key"),
    )
    op.create_index(
        "ix_outbox_events_tenant_created",
        "outbox_events",
        ("tenant_id", "created_at", "id"),
    )
    op.create_index(
        "ix_outbox_events_event_created",
        "outbox_events",
        ("event_type", "created_at", "id"),
    )


def _assert_legacy_preflight() -> None:
    connection = op.get_bind()
    violations = (
        connection.execute(
            sa.text(
                """
            with violations as (
                select 'leave_requests.tenant' as relationship_name, count(*) as row_count
                from leave_requests child
                left join tenants parent on parent.id = child.tenant_id
                where parent.id is null
                union all
                select 'leave_requests.employee', count(*)
                from leave_requests child
                left join employees parent
                  on parent.tenant_id = child.tenant_id and parent.id = child.employee_id
                where parent.id is null
                union all
                select 'leave_requests.requested_by_user', count(*)
                from leave_requests child
                left join users parent
                  on parent.tenant_id = child.tenant_id
                 and parent.id = child.requested_by_user_id
                where parent.id is null
                union all
                select 'leave_requests.decided_by_user', count(*)
                from leave_requests child
                left join users parent
                  on parent.tenant_id = child.tenant_id
                 and parent.id = child.decided_by_user_id
                where child.decided_by_user_id is not null and parent.id is null
                union all
                select 'leave_balance_summaries.tenant', count(*)
                from leave_balance_summaries child
                left join tenants parent on parent.id = child.tenant_id
                where parent.id is null
                union all
                select 'leave_balance_summaries.employee', count(*)
                from leave_balance_summaries child
                left join employees parent
                  on parent.tenant_id = child.tenant_id and parent.id = child.employee_id
                where parent.id is null
            )
            select relationship_name, row_count
            from violations
            where row_count > 0
            order by relationship_name
            """
            )
        )
        .mappings()
        .all()
    )
    if violations:
        detail = ", ".join(f"{row['relationship_name']}={row['row_count']}" for row in violations)
        raise RuntimeError(
            "P6 leave migration preflight found orphan or cross-tenant history: " + detail
        )

    request_table = _migration_table("leave_requests")
    request_rows = connection.execute(
        sa.select(
            request_table.c.id,
            request_table.c.tenant_id,
            request_table.c.start_date,
            request_table.c.end_date,
            request_table.c.status,
            request_table.c.decided_by_user_id,
        )
    ).mappings()
    for row in request_rows:
        start_date = _as_date(row["start_date"])
        end_date = _as_date(row["end_date"])
        if start_date.year < 1900 or end_date.year > 2200:
            raise RuntimeError(
                "P6 leave migration found a legacy request outside the supported date "
                f"range: request_id={row['id']}, start_date={start_date}, "
                f"end_date={end_date}"
            )
        span_days = (end_date - start_date).days + 1
        if span_days < 1 or span_days > _LEGACY_MAX_SPAN_DAYS:
            raise RuntimeError(
                "P6 leave migration preflight found an oversized legacy request: "
                f"request_id={row['id']}, span_days={span_days}"
            )
        status = str(row["status"])
        decided_by_user_id = row["decided_by_user_id"]
        if status == "pending" and decided_by_user_id is not None:
            raise RuntimeError(
                "P6 leave migration preflight found pending request decision metadata: "
                f"request_id={row['id']}"
            )
        if status != "pending" and decided_by_user_id is None:
            raise RuntimeError(
                "P6 leave migration preflight found terminal request without actor: "
                f"request_id={row['id']}"
            )

    overlap = (
        connection.execute(
            sa.text(
                """
            select first_request.id as first_id, second_request.id as second_id
            from leave_requests first_request
            join leave_requests second_request
              on second_request.tenant_id = first_request.tenant_id
             and second_request.employee_id = first_request.employee_id
             and second_request.id <> first_request.id
             and second_request.start_date <= first_request.end_date
             and second_request.end_date >= first_request.start_date
            where first_request.status in ('pending','approved')
              and second_request.status in ('pending','approved')
            limit 1
            """
            )
        )
        .mappings()
        .one_or_none()
    )
    if overlap is not None:
        raise RuntimeError(
            "P6 leave migration preflight found overlapping active requests: "
            f"first_id={overlap['first_id']}, second_id={overlap['second_id']}"
        )

    summary_table = _migration_table("leave_balance_summaries")
    summaries = connection.execute(
        sa.select(
            summary_table.c.id,
            summary_table.c.opening_balance_days,
            summary_table.c.used_days,
            summary_table.c.planned_days,
        )
    ).mappings()
    for row in summaries:
        for field_name in ("opening_balance_days", "used_days", "planned_days"):
            _legacy_decimal(row[field_name], summary_id=row["id"], field_name=field_name)

    legacy_types: dict[UUID, set[str]] = {}
    for table in (request_table, summary_table):
        for tenant_value, leave_type_value in connection.execute(
            sa.select(table.c.tenant_id, table.c.leave_type)
        ):
            tenant_id = _as_uuid(tenant_value)
            legacy_types.setdefault(tenant_id, set()).add(str(leave_type_value))
    for tenant_id, values in legacy_types.items():
        imported_type_count = sum(value not in _CANONICAL_CODES for value in values)
        total_type_count = len(_STARTER_TYPES) + imported_type_count
        if total_type_count > _CONFIGURATION_LIMIT:
            raise RuntimeError(
                "P6 leave migration found more distinct leave types than the bounded "
                f"configuration can preserve: tenant_id={tenant_id}, "
                f"leave_type_count={total_type_count}"
            )


def _seed_tenant_defaults_and_legacy_types() -> tuple[
    dict[tuple[UUID, str], UUID],
    dict[tuple[UUID, UUID], UUID],
]:
    connection = op.get_bind()
    tenant_table = _migration_table("tenants")
    request_table = _migration_table("leave_requests")
    summary_table = _migration_table("leave_balance_summaries")
    tenant_ids = sorted(
        (_as_uuid(value) for value in connection.scalars(sa.select(tenant_table.c.id))),
        key=str,
    )

    legacy_values: dict[UUID, set[str]] = {tenant_id: set() for tenant_id in tenant_ids}
    for table in (request_table, summary_table):
        rows = connection.execute(sa.select(table.c.tenant_id, table.c.leave_type))
        for tenant_value, raw_value in rows:
            legacy_values[_as_uuid(tenant_value)].add(str(raw_value))

    leave_type_rows: list[dict[str, object]] = []
    policy_rows: list[dict[str, object]] = []
    calendar_rows: list[dict[str, object]] = []
    type_mapping: dict[tuple[UUID, str], UUID] = {}
    policy_mapping: dict[tuple[UUID, UUID], UUID] = {}

    for tenant_id in tenant_ids:
        imported_type_count = sum(
            raw_value not in _CANONICAL_CODES for raw_value in legacy_values[tenant_id]
        )
        if len(_STARTER_TYPES) + imported_type_count > _CONFIGURATION_LIMIT:
            raise RuntimeError(
                "P6 leave migration found more distinct leave types than the bounded "
                f"configuration can preserve: tenant_id={tenant_id}, "
                f"leave_type_count={len(_STARTER_TYPES) + imported_type_count}"
            )
        code_to_type_id: dict[str, UUID] = {}
        for code, name, paid, document_required in _STARTER_TYPES:
            leave_type_id = _deterministic_uuid(f"p6:leave-type:{tenant_id}:{code}")
            code_to_type_id[code] = leave_type_id
            leave_type_rows.append(
                {
                    "id": leave_type_id,
                    "tenant_id": tenant_id,
                    "code": code,
                    "name": name,
                    "description": None,
                    "is_active": True,
                    "version": 1,
                }
            )
            policy_id = _deterministic_uuid(f"p6:leave-policy:{tenant_id}:{leave_type_id}:1")
            policy_mapping[(tenant_id, leave_type_id)] = policy_id
            policy_rows.append(
                _policy_seed_row(
                    policy_id=policy_id,
                    tenant_id=tenant_id,
                    leave_type_id=leave_type_id,
                    paid=paid,
                    document_required=document_required,
                )
            )

        seen_codes = set(code_to_type_id)
        for raw_value in sorted(legacy_values[tenant_id]):
            if raw_value in _CANONICAL_CODES:
                type_mapping[(tenant_id, raw_value)] = code_to_type_id[raw_value]
                continue
            digest = hashlib.md5(raw_value.encode("utf-8"), usedforsecurity=False).hexdigest()
            code = f"legacy_{digest}"
            if code in seen_codes:
                raise RuntimeError(
                    "P6 leave migration legacy type code collision: "
                    f"tenant_id={tenant_id}, leave_type={raw_value!r}"
                )
            seen_codes.add(code)
            leave_type_id = _deterministic_uuid(f"p6:legacy-leave-type:{tenant_id}:{raw_value}")
            type_mapping[(tenant_id, raw_value)] = leave_type_id
            display_name = raw_value.strip() or "Legacy unclassified leave"
            leave_type_rows.append(
                {
                    "id": leave_type_id,
                    "tenant_id": tenant_id,
                    "code": code,
                    "name": display_name[:200],
                    "description": "Imported legacy leave type; inactive for new requests.",
                    "is_active": False,
                    "version": 1,
                }
            )
            policy_id = _deterministic_uuid(f"p6:leave-policy:{tenant_id}:{leave_type_id}:1")
            policy_mapping[(tenant_id, leave_type_id)] = policy_id
            policy_rows.append(
                _policy_seed_row(
                    policy_id=policy_id,
                    tenant_id=tenant_id,
                    leave_type_id=leave_type_id,
                    paid=False,
                    document_required=False,
                )
            )

        calendar_rows.append(
            {
                "id": _deterministic_uuid(f"p6:holiday-calendar:{tenant_id}:default"),
                "tenant_id": tenant_id,
                "name": "Default work calendar",
                "is_default": True,
                "is_active": True,
                "non_working_weekdays": [5, 6],
                "version": 1,
            }
        )

    if leave_type_rows:
        connection.execute(sa.insert(_leave_types_seed_table()), leave_type_rows)
    if calendar_rows:
        connection.execute(sa.insert(_holiday_calendars_seed_table()), calendar_rows)
    if policy_rows:
        connection.execute(sa.insert(_leave_policies_seed_table()), policy_rows)
    return type_mapping, policy_mapping


def _policy_seed_row(
    *,
    policy_id: UUID,
    tenant_id: UUID,
    leave_type_id: UUID,
    paid: bool,
    document_required: bool,
) -> dict[str, object]:
    return {
        "id": policy_id,
        "tenant_id": tenant_id,
        "leave_type_id": leave_type_id,
        "version": 1,
        "effective_from": _POLICY_EFFECTIVE_FROM,
        "paid": paid,
        "document_required": document_required,
        "negative_balance_allowed": False,
        "accrual_enabled": False,
        "accrual_days_per_month": Decimal("0.00"),
        "carryover_enabled": False,
        "carryover_limit_days": None,
        "created_by_user_id": None,
    }


def _backfill_requests(
    type_mapping: dict[tuple[UUID, str], UUID],
    policy_mapping: dict[tuple[UUID, UUID], UUID],
) -> list[dict[str, object]]:
    connection = op.get_bind()
    request_table = _migration_table("leave_requests")
    day_table = _migration_table("leave_request_days")
    timeline_table = _migration_table("leave_request_timeline")

    linked_memberships = {
        (
            _as_uuid(row["tenant_id"]),
            _as_uuid(row["legacy_user_id"]),
            _as_uuid(row["employee_id"]),
        ): _as_uuid(row["membership_id"])
        for row in connection.execute(
            sa.text(
                """
                select membership.tenant_id,
                       membership.legacy_user_id,
                       account_link.employee_id,
                       membership.id as membership_id
                from tenant_memberships membership
                join employee_account_links account_link
                  on account_link.tenant_id = membership.tenant_id
                 and account_link.membership_id = membership.id
                """
            )
        ).mappings()
    }

    day_rows: list[dict[str, object]] = []
    timeline_rows: list[dict[str, object]] = []
    request_facts: list[dict[str, object]] = []
    requests = connection.execute(
        sa.select(request_table).order_by(request_table.c.tenant_id, request_table.c.id)
    ).mappings()
    for row in requests:
        tenant_id = _as_uuid(row["tenant_id"])
        request_id = _as_uuid(row["id"])
        employee_id = _as_uuid(row["employee_id"])
        requested_by_user_id = _as_uuid(row["requested_by_user_id"])
        raw_leave_type = str(row["leave_type"])
        leave_type_id = type_mapping.get((tenant_id, raw_leave_type))
        if leave_type_id is None:
            raise RuntimeError(
                "P6 leave migration could not map legacy request type: "
                f"request_id={request_id}, leave_type={raw_leave_type!r}"
            )
        policy_id = policy_mapping[(tenant_id, leave_type_id)]
        start_date = _as_date(row["start_date"])
        end_date = _as_date(row["end_date"])
        created_at = _as_datetime(row["created_at"])
        updated_at = _as_datetime(row["updated_at"])
        status = str(row["status"])

        counted_by_year: dict[int, Decimal] = {}
        first_counted_by_year: dict[int, date] = {}
        counted_total = Decimal("0.00")
        current_date = start_date
        while current_date <= end_date:
            is_working_day = current_date.weekday() not in {5, 6}
            counted_days = Decimal("1.00") if is_working_day else Decimal("0.00")
            day_rows.append(
                {
                    "id": _deterministic_uuid(
                        f"p6:leave-request-day:{tenant_id}:{request_id}:{current_date.isoformat()}"
                    ),
                    "tenant_id": tenant_id,
                    "request_id": request_id,
                    "leave_date": current_date,
                    "is_working_day": is_working_day,
                    "is_holiday": False,
                    "counted_days": counted_days,
                    "holiday_entry_id": None,
                    "created_at": created_at,
                }
            )
            if counted_days:
                counted_total += counted_days
                counted_by_year[current_date.year] = (
                    counted_by_year.get(current_date.year, Decimal("0.00")) + counted_days
                )
                first_counted_by_year.setdefault(current_date.year, current_date)
            current_date += timedelta(days=1)

        membership_id = linked_memberships.get((tenant_id, requested_by_user_id, employee_id))
        decided_at = updated_at if status != "pending" else None
        connection.execute(
            sa.update(request_table)
            .where(
                request_table.c.tenant_id == tenant_id,
                request_table.c.id == request_id,
            )
            .values(
                leave_type_id=leave_type_id,
                policy_id=policy_id,
                requested_by_membership_id=membership_id,
                routed_manager_user_id=None,
                document_id=None,
                employee_note=None,
                counted_days=counted_total,
                version=1,
                decided_at=decided_at,
            )
        )

        timeline_rows.append(
            {
                "id": _deterministic_uuid(
                    f"p6:leave-request-timeline:{tenant_id}:{request_id}:submitted"
                ),
                "tenant_id": tenant_id,
                "request_id": request_id,
                "event_type": "submitted",
                "status": "pending",
                "actor_user_id": requested_by_user_id,
                "source_key": f"legacy-request:{request_id}:submitted",
                "occurred_at": created_at,
            }
        )
        if status != "pending":
            timeline_rows.append(
                {
                    "id": _deterministic_uuid(
                        f"p6:leave-request-timeline:{tenant_id}:{request_id}:{status}"
                    ),
                    "tenant_id": tenant_id,
                    "request_id": request_id,
                    "event_type": status,
                    "status": status,
                    "actor_user_id": _as_uuid(row["decided_by_user_id"]),
                    "source_key": f"legacy-request:{request_id}:{status}",
                    "occurred_at": updated_at,
                }
            )

        entry_type = {"pending": "planned", "approved": "used"}.get(status)
        if entry_type is not None:
            for period_year, amount_days in counted_by_year.items():
                request_facts.append(
                    {
                        "tenant_id": tenant_id,
                        "employee_id": employee_id,
                        "leave_type_id": leave_type_id,
                        "legacy_leave_type": raw_leave_type,
                        "period_year": period_year,
                        "entry_type": entry_type,
                        "amount_days": amount_days,
                        "effective_date": first_counted_by_year[period_year],
                        "request_id": request_id,
                    }
                )

    _execute_in_chunks(day_table.insert(), day_rows)
    _execute_in_chunks(timeline_table.insert(), timeline_rows)
    return request_facts


def _backfill_ledger(
    type_mapping: dict[tuple[UUID, str], UUID],
    request_facts: list[dict[str, object]],
) -> None:
    connection = op.get_bind()
    summary_table = _migration_table("leave_balance_summaries")
    ledger_table = _migration_table("leave_balance_ledger")
    request_totals: dict[tuple[UUID, UUID, UUID, int, str], Decimal] = {}
    ledger_rows: list[dict[str, object]] = []

    for fact in request_facts:
        tenant_id = _as_uuid(fact["tenant_id"])
        employee_id = _as_uuid(fact["employee_id"])
        leave_type_id = _as_uuid(fact["leave_type_id"])
        period_year = int(fact["period_year"])
        entry_type = str(fact["entry_type"])
        amount_days = _as_decimal(fact["amount_days"])
        request_id = _as_uuid(fact["request_id"])
        key = (tenant_id, employee_id, leave_type_id, period_year, entry_type)
        request_totals[key] = request_totals.get(key, Decimal("0.00")) + amount_days
        ledger_rows.append(
            _ledger_row(
                tenant_id=tenant_id,
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                period_year=period_year,
                entry_type=entry_type,
                amount_days=amount_days,
                effective_date=_as_date(fact["effective_date"]),
                reason=None,
                request_id=request_id,
                source_type="legacy_request",
                source_id=request_id,
                source_key=f"legacy-request:{request_id}:{entry_type}:{period_year}",
            )
        )

    summaries = connection.execute(
        sa.select(summary_table).order_by(summary_table.c.tenant_id, summary_table.c.id)
    ).mappings()
    for row in summaries:
        tenant_id = _as_uuid(row["tenant_id"])
        employee_id = _as_uuid(row["employee_id"])
        summary_id = _as_uuid(row["id"])
        raw_leave_type = str(row["leave_type"])
        leave_type_id = type_mapping.get((tenant_id, raw_leave_type))
        if leave_type_id is None:
            raise RuntimeError(
                "P6 leave migration could not map legacy balance type: "
                f"summary_id={summary_id}, leave_type={raw_leave_type!r}"
            )
        period_year = int(row["period_year"])
        opening_days = _legacy_decimal(
            row["opening_balance_days"],
            summary_id=summary_id,
            field_name="opening_balance_days",
        )
        used_days = _legacy_decimal(row["used_days"], summary_id=summary_id, field_name="used_days")
        planned_days = _legacy_decimal(
            row["planned_days"], summary_id=summary_id, field_name="planned_days"
        )
        effective_date = date(period_year, 1, 1)

        for entry_type, stored_total in (("used", used_days), ("planned", planned_days)):
            request_total = request_totals.get(
                (tenant_id, employee_id, leave_type_id, period_year, entry_type),
                Decimal("0.00"),
            )
            if request_total > stored_total:
                raise RuntimeError(
                    "P6 leave ledger reconciliation failed; legacy summary is insufficient: "
                    f"summary_id={summary_id}, entry_type={entry_type}, "
                    f"summary_days={stored_total}, request_days={request_total}"
                )
            residual = stored_total - request_total
            if residual:
                ledger_rows.append(
                    _ledger_row(
                        tenant_id=tenant_id,
                        employee_id=employee_id,
                        leave_type_id=leave_type_id,
                        period_year=period_year,
                        entry_type=entry_type,
                        amount_days=residual,
                        effective_date=effective_date,
                        reason=None,
                        request_id=None,
                        source_type="legacy_summary",
                        source_id=summary_id,
                        source_key=(f"legacy-summary:{summary_id}:{entry_type}:{period_year}"),
                    )
                )

        if opening_days:
            ledger_rows.append(
                _ledger_row(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    leave_type_id=leave_type_id,
                    period_year=period_year,
                    entry_type="adjustment",
                    amount_days=opening_days,
                    effective_date=effective_date,
                    reason="Imported legacy opening balance.",
                    request_id=None,
                    source_type="legacy_summary",
                    source_id=summary_id,
                    source_key=f"legacy-summary:{summary_id}:opening:{period_year}",
                )
            )

    _execute_in_chunks(ledger_table.insert(), ledger_rows)


def _ledger_row(
    *,
    tenant_id: UUID,
    employee_id: UUID,
    leave_type_id: UUID,
    period_year: int,
    entry_type: str,
    amount_days: Decimal,
    effective_date: date,
    reason: str | None,
    request_id: UUID | None,
    source_type: str,
    source_id: UUID | None,
    source_key: str,
) -> dict[str, object]:
    return {
        "id": _deterministic_uuid(f"p6:leave-ledger:{tenant_id}:{source_key}"),
        "tenant_id": tenant_id,
        "employee_id": employee_id,
        "leave_type_id": leave_type_id,
        "period_year": period_year,
        "entry_type": entry_type,
        "amount_days": amount_days,
        "effective_date": effective_date,
        "reason": reason,
        "request_id": request_id,
        "source_type": source_type,
        "source_id": source_id,
        "source_key": source_key,
        "reversal_of_entry_id": None,
        "created_by_user_id": None,
    }


def _contract_leave_requests() -> None:
    with op.batch_alter_table("leave_requests") as batch_op:
        batch_op.alter_column(
            "leave_type_id",
            existing_type=_UUID,
            nullable=False,
        )
        batch_op.alter_column(
            "policy_id",
            existing_type=_UUID,
            nullable=False,
        )
        batch_op.alter_column(
            "counted_days",
            existing_type=sa.Numeric(8, 2),
            existing_server_default=sa.text("0"),
            nullable=False,
        )
        batch_op.alter_column(
            "version",
            existing_type=sa.Integer(),
            existing_server_default=sa.text("1"),
            nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_leave_requests_counted_days_non_negative",
            "counted_days >= 0",
        )
        batch_op.create_check_constraint(
            "ck_leave_requests_supported_dates",
            "start_date >= '1900-01-01' and end_date <= '2200-12-31'",
        )
        batch_op.create_check_constraint(
            "ck_leave_requests_version_positive",
            "version > 0",
        )
        batch_op.create_check_constraint(
            "ck_leave_requests_decision_state",
            "(status = 'pending' and decided_by_user_id is null and decided_at is null) or "
            "(status <> 'pending' and decided_by_user_id is not null and decided_at is not null)",
        )
        batch_op.create_foreign_key(
            "fk_leave_requests_tenant_leave_type",
            "leave_types",
            ("tenant_id", "leave_type_id"),
            ("tenant_id", "id"),
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_leave_requests_tenant_type_policy",
            "leave_policies",
            ("tenant_id", "leave_type_id", "policy_id"),
            ("tenant_id", "leave_type_id", "id"),
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_leave_requests_tenant_requested_by_membership",
            "tenant_memberships",
            ("tenant_id", "requested_by_membership_id"),
            ("tenant_id", "id"),
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_leave_requests_tenant_routed_manager_user",
            "users",
            ("tenant_id", "routed_manager_user_id"),
            ("tenant_id", "id"),
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_leave_requests_tenant_document",
            "employee_documents",
            ("tenant_id", "employee_id", "document_id"),
            ("tenant_id", "employee_id", "id"),
            ondelete="RESTRICT",
        )
    op.create_index(
        "ix_leave_requests_tenant_manager_status_created",
        "leave_requests",
        ("tenant_id", "routed_manager_user_id", "status", "created_at", "id"),
    )
    op.create_index(
        "ix_leave_requests_tenant_employee_status_dates",
        "leave_requests",
        ("tenant_id", "employee_id", "status", "start_date", "end_date"),
    )
    op.create_index(
        "ix_leave_requests_tenant_type_start",
        "leave_requests",
        ("tenant_id", "leave_type_id", "start_date"),
    )


def _create_overlap_constraint() -> None:
    op.execute(
        sa.text(
            f"""
            ALTER TABLE public.leave_requests
            ADD CONSTRAINT {_OVERLAP_CONSTRAINT}
            EXCLUDE USING gist (
                tenant_id WITH =,
                employee_id WITH =,
                daterange(start_date, end_date, '[]') WITH &&
            )
            WHERE (status IN ('pending','approved'))
            """
        )
    )


def _seed_permissions() -> None:
    connection = op.get_bind()
    permissions = sa.table(
        "permissions",
        sa.column("id", _UUID),
        sa.column("code", sa.String()),
        sa.column("resource", sa.String()),
        sa.column("action", sa.String()),
        sa.column("target", sa.String()),
        sa.column("target_type", sa.String()),
        sa.column("description", sa.Text()),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", _UUID),
        sa.column("permission_id", _UUID),
    )
    roles = sa.table("roles", sa.column("id", _UUID), sa.column("code", sa.String()))

    expected_role_ids = set(_ROLE_IDS.values())
    actual_role_ids = set(
        connection.scalars(sa.select(roles.c.id).where(roles.c.id.in_(expected_role_ids)))
    )
    if {_as_uuid(value) for value in actual_role_ids} != expected_role_ids:
        raise RuntimeError("P6 leave permission seed is missing expected system roles")

    for (
        permission_id,
        code,
        resource,
        action,
        target,
        description,
        role_codes,
    ) in _PERMISSIONS:
        matches = (
            connection.execute(
                sa.select(permissions).where(
                    sa.or_(permissions.c.id == permission_id, permissions.c.code == code)
                )
            )
            .mappings()
            .all()
        )
        expected = {
            "id": permission_id,
            "code": code,
            "resource": resource,
            "action": action,
            "target": target,
            "target_type": "scope",
            "description": description,
        }
        if matches:
            if len(matches) != 1 or any(
                str(matches[0][key]) != str(value) for key, value in expected.items()
            ):
                raise RuntimeError(f"P6 permission catalog conflicts with {code}")
        else:
            connection.execute(sa.insert(permissions).values(expected))

        expected_grants = {_ROLE_IDS[role_code] for role_code in role_codes}
        actual_grants = {
            _as_uuid(value)
            for value in connection.scalars(
                sa.select(role_permissions.c.role_id).where(
                    role_permissions.c.permission_id == permission_id
                )
            )
        }
        if not actual_grants <= expected_grants:
            raise RuntimeError(f"P6 permission {code} has unexpected role grants")
        for role_id in sorted(expected_grants - actual_grants, key=str):
            connection.execute(
                sa.insert(role_permissions).values(
                    role_id=role_id,
                    permission_id=permission_id,
                )
            )


def _seed_manager_own_document_read_grant() -> None:
    connection = op.get_bind()
    permissions = sa.table(
        "permissions",
        sa.column("id", _UUID),
        sa.column("code", sa.String()),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", _UUID),
        sa.column("permission_id", _UUID),
    )
    matches = (
        connection.execute(
            sa.select(permissions).where(
                sa.or_(
                    permissions.c.id == _OWN_DOCUMENT_READ_PERMISSION_ID,
                    permissions.c.code == _OWN_DOCUMENT_READ_PERMISSION_CODE,
                )
            )
        )
        .mappings()
        .all()
    )
    if (
        len(matches) != 1
        or _as_uuid(matches[0]["id"]) != _OWN_DOCUMENT_READ_PERMISSION_ID
        or str(matches[0]["code"]) != _OWN_DOCUMENT_READ_PERMISSION_CODE
    ):
        raise RuntimeError("P6 manager own-document read permission conflicts with the catalog")
    expected_roles = {
        _ROLE_IDS["hr_director"],
        _ROLE_IDS["hr_specialist"],
        _ROLE_IDS["manager"],
        _ROLE_IDS["employee"],
    }
    actual_roles = {
        _as_uuid(value)
        for value in connection.scalars(
            sa.select(role_permissions.c.role_id).where(
                role_permissions.c.permission_id == _OWN_DOCUMENT_READ_PERMISSION_ID
            )
        )
    }
    if not actual_roles <= expected_roles:
        raise RuntimeError("P6 own-document read permission has unexpected role grants")
    for role_id in sorted(expected_roles - actual_roles, key=str):
        connection.execute(
            sa.insert(role_permissions).values(
                role_id=role_id,
                permission_id=_OWN_DOCUMENT_READ_PERMISSION_ID,
            )
        )


def _create_immutability_triggers() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_IMMUTABILITY_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            VOLATILE
            SECURITY INVOKER
            SET search_path = pg_catalog, public
            AS $p6_leave_immutability$
            BEGIN
                RAISE EXCEPTION 'P6 leave facts are append-only'
                    USING ERRCODE = '23514',
                          SCHEMA = 'public',
                          TABLE = TG_TABLE_NAME,
                          CONSTRAINT = 'ck_' || TG_TABLE_NAME || '_immutable';
            END
            $p6_leave_immutability$
            """
        )
    )
    op.execute(sa.text(f"REVOKE ALL ON FUNCTION public.{_IMMUTABILITY_FUNCTION}() FROM PUBLIC"))
    for table_name in _IMMUTABLE_TABLES:
        op.execute(
            sa.text(
                f'CREATE TRIGGER "trg_{table_name}_immutable" '
                f'BEFORE UPDATE OR DELETE ON public."{table_name}" '
                f"FOR EACH ROW EXECUTE FUNCTION public.{_IMMUTABILITY_FUNCTION}()"
            )
        )


def _drop_immutability_triggers() -> None:
    for table_name in _IMMUTABLE_TABLES:
        op.execute(
            sa.text(f'DROP TRIGGER IF EXISTS "trg_{table_name}_immutable" ON public."{table_name}"')
        )
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS public.{_IMMUTABILITY_FUNCTION}()"))


def _configure_postgresql_security() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE holiday_calendars ADD CONSTRAINT "
            "ck_holiday_calendars_weekdays_json CHECK ("
            "jsonb_typeof(non_working_weekdays) = 'array' "
            "and jsonb_array_length(non_working_weekdays) <= 7 "
            "and non_working_weekdays <@ '[0,1,2,3,4,5,6]'::jsonb)"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE outbox_events ADD CONSTRAINT "
            "ck_outbox_events_payload_object CHECK (jsonb_typeof(payload) = 'object')"
        )
    )

    request_columns = (
        "id",
        "tenant_id",
        "employee_id",
        "leave_type",
        "leave_type_id",
        "policy_id",
        "start_date",
        "end_date",
        "status",
        "requested_by_user_id",
        "requested_by_membership_id",
        "routed_manager_user_id",
        "document_id",
        "employee_note",
        "counted_days",
        "version",
        "decided_by_user_id",
        "decision_note",
        "decided_at",
        "created_at",
        "updated_at",
    )
    summary_columns = (
        "id",
        "tenant_id",
        "employee_id",
        "leave_type",
        "period_year",
        "opening_balance_days",
        "used_days",
        "planned_days",
        "created_at",
        "updated_at",
    )
    _reset_postgresql_acl("leave_requests", request_columns)
    grant_table_privileges(
        op,
        table_name="leave_requests",
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT"),
    )
    grant_column_privilege(
        op,
        table_name="leave_requests",
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=(
            "status",
            "decided_by_user_id",
            "decision_note",
            "decided_at",
            "version",
            "updated_at",
        ),
    )
    _reset_postgresql_acl("leave_balance_summaries", summary_columns)
    grant_table_privileges(
        op,
        table_name="leave_balance_summaries",
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT",),
    )

    table_columns = _new_table_columns()
    for table_name in _NEW_TABLES:
        _reset_postgresql_acl(table_name, table_columns[table_name])
        enable_forced_row_security(op, table_name=table_name)
        create_tenant_isolation_policy(
            op,
            table_name=table_name,
            policy_name=_TENANT_POLICY,
            role_name=TENANT_APPLICATION_ROLE,
        )

    for table_name in ("leave_types", "holiday_calendars", "holiday_entries"):
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=TENANT_APPLICATION_ROLE,
            privileges=("SELECT", "INSERT"),
        )
    grant_column_privilege(
        op,
        table_name="leave_types",
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=("name", "description", "is_active", "version", "updated_at"),
    )
    grant_column_privilege(
        op,
        table_name="holiday_calendars",
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=(
            "name",
            "is_default",
            "is_active",
            "non_working_weekdays",
            "version",
            "updated_at",
        ),
    )
    grant_column_privilege(
        op,
        table_name="holiday_entries",
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=("name", "is_active", "version", "updated_at"),
    )
    for table_name in (
        "leave_policies",
        "leave_balance_ledger",
        "leave_request_days",
        "leave_request_timeline",
    ):
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=TENANT_APPLICATION_ROLE,
            privileges=("SELECT", "INSERT"),
        )
    # PostgreSQL requires UPDATE privilege on at least one column for
    # SELECT ... FOR UPDATE. Grant only the immutable primary key as a lock
    # capability; the table trigger still rejects every actual UPDATE/DELETE.
    grant_column_privilege(
        op,
        table_name="leave_balance_ledger",
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=("id",),
    )
    grant_table_privileges(
        op,
        table_name="outbox_events",
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("INSERT",),
    )

    for table_name in _PLATFORM_BOOTSTRAP_TABLES:
        create_unrestricted_insert_policy(
            op,
            table_name=table_name,
            policy_name=_PLATFORM_BOOTSTRAP_POLICY,
            role_name=PLATFORM_APPLICATION_ROLE,
        )
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=PLATFORM_APPLICATION_ROLE,
            privileges=("INSERT",),
        )


def _reset_postgresql_acl(table_name: str, column_names: tuple[str, ...]) -> None:
    quoted_columns = ", ".join(f'"{column}"' for column in column_names)
    op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{table_name}" FROM PUBLIC'))
    op.execute(
        sa.text(f'REVOKE ALL PRIVILEGES ({quoted_columns}) ON TABLE "{table_name}" FROM PUBLIC')
    )
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
    ):
        revoke_all_table_privileges(
            op,
            table_name=table_name,
            role_name=role_name,
        )
        revoke_all_column_privileges(
            op,
            table_name=table_name,
            role_name=role_name,
            column_names=column_names,
        )


def _new_table_columns() -> dict[str, tuple[str, ...]]:
    return {
        "leave_types": (
            "id",
            "tenant_id",
            "code",
            "name",
            "description",
            "is_active",
            "version",
            "created_at",
            "updated_at",
        ),
        "holiday_calendars": (
            "id",
            "tenant_id",
            "name",
            "is_default",
            "is_active",
            "non_working_weekdays",
            "version",
            "created_at",
            "updated_at",
        ),
        "holiday_entries": (
            "id",
            "tenant_id",
            "calendar_id",
            "holiday_date",
            "name",
            "is_active",
            "version",
            "created_at",
            "updated_at",
        ),
        "leave_policies": (
            "id",
            "tenant_id",
            "leave_type_id",
            "version",
            "effective_from",
            "paid",
            "document_required",
            "negative_balance_allowed",
            "accrual_enabled",
            "accrual_days_per_month",
            "carryover_enabled",
            "carryover_limit_days",
            "created_by_user_id",
            "created_at",
        ),
        "leave_balance_ledger": (
            "id",
            "tenant_id",
            "employee_id",
            "leave_type_id",
            "period_year",
            "entry_type",
            "amount_days",
            "effective_date",
            "reason",
            "request_id",
            "source_type",
            "source_id",
            "source_key",
            "reversal_of_entry_id",
            "created_by_user_id",
            "created_at",
        ),
        "leave_request_days": (
            "id",
            "tenant_id",
            "request_id",
            "leave_date",
            "is_working_day",
            "is_holiday",
            "counted_days",
            "holiday_entry_id",
            "created_at",
        ),
        "leave_request_timeline": (
            "id",
            "tenant_id",
            "request_id",
            "event_type",
            "status",
            "actor_user_id",
            "source_key",
            "occurred_at",
        ),
        "outbox_events": (
            "id",
            "tenant_id",
            "aggregate_type",
            "aggregate_id",
            "event_type",
            "payload",
            "source_key",
            "occurred_at",
            "created_at",
        ),
    }


def _assert_downgrade_is_safe() -> None:
    """Refuse to discard any workflow/configuration history created after P6."""

    connection = op.get_bind()
    protected_tables = (
        "holiday_entries",
        "leave_balance_ledger",
        "leave_request_days",
        "leave_request_timeline",
        "outbox_events",
    )
    counts = {
        table_name: int(connection.scalar(sa.text(f'SELECT count(*) FROM "{table_name}"')) or 0)
        for table_name in protected_tables
    }
    request_count = int(connection.scalar(sa.text("SELECT count(*) FROM leave_requests")) or 0)
    if request_count:
        counts["leave_requests"] = request_count

    tenant_ids = [
        _as_uuid(value)
        for value in connection.scalars(sa.text("SELECT id FROM tenants ORDER BY id"))
    ]
    expected_type_ids = {
        _deterministic_uuid(f"p6:leave-type:{tenant_id}:{code}")
        for tenant_id in tenant_ids
        for code in _CANONICAL_CODES
    }
    expected_calendar_ids = {
        _deterministic_uuid(f"p6:holiday-calendar:{tenant_id}:default") for tenant_id in tenant_ids
    }
    actual_types = connection.execute(
        sa.text(
            "SELECT id, tenant_id, code, name, description, is_active, version FROM leave_types"
        )
    ).mappings()
    starter_by_code = {item[0]: item for item in _STARTER_TYPES}
    for row in actual_types:
        type_id = _as_uuid(row["id"])
        code = str(row["code"])
        starter = starter_by_code.get(code)
        if (
            type_id not in expected_type_ids
            or starter is None
            or str(row["name"]) != starter[1]
            or row["description"] is not None
            or not bool(row["is_active"])
            or int(row["version"]) != 1
        ):
            counts["leave_types_changed"] = counts.get("leave_types_changed", 0) + 1

    actual_calendars = connection.execute(
        sa.text(
            "SELECT id, name, is_default, is_active, non_working_weekdays, version "
            "FROM holiday_calendars"
        )
    ).mappings()
    for row in actual_calendars:
        weekdays = row["non_working_weekdays"]
        if isinstance(weekdays, str):
            normalized_weekdays = weekdays.replace(" ", "")
        else:
            normalized_weekdays = str(list(weekdays)).replace(" ", "")
        if (
            _as_uuid(row["id"]) not in expected_calendar_ids
            or str(row["name"]) != "Default work calendar"
            or not bool(row["is_default"])
            or not bool(row["is_active"])
            or normalized_weekdays != "[5,6]"
            or int(row["version"]) != 1
        ):
            counts["holiday_calendars_changed"] = counts.get("holiday_calendars_changed", 0) + 1

    policies = connection.execute(
        sa.text(
            "SELECT id, tenant_id, leave_type_id, version, effective_from, paid, "
            "document_required, negative_balance_allowed, accrual_enabled, "
            "accrual_days_per_month, carryover_enabled, carryover_limit_days, "
            "created_by_user_id FROM leave_policies"
        )
    ).mappings()
    expected_type_settings = {
        _deterministic_uuid(f"p6:leave-type:{tenant_id}:{code}"): (
            tenant_id,
            paid,
            required,
        )
        for tenant_id in tenant_ids
        for code, _name, paid, required in _STARTER_TYPES
    }
    expected_policy_ids = {
        _deterministic_uuid(f"p6:leave-policy:{tenant_id}:{type_id}:1")
        for type_id, (tenant_id, _paid, _required) in expected_type_settings.items()
    }
    for row in policies:
        policy_id = _as_uuid(row["id"])
        leave_type_id = _as_uuid(row["leave_type_id"])
        expected_settings = expected_type_settings.get(leave_type_id)
        expected_id = _deterministic_uuid(
            f"p6:leave-policy:{_as_uuid(row['tenant_id'])}:{leave_type_id}:1"
        )
        if (
            policy_id != expected_id
            or policy_id not in expected_policy_ids
            or expected_settings is None
            or int(row["version"]) != 1
            or _as_date(row["effective_from"]) != _POLICY_EFFECTIVE_FROM
            or bool(row["paid"]) is not expected_settings[1]
            or bool(row["document_required"]) is not expected_settings[2]
            or bool(row["negative_balance_allowed"])
            or bool(row["accrual_enabled"])
            or _as_decimal(row["accrual_days_per_month"]) != Decimal("0.00")
            or bool(row["carryover_enabled"])
            or row["carryover_limit_days"] is not None
            or row["created_by_user_id"] is not None
        ):
            counts["leave_policies_changed"] = counts.get("leave_policies_changed", 0) + 1

    expected_baseline_counts = {
        "leave_types": len(tenant_ids) * len(_STARTER_TYPES),
        "holiday_calendars": len(tenant_ids),
        "leave_policies": len(tenant_ids) * len(_STARTER_TYPES),
    }
    for table_name, expected_count in expected_baseline_counts.items():
        actual_count = int(connection.scalar(sa.text(f'SELECT count(*) FROM "{table_name}"')) or 0)
        if actual_count != expected_count:
            counts[f"{table_name}_count_mismatch"] = abs(actual_count - expected_count) or 1

    retained = {name: count for name, count in counts.items() if count}
    if retained:
        detail = ", ".join(f"{name}={count}" for name, count in sorted(retained.items()))
        raise RuntimeError(
            "P6 leave downgrade refused because it would discard retained history or "
            f"configuration: {detail}"
        )


def _remove_permissions() -> None:
    connection = op.get_bind()
    permissions = sa.table(
        "permissions",
        sa.column("id", _UUID),
        sa.column("code", sa.String()),
        sa.column("resource", sa.String()),
        sa.column("action", sa.String()),
        sa.column("target", sa.String()),
        sa.column("target_type", sa.String()),
        sa.column("description", sa.Text()),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", _UUID),
        sa.column("permission_id", _UUID),
    )
    for (
        permission_id,
        code,
        resource,
        action,
        target,
        description,
        role_codes,
    ) in reversed(_PERMISSIONS):
        row = (
            connection.execute(sa.select(permissions).where(permissions.c.id == permission_id))
            .mappings()
            .one_or_none()
        )
        expected = {
            "id": permission_id,
            "code": code,
            "resource": resource,
            "action": action,
            "target": target,
            "target_type": "scope",
            "description": description,
        }
        if row is None or any(str(row[key]) != str(value) for key, value in expected.items()):
            raise RuntimeError(f"P6 permission catalog changed; cannot remove {code}")
        expected_grants = {_ROLE_IDS[role_code] for role_code in role_codes}
        actual_grants = {
            _as_uuid(value)
            for value in connection.scalars(
                sa.select(role_permissions.c.role_id).where(
                    role_permissions.c.permission_id == permission_id
                )
            )
        }
        if actual_grants != expected_grants:
            raise RuntimeError(f"P6 permission grants changed; cannot remove {code}")
        connection.execute(
            sa.delete(role_permissions).where(role_permissions.c.permission_id == permission_id)
        )
        connection.execute(
            sa.delete(permissions).where(
                permissions.c.id == permission_id,
                permissions.c.code == code,
            )
        )


def _remove_manager_own_document_read_grant() -> None:
    connection = op.get_bind()
    permissions = sa.table(
        "permissions",
        sa.column("id", _UUID),
        sa.column("code", sa.String()),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", _UUID),
        sa.column("permission_id", _UUID),
    )
    permission = (
        connection.execute(
            sa.select(permissions).where(
                permissions.c.id == _OWN_DOCUMENT_READ_PERMISSION_ID,
                permissions.c.code == _OWN_DOCUMENT_READ_PERMISSION_CODE,
            )
        )
        .mappings()
        .one_or_none()
    )
    if permission is None:
        raise RuntimeError("P6 own-document read permission changed; cannot remove manager grant")
    expected_roles = {
        _ROLE_IDS["hr_director"],
        _ROLE_IDS["hr_specialist"],
        _ROLE_IDS["manager"],
        _ROLE_IDS["employee"],
    }
    actual_roles = {
        _as_uuid(value)
        for value in connection.scalars(
            sa.select(role_permissions.c.role_id).where(
                role_permissions.c.permission_id == _OWN_DOCUMENT_READ_PERMISSION_ID
            )
        )
    }
    if actual_roles != expected_roles:
        raise RuntimeError("P6 own-document read grants changed; cannot remove manager grant")
    connection.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.role_id == _ROLE_IDS["manager"],
            role_permissions.c.permission_id == _OWN_DOCUMENT_READ_PERMISSION_ID,
        )
    )


def _drop_request_expansion() -> None:
    for index_name in (
        "ix_leave_requests_tenant_type_start",
        "ix_leave_requests_tenant_employee_status_dates",
        "ix_leave_requests_tenant_manager_status_created",
    ):
        op.drop_index(index_name, table_name="leave_requests")
    with op.batch_alter_table("leave_requests") as batch_op:
        for constraint_name in (
            "fk_leave_requests_tenant_document",
            "fk_leave_requests_tenant_routed_manager_user",
            "fk_leave_requests_tenant_requested_by_membership",
            "fk_leave_requests_tenant_type_policy",
            "fk_leave_requests_tenant_leave_type",
        ):
            batch_op.drop_constraint(constraint_name, type_="foreignkey")
        for constraint_name in (
            "ck_leave_requests_decision_state",
            "ck_leave_requests_version_positive",
            "ck_leave_requests_supported_dates",
            "ck_leave_requests_counted_days_non_negative",
        ):
            batch_op.drop_constraint(constraint_name, type_="check")
        batch_op.drop_constraint("uq_leave_requests_tenant_id_id", type_="unique")
        for column_name in (
            "decided_at",
            "version",
            "counted_days",
            "employee_note",
            "document_id",
            "routed_manager_user_id",
            "requested_by_membership_id",
            "policy_id",
            "leave_type_id",
        ):
            batch_op.drop_column(column_name)


def _restore_legacy_postgresql_security() -> None:
    legacy_request_columns = (
        "id",
        "tenant_id",
        "employee_id",
        "leave_type",
        "start_date",
        "end_date",
        "status",
        "requested_by_user_id",
        "decided_by_user_id",
        "decision_note",
        "created_at",
        "updated_at",
    )
    _reset_postgresql_acl("leave_requests", legacy_request_columns)
    grant_table_privileges(
        op,
        table_name="leave_requests",
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT", "UPDATE"),
    )
    enable_forced_row_security(op, table_name="leave_requests")
    enable_forced_row_security(op, table_name="employee_documents")


def _migration_table(table_name: str) -> sa.TableClause:
    columns: dict[str, tuple[sa.ColumnClause[object], ...]] = {
        "tenants": (sa.column("id", _UUID),),
        "leave_requests": (
            sa.column("id", _UUID),
            sa.column("tenant_id", _UUID),
            sa.column("employee_id", _UUID),
            sa.column("leave_type", sa.String(64)),
            sa.column("start_date", sa.Date()),
            sa.column("end_date", sa.Date()),
            sa.column("status", sa.String(32)),
            sa.column("requested_by_user_id", _UUID),
            sa.column("decided_by_user_id", _UUID),
            sa.column("decision_note", sa.Text()),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
            sa.column("leave_type_id", _UUID),
            sa.column("policy_id", _UUID),
            sa.column("requested_by_membership_id", _UUID),
            sa.column("routed_manager_user_id", _UUID),
            sa.column("document_id", _UUID),
            sa.column("employee_note", sa.Text()),
            sa.column("counted_days", sa.Numeric(8, 2)),
            sa.column("version", sa.Integer()),
            sa.column("decided_at", sa.DateTime(timezone=True)),
        ),
        "leave_balance_summaries": (
            sa.column("id", _UUID),
            sa.column("tenant_id", _UUID),
            sa.column("employee_id", _UUID),
            sa.column("leave_type", sa.String(64)),
            sa.column("period_year", sa.Integer()),
            sa.column("opening_balance_days", sa.Float()),
            sa.column("used_days", sa.Float()),
            sa.column("planned_days", sa.Float()),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        "leave_request_days": (
            sa.column("id", _UUID),
            sa.column("tenant_id", _UUID),
            sa.column("request_id", _UUID),
            sa.column("leave_date", sa.Date()),
            sa.column("is_working_day", sa.Boolean()),
            sa.column("is_holiday", sa.Boolean()),
            sa.column("counted_days", sa.Numeric(8, 2)),
            sa.column("holiday_entry_id", _UUID),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        "leave_request_timeline": (
            sa.column("id", _UUID),
            sa.column("tenant_id", _UUID),
            sa.column("request_id", _UUID),
            sa.column("event_type", sa.String(32)),
            sa.column("status", sa.String(32)),
            sa.column("actor_user_id", _UUID),
            sa.column("source_key", sa.String(160)),
            sa.column("occurred_at", sa.DateTime(timezone=True)),
        ),
        "leave_balance_ledger": (
            sa.column("id", _UUID),
            sa.column("tenant_id", _UUID),
            sa.column("employee_id", _UUID),
            sa.column("leave_type_id", _UUID),
            sa.column("period_year", sa.Integer()),
            sa.column("entry_type", sa.String(32)),
            sa.column("amount_days", sa.Numeric(10, 2)),
            sa.column("effective_date", sa.Date()),
            sa.column("reason", sa.String(500)),
            sa.column("request_id", _UUID),
            sa.column("source_type", sa.String(64)),
            sa.column("source_id", _UUID),
            sa.column("source_key", sa.String(160)),
            sa.column("reversal_of_entry_id", _UUID),
            sa.column("created_by_user_id", _UUID),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
    }
    try:
        return sa.table(table_name, *columns[table_name])
    except KeyError as exc:  # pragma: no cover - frozen migration guard
        raise RuntimeError(f"Unknown P6 migration table: {table_name}") from exc


def _leave_types_seed_table() -> sa.TableClause:
    return sa.table(
        "leave_types",
        sa.column("id", _UUID),
        sa.column("tenant_id", _UUID),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("version", sa.Integer()),
    )


def _holiday_calendars_seed_table() -> sa.TableClause:
    return sa.table(
        "holiday_calendars",
        sa.column("id", _UUID),
        sa.column("tenant_id", _UUID),
        sa.column("name", sa.String()),
        sa.column("is_default", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        sa.column("non_working_weekdays", _JSON),
        sa.column("version", sa.Integer()),
    )


def _leave_policies_seed_table() -> sa.TableClause:
    return sa.table(
        "leave_policies",
        sa.column("id", _UUID),
        sa.column("tenant_id", _UUID),
        sa.column("leave_type_id", _UUID),
        sa.column("version", sa.Integer()),
        sa.column("effective_from", sa.Date()),
        sa.column("paid", sa.Boolean()),
        sa.column("document_required", sa.Boolean()),
        sa.column("negative_balance_allowed", sa.Boolean()),
        sa.column("accrual_enabled", sa.Boolean()),
        sa.column("accrual_days_per_month", sa.Numeric(8, 2)),
        sa.column("carryover_enabled", sa.Boolean()),
        sa.column("carryover_limit_days", sa.Numeric(8, 2)),
        sa.column("created_by_user_id", _UUID),
    )


def _execute_in_chunks(
    statement: sa.Executable,
    rows: list[dict[str, object]],
    *,
    chunk_size: int = 500,
) -> None:
    connection = op.get_bind()
    for offset in range(0, len(rows), chunk_size):
        connection.execute(statement, rows[offset : offset + chunk_size])


def _deterministic_uuid(value: str) -> UUID:
    digest = hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()
    return UUID(digest, version=4)


def _as_uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    rendered = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(rendered)


def _as_decimal(value: object) -> Decimal:
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RuntimeError(f"P6 leave migration found invalid numeric value: {value!r}") from exc
    if not decimal_value.is_finite():
        raise RuntimeError(f"P6 leave migration found non-finite numeric value: {value!r}")
    return decimal_value


def _legacy_decimal(
    value: object,
    *,
    summary_id: object,
    field_name: str,
) -> Decimal:
    decimal_value = _as_decimal(value)
    try:
        quantized = decimal_value.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise RuntimeError(
            "P6 leave migration found an out-of-range legacy balance: "
            f"summary_id={summary_id}, field={field_name}, value={value!r}"
        ) from exc
    if (
        decimal_value != quantized
        or quantized < Decimal("0.00")
        or quantized > Decimal("99999999.99")
    ):
        raise RuntimeError(
            "P6 leave migration cannot safely represent legacy balance: "
            f"summary_id={summary_id}, field={field_name}, value={value!r}"
        )
    return quantized
