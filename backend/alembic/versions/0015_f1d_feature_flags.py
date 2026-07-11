"""add tenant feature rollout state and configured employee limits

Revision ID: 0015_f1d_feature_flags
Revises: 0014_f1c_postgresql_rls
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    create_tenant_isolation_policy,
    create_unrestricted_role_policy,
    disable_forced_row_security,
    drop_policy,
    enable_forced_row_security,
    grant_table_privileges,
    revoke_all_table_privileges,
    revoke_table_privileges,
)
from app.platform.db.tenant_access import (
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy.dialects import postgresql

revision: str = "0015_f1d_feature_flags"
down_revision: str | None = "0014_f1c_postgresql_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FEATURE_TABLE = "tenant_feature_flags"
_TENANT_POLICY = "tenant_isolation_app"
_PLATFORM_POLICY = "platform_feature_operations"
_ACTIVE_EMPLOYEE_LIMIT_CHECK = "ck_tenants_active_employee_limit_positive"
_FEATURE_KEY_CHECK = "ck_tenant_feature_flags_key"
_FEATURE_ENABLED_CHECK = "ck_tenant_feature_flags_enabled"

# This inventory is frozen into the revision. Changing the live Python catalog later must not
# rewrite the meaning of an already-published migration or its downgrade retention preflight.
_FEATURE_DEFAULTS = (
    ("organization", False),
    ("employees", True),
    ("documents", False),
    ("leave", True),
    ("self_service", False),
    ("reporting", True),
    ("notifications", False),
)


def upgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    _add_active_employee_limit()
    op.create_table(
        _FEATURE_TABLE,
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint(
            "key in ("
            "'organization','employees','documents','leave','self_service','reporting',"
            "'notifications'"
            ")",
            name=_FEATURE_KEY_CHECK,
        ),
        sa.CheckConstraint(
            "enabled in (false, true)",
            name=_FEATURE_ENABLED_CHECK,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_feature_flags_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "key",
            name="pk_tenant_feature_flags",
        ),
    )
    if is_postgresql:
        # Hostile ALTER DEFAULT PRIVILEGES must not broaden this capability table. PUBLIC is a
        # PostgreSQL pseudo-role and intentionally remains unquoted; named capability roles use
        # the shared identifier-safe helper.
        op.execute(
            sa.text(
                'REVOKE ALL PRIVILEGES ON TABLE "tenant_feature_flags" FROM PUBLIC'
            )
        )
        for role_name in (TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE):
            revoke_all_table_privileges(
                op,
                table_name=_FEATURE_TABLE,
                role_name=role_name,
            )
    if is_postgresql:
        # F1C forces RLS even for the table owner. Alembic's migration owner is deliberately not
        # assumed to be a superuser/BYPASSRLS role, so the owner-only backfill temporarily removes
        # and then restores the tenant-root RLS flags in this transactional DDL migration.
        disable_forced_row_security(op, table_name="tenants")
    _backfill_feature_defaults()
    if is_postgresql:
        enable_forced_row_security(op, table_name="tenants")

    if not is_postgresql:
        return

    enable_forced_row_security(op, table_name=_FEATURE_TABLE)
    create_tenant_isolation_policy(
        op,
        table_name=_FEATURE_TABLE,
        policy_name=_TENANT_POLICY,
        role_name=TENANT_APPLICATION_ROLE,
    )
    create_unrestricted_role_policy(
        op,
        table_name=_FEATURE_TABLE,
        policy_name=_PLATFORM_POLICY,
        role_name=PLATFORM_APPLICATION_ROLE,
    )
    grant_table_privileges(
        op,
        table_name=_FEATURE_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT",),
    )
    grant_table_privileges(
        op,
        table_name=_FEATURE_TABLE,
        role_name=PLATFORM_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT", "UPDATE"),
    )


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        # Both table owners are subject to FORCE RLS. Transactional DDL restores the prior flags
        # automatically if the retention preflight raises.
        disable_forced_row_security(op, table_name=_FEATURE_TABLE)
        disable_forced_row_security(op, table_name="tenants")

    _assert_downgrade_is_safe()

    if is_postgresql:
        enable_forced_row_security(op, table_name="tenants")
        revoke_table_privileges(
            op,
            table_name=_FEATURE_TABLE,
            role_name=PLATFORM_APPLICATION_ROLE,
            privileges=("SELECT", "INSERT", "UPDATE"),
        )
        revoke_table_privileges(
            op,
            table_name=_FEATURE_TABLE,
            role_name=TENANT_APPLICATION_ROLE,
            privileges=("SELECT",),
        )
        drop_policy(
            op,
            table_name=_FEATURE_TABLE,
            policy_name=_PLATFORM_POLICY,
        )
        drop_policy(
            op,
            table_name=_FEATURE_TABLE,
            policy_name=_TENANT_POLICY,
        )

    op.drop_table(_FEATURE_TABLE)
    _drop_active_employee_limit()


def _add_active_employee_limit() -> None:
    column = sa.Column("active_employee_limit", sa.Integer(), nullable=True)
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("tenants") as batch_op:
            batch_op.add_column(column)
            batch_op.create_check_constraint(
                _ACTIVE_EMPLOYEE_LIMIT_CHECK,
                "active_employee_limit is null or active_employee_limit between 1 and 1000000",
            )
        return

    op.add_column("tenants", column)
    op.create_check_constraint(
        _ACTIVE_EMPLOYEE_LIMIT_CHECK,
        "tenants",
        "active_employee_limit is null or active_employee_limit between 1 and 1000000",
    )


def _drop_active_employee_limit() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("tenants") as batch_op:
            batch_op.drop_constraint(_ACTIVE_EMPLOYEE_LIMIT_CHECK, type_="check")
            batch_op.drop_column("active_employee_limit")
        return

    op.drop_constraint(_ACTIVE_EMPLOYEE_LIMIT_CHECK, "tenants", type_="check")
    op.drop_column("tenants", "active_employee_limit")


def _backfill_feature_defaults() -> None:
    for key, enabled in _FEATURE_DEFAULTS:
        enabled_literal = "true" if enabled else "false"
        op.execute(
            sa.text(
                "insert into tenant_feature_flags ("
                "tenant_id, key, enabled, created_at, updated_at"
                ") select id, "
                f"'{key}', {enabled_literal}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
                "from tenants"
            )
        )


def _assert_downgrade_is_safe() -> None:
    override_predicate = (
        "enabled <> case key "
        "when 'employees' then true "
        "when 'leave' then true "
        "when 'reporting' then true "
        "else false end"
    )
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $f1d_downgrade_preflight$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM tenant_feature_flags WHERE {override_predicate}
                    ) OR EXISTS (
                        SELECT 1 FROM tenants WHERE active_employee_limit IS NOT NULL
                    ) THEN
                        RAISE EXCEPTION
                            'F1D downgrade preflight failed; restore feature defaults and clear '
                            'configured active employee limits before retrying';
                    END IF;
                END
                $f1d_downgrade_preflight$
                """
            )
        )
        return

    connection = op.get_bind()
    feature_override_count = int(
        connection.scalar(
            sa.text(
                "select count(*) from tenant_feature_flags where "
                f"{override_predicate}"
            )
        )
        or 0
    )
    configured_limit_count = int(
        connection.scalar(
            sa.text(
                "select count(*) from tenants where active_employee_limit is not null"
            )
        )
        or 0
    )
    if feature_override_count == 0 and configured_limit_count == 0:
        return

    raise RuntimeError(
        "F1D downgrade preflight failed; restore defaults/clear configured metadata before "
        f"retrying: feature_overrides={feature_override_count}, "
        f"configured_active_employee_limits={configured_limit_count}"
    )
