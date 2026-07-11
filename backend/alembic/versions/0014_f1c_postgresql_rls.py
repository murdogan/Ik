"""establish PostgreSQL tenant row security and capability roles

Revision ID: 0014_f1c_postgresql_rls
Revises: 0013_tenant_settings
Create Date: 2026-07-11
"""

from collections.abc import Sequence

from alembic import op
from app.platform.db.rls_migration import (
    assert_capability_role_has_no_parent_memberships,
    create_tenant_isolation_policy,
    create_unrestricted_insert_policy,
    create_unrestricted_role_policy,
    disable_forced_row_security,
    drop_policy,
    enable_forced_row_security,
    ensure_capability_role,
    grant_column_privilege,
    grant_schema_usage,
    grant_table_privileges,
    revoke_all_column_privileges,
    revoke_all_schema_privileges,
    revoke_all_table_privileges,
    revoke_column_privilege,
    revoke_schema_usage,
    revoke_table_privileges,
)
from app.platform.db.tenant_access import (
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)

revision: str = "0014_f1c_postgresql_rls"
down_revision: str | None = "0013_tenant_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA_NAME = "public"
_TENANT_POLICY_NAME = "tenant_isolation_app"
_PLATFORM_POLICY_NAME = "platform_operations"
_PLATFORM_SETTINGS_POLICY_NAME = "platform_provision_settings"

# Frozen revision inventory. Future tenant-owned tables must receive RLS in their own migration.
TENANT_OWNED_TABLES = (
    "users",
    "employees",
    "leave_requests",
    "leave_balance_summaries",
    "command_idempotency",
    "tenant_settings",
)
_ROW_SECURITY_TABLES = ("tenants", *TENANT_OWNED_TABLES)
_PLATFORM_TABLES = ("tenants", "tenant_settings")
_ROW_SECURITY_TABLE_COLUMNS = {
    "tenants": (
        "id",
        "slug",
        "name",
        "status",
        "plan_code",
        "data_region",
        "locale",
        "timezone",
        "created_at",
        "updated_at",
    ),
    "users": (
        "id",
        "tenant_id",
        "email",
        "full_name",
        "status",
        "password_hash",
        "created_at",
        "updated_at",
    ),
    "employees": (
        "id",
        "tenant_id",
        "employee_number",
        "first_name",
        "last_name",
        "email",
        "department",
        "department_normalized",
        "position",
        "status",
        "employment_start_date",
        "employment_end_date",
        "archived_at",
        "created_at",
        "updated_at",
    ),
    "leave_requests": (
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
    ),
    "leave_balance_summaries": (
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
    ),
    "command_idempotency": (
        "id",
        "tenant_id",
        "idempotency_key",
        "command_name",
        "request_fingerprint",
        "resource_id",
        "response_payload",
        "created_at",
        "completed_at",
    ),
    "tenant_settings": (
        "tenant_id",
        "week_start_day",
        "date_format",
        "time_format",
        "created_at",
        "updated_at",
    ),
}

# Privileges reflect the current product paths. Neither capability role receives DELETE.
APPLICATION_TABLE_PRIVILEGES = (
    ("tenants", ("SELECT",)),
    ("users", ("SELECT",)),
    ("employees", ("SELECT", "INSERT", "UPDATE")),
    ("leave_requests", ("SELECT", "INSERT", "UPDATE")),
    ("leave_balance_summaries", ("SELECT",)),
    ("command_idempotency", ("SELECT", "INSERT", "UPDATE")),
    ("tenant_settings", ("SELECT", "INSERT", "UPDATE")),
)
APPLICATION_COLUMN_PRIVILEGES = (
    ("tenants", "UPDATE", ("locale", "timezone", "updated_at")),
)
PLATFORM_TABLE_PRIVILEGES = (
    ("tenants", ("SELECT", "INSERT", "UPDATE")),
    ("tenant_settings", ("INSERT",)),
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for role_name in (TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE):
        ensure_capability_role(op, role_name)
        assert_capability_role_has_no_parent_memberships(op, role_name)
        revoke_all_schema_privileges(
            op,
            schema_name=_SCHEMA_NAME,
            role_name=role_name,
        )
        grant_schema_usage(op, schema_name=_SCHEMA_NAME, role_name=role_name)
        for table_name in _ROW_SECURITY_TABLES:
            revoke_all_table_privileges(
                op,
                table_name=table_name,
                role_name=role_name,
            )
            revoke_all_column_privileges(
                op,
                table_name=table_name,
                role_name=role_name,
                column_names=_ROW_SECURITY_TABLE_COLUMNS[table_name],
            )

    for table_name in _ROW_SECURITY_TABLES:
        enable_forced_row_security(op, table_name=table_name)
        create_tenant_isolation_policy(
            op,
            table_name=table_name,
            policy_name=_TENANT_POLICY_NAME,
            role_name=TENANT_APPLICATION_ROLE,
            tenant_column="id" if table_name == "tenants" else "tenant_id",
        )

    create_unrestricted_role_policy(
        op,
        table_name="tenants",
        policy_name=_PLATFORM_POLICY_NAME,
        role_name=PLATFORM_APPLICATION_ROLE,
    )
    create_unrestricted_insert_policy(
        op,
        table_name="tenant_settings",
        policy_name=_PLATFORM_SETTINGS_POLICY_NAME,
        role_name=PLATFORM_APPLICATION_ROLE,
    )

    for table_name, privileges in APPLICATION_TABLE_PRIVILEGES:
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=TENANT_APPLICATION_ROLE,
            privileges=privileges,
        )
    for table_name, privilege, column_names in APPLICATION_COLUMN_PRIVILEGES:
        grant_column_privilege(
            op,
            table_name=table_name,
            role_name=TENANT_APPLICATION_ROLE,
            privilege=privilege,
            column_names=column_names,
        )
    for table_name, privileges in PLATFORM_TABLE_PRIVILEGES:
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=PLATFORM_APPLICATION_ROLE,
            privileges=privileges,
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table_name, privilege, column_names in reversed(
        APPLICATION_COLUMN_PRIVILEGES
    ):
        revoke_column_privilege(
            op,
            table_name=table_name,
            role_name=TENANT_APPLICATION_ROLE,
            privilege=privilege,
            column_names=column_names,
        )
    for table_name, privileges in reversed(PLATFORM_TABLE_PRIVILEGES):
        revoke_table_privileges(
            op,
            table_name=table_name,
            role_name=PLATFORM_APPLICATION_ROLE,
            privileges=privileges,
        )
    for table_name, privileges in reversed(APPLICATION_TABLE_PRIVILEGES):
        revoke_table_privileges(
            op,
            table_name=table_name,
            role_name=TENANT_APPLICATION_ROLE,
            privileges=privileges,
        )

    drop_policy(
        op,
        table_name="tenant_settings",
        policy_name=_PLATFORM_SETTINGS_POLICY_NAME,
    )
    drop_policy(op, table_name="tenants", policy_name=_PLATFORM_POLICY_NAME)
    for table_name in reversed(_ROW_SECURITY_TABLES):
        drop_policy(op, table_name=table_name, policy_name=_TENANT_POLICY_NAME)
        disable_forced_row_security(op, table_name=table_name)

    for role_name in (PLATFORM_APPLICATION_ROLE, TENANT_APPLICATION_ROLE):
        revoke_schema_usage(op, schema_name=_SCHEMA_NAME, role_name=role_name)

    # Capability roles are cluster-global and may be shared by another database. Downgrade removes
    # only this database's policies and grants; it intentionally never drops either role.
