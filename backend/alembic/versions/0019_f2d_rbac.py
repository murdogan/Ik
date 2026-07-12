"""add F2D role catalog, tenant assignments, and permission versioning

Revision ID: 0019_f2d_rbac
Revises: 0018_f2c_user_administration
Create Date: 2026-07-12
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    create_tenant_isolation_policy,
    disable_forced_row_security,
    drop_policy,
    enable_forced_row_security,
    grant_column_privilege,
    grant_table_privileges,
    revoke_all_column_privileges,
    revoke_all_table_privileges,
)
from app.platform.db.tenant_access import (
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy.dialects import postgresql

revision: str = "0019_f2d_rbac"
down_revision: str | None = "0018_f2c_user_administration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLES_TABLE = "roles"
_PERMISSIONS_TABLE = "permissions"
_ROLE_PERMISSIONS_TABLE = "role_permissions"
_USER_ROLES_TABLE = "user_roles"
_USERS_TABLE = "users"
_TENANT_POLICY = "tenant_isolation_app"

_ROLE_COLUMNS = (
    "id",
    "code",
    "name",
    "description",
    "scope_type",
    "system_role",
    "created_at",
    "updated_at",
)
_PERMISSION_COLUMNS = (
    "id",
    "code",
    "resource",
    "action",
    "target",
    "target_type",
    "description",
    "created_at",
    "updated_at",
)
_ROLE_PERMISSION_COLUMNS = ("role_id", "permission_id")
_USER_ROLE_COLUMNS = (
    "tenant_id",
    "user_id",
    "role_id",
    "role_scope_type",
    "active",
    "created_at",
    "updated_at",
)
_USER_COLUMNS = (
    "id",
    "tenant_id",
    "email",
    "email_normalized",
    "full_name",
    "status",
    "password_hash",
    "can_invite_users",
    "permission_version",
    "created_at",
    "updated_at",
)
_USER_RUNTIME_INSERT_COLUMNS = (
    "id",
    "tenant_id",
    "email",
    "full_name",
    "status",
    "password_hash",
)
_USER_RUNTIME_UPDATE_COLUMNS = (
    "email",
    "full_name",
    "status",
    "password_hash",
    "permission_version",
    "updated_at",
)
_PRE_F2D_USER_RUNTIME_UPDATE_COLUMNS = tuple(
    column for column in _USER_RUNTIME_UPDATE_COLUMNS if column != "permission_version"
)


def _catalog_uuid(prefix: str, ordinal: int) -> UUID:
    return UUID(f"{prefix}000000-0000-4000-8000-{ordinal:012d}")


# Frozen seed inventory. Do not replace this revision's constants with live ORM/application
# metadata: historical migrations must continue rendering the exact F2D catalog.
_ROLE_ROWS = (
    (
        _catalog_uuid("d2", 1),
        "super_admin",
        "Platform super admin",
        "Operates platform tenant metadata without implicit customer HR access.",
        "platform",
    ),
    (
        _catalog_uuid("d2", 2),
        "tenant_admin",
        "Tenant admin",
        "Administers tenant settings, users, roles, and application access.",
        "tenant",
    ),
    (
        _catalog_uuid("d2", 3),
        "hr_director",
        "HR director",
        "Leads tenant-wide HR operations and compliance visibility.",
        "tenant",
    ),
    (
        _catalog_uuid("d2", 4),
        "hr_specialist",
        "HR specialist",
        "Runs day-to-day HR operations within granted organizational scopes.",
        "tenant",
    ),
    (
        _catalog_uuid("d2", 5),
        "it_admin",
        "IT admin",
        "Manages tenant identity and session operations without HR-data access.",
        "tenant",
    ),
    (
        _catalog_uuid("d2", 6),
        "auditor",
        "Auditor",
        "Reads authorized tenant audit history without mutation privileges.",
        "tenant",
    ),
    (
        _catalog_uuid("d2", 7),
        "manager",
        "Manager",
        "Reads team information and handles team leave approvals.",
        "tenant",
    ),
    (
        _catalog_uuid("d2", 8),
        "employee",
        "Employee",
        "Uses employee self-service within own-data scope.",
        "tenant",
    ),
)

_PERMISSION_ROWS = (
    (_catalog_uuid("d3", 1), "tenant:read:tenant", "Read current-tenant metadata."),
    (
        _catalog_uuid("d3", 2),
        "tenant:update:tenant",
        "Update allowlisted current-tenant settings.",
    ),
    (
        _catalog_uuid("d3", 3),
        "dashboard:read:tenant",
        "Read tenant-wide dashboard summaries.",
    ),
    (_catalog_uuid("d3", 4), "dashboard:read:own", "Read the current user's dashboard."),
    (_catalog_uuid("d3", 5), "user:read:tenant", "Read users in the current tenant."),
    (_catalog_uuid("d3", 6), "user:update:tenant", "Update users in the current tenant."),
    (_catalog_uuid("d3", 7), "user:invite:tenant", "Invite users to the current tenant."),
    (_catalog_uuid("d3", 8), "role:read:tenant", "Read tenant-assignable roles."),
    (
        _catalog_uuid("d3", 9),
        "role:assign:tenant",
        "Replace a tenant user's role assignments.",
    ),
    (
        _catalog_uuid("d3", 10),
        "permission:read:tenant",
        "Read the tenant permission catalog.",
    ),
    (
        _catalog_uuid("d3", 11),
        "session:manage:tenant",
        "Manage user sessions in the current tenant.",
    ),
    (
        _catalog_uuid("d3", 12),
        "employee:read:own",
        "Read the current user's employee record.",
    ),
    (
        _catalog_uuid("d3", 13),
        "employee:read:team",
        "Read employee records in the current user's team.",
    ),
    (
        _catalog_uuid("d3", 14),
        "employee:read:department",
        "Read employee records in scope departments.",
    ),
    (
        _catalog_uuid("d3", 15),
        "employee:read:branch",
        "Read employee records in scope branches.",
    ),
    (
        _catalog_uuid("d3", 16),
        "employee:read:tenant",
        "Read employee records across the current tenant.",
    ),
    (
        _catalog_uuid("d3", 17),
        "employee:update:tenant",
        "Update employee records across the tenant.",
    ),
    (_catalog_uuid("d3", 18), "leave:read:own", "Read the current user's leave records."),
    (
        _catalog_uuid("d3", 19),
        "leave:read:team",
        "Read leave records in the current user's team.",
    ),
    (
        _catalog_uuid("d3", 20),
        "leave:read:department",
        "Read leave records in scope departments.",
    ),
    (
        _catalog_uuid("d3", 21),
        "leave:read:branch",
        "Read leave records in scope branches.",
    ),
    (
        _catalog_uuid("d3", 22),
        "leave:read:tenant",
        "Read leave records across the current tenant.",
    ),
    (
        _catalog_uuid("d3", 23),
        "leave:approve:team",
        "Approve leave requests in the current user's team.",
    ),
    (
        _catalog_uuid("d3", 24),
        "audit:read:tenant",
        "Read authorized audit history in the tenant.",
    ),
    (
        _catalog_uuid("d3", 25),
        "tenant:read:platform",
        "Read platform-safe tenant metadata.",
    ),
    (
        _catalog_uuid("d3", 26),
        "tenant:create:platform",
        "Provision a tenant through platform operations.",
    ),
    (
        _catalog_uuid("d3", 27),
        "tenant:update:platform",
        "Update platform-safe tenant metadata.",
    ),
    (
        _catalog_uuid("d3", 28),
        "feature:read:platform",
        "Read platform feature rollout metadata.",
    ),
    (
        _catalog_uuid("d3", 29),
        "feature:update:platform",
        "Update platform feature rollout metadata.",
    ),
)

_ROLE_GRANTS = {
    "super_admin": (
        "tenant:read:platform",
        "tenant:create:platform",
        "tenant:update:platform",
        "feature:read:platform",
        "feature:update:platform",
    ),
    "tenant_admin": (
        "tenant:read:tenant",
        "tenant:update:tenant",
        "dashboard:read:tenant",
        "dashboard:read:own",
        "user:read:tenant",
        "user:update:tenant",
        "user:invite:tenant",
        "role:read:tenant",
        "role:assign:tenant",
        "permission:read:tenant",
    ),
    "hr_director": (
        "dashboard:read:tenant",
        "dashboard:read:own",
        "employee:read:own",
        "employee:read:team",
        "employee:read:department",
        "employee:read:branch",
        "employee:read:tenant",
        "employee:update:tenant",
        "leave:read:own",
        "leave:read:team",
        "leave:read:department",
        "leave:read:branch",
        "leave:read:tenant",
        "audit:read:tenant",
    ),
    "hr_specialist": (
        "dashboard:read:tenant",
        "dashboard:read:own",
        "employee:read:own",
        "employee:read:department",
        "employee:read:branch",
        "employee:read:tenant",
        "employee:update:tenant",
        "leave:read:own",
        "leave:read:department",
        "leave:read:branch",
        "leave:read:tenant",
    ),
    "it_admin": (
        "dashboard:read:own",
        "user:read:tenant",
        "session:manage:tenant",
    ),
    "auditor": ("dashboard:read:own", "audit:read:tenant"),
    "manager": (
        "dashboard:read:own",
        "employee:read:own",
        "employee:read:team",
        "leave:read:own",
        "leave:read:team",
        "leave:approve:team",
    ),
    "employee": (
        "dashboard:read:own",
        "employee:read:own",
        "leave:read:own",
    ),
}


def upgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    _add_permission_version()
    _create_roles_table()
    _create_permissions_table()
    _create_role_permissions_table()
    _create_user_roles_table()
    _seed_catalog()
    if is_postgresql:
        # F1C FORCE RLS also applies to the table owner. Temporarily restore the owner's normal
        # RLS bypass so this migration can see and backfill every tenant user, then force the
        # boundary again before configuring runtime grants.
        disable_forced_row_security(op, table_name=_USERS_TABLE)
    _backfill_user_roles()
    if is_postgresql:
        enable_forced_row_security(op, table_name=_USERS_TABLE)

    if is_postgresql:
        _configure_postgresql_security()


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        disable_forced_row_security(op, table_name=_USERS_TABLE)
    _assert_downgrade_has_no_authorization_changes()
    if is_postgresql:
        enable_forced_row_security(op, table_name=_USERS_TABLE)
        _remove_postgresql_security()

    op.drop_table(_USER_ROLES_TABLE)
    op.drop_table(_ROLE_PERMISSIONS_TABLE)
    op.drop_table(_PERMISSIONS_TABLE)
    op.drop_table(_ROLES_TABLE)
    _drop_permission_version()


def _assert_downgrade_has_no_authorization_changes() -> None:
    drift_count_sql = (
        "select count(*) from users as u where "
        "u.permission_version <> 1 or "
        "exists (select 1 from user_roles as inactive_role "
        "where inactive_role.tenant_id = u.tenant_id "
        "and inactive_role.user_id = u.id and inactive_role.active = false) or "
        "1 <> (select count(*) from user_roles as active_role "
        "where active_role.tenant_id = u.tenant_id "
        "and active_role.user_id = u.id and active_role.active = true) or "
        "not exists (select 1 from user_roles as expected_assignment "
        "join roles as expected_role on expected_role.id = expected_assignment.role_id "
        "and expected_role.scope_type = expected_assignment.role_scope_type "
        "where expected_assignment.tenant_id = u.tenant_id "
        "and expected_assignment.user_id = u.id and expected_assignment.active = true "
        "and expected_role.code = case when u.can_invite_users = true "
        "then 'tenant_admin' else 'employee' end)"
    )
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $f2d_rbac_downgrade_preflight$
                DECLARE
                    drift_count bigint;
                BEGIN
                    drift_count := ({drift_count_sql});
                    IF drift_count > 0 THEN
                        RAISE EXCEPTION
                            'F2D downgrade preflight failed: changed_authorization_users=%',
                            drift_count;
                    END IF;
                END
                $f2d_rbac_downgrade_preflight$
                """
            )
        )
        return

    drift_count = int(op.get_bind().execute(sa.text(drift_count_sql)).scalar_one())
    if drift_count:
        raise RuntimeError(
            "F2D downgrade preflight failed: "
            f"changed_authorization_users={drift_count}"
        )


def _add_permission_version() -> None:
    if op.get_bind().dialect.name == "sqlite":
        # A native ADD COLUMN keeps SQLite's stored generated email column intact. Alembic batch
        # recreation would try to copy that generated value explicitly, which SQLite forbids.
        op.add_column(
            _USERS_TABLE,
            sa.Column(
                "permission_version",
                sa.Integer(),
                sa.CheckConstraint(
                    "permission_version >= 1",
                    name="ck_users_permission_version_positive",
                ),
                server_default=sa.text("1"),
                nullable=False,
            ),
        )
        return

    op.add_column(
        _USERS_TABLE,
        sa.Column(
            "permission_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_users_permission_version_positive",
        _USERS_TABLE,
        "permission_version >= 1",
    )


def _drop_permission_version() -> None:
    if op.get_bind().dialect.name == "sqlite":
        # The named single-column CHECK is removed with its column by modern SQLite. Avoid batch
        # recreation for the same generated-column reason documented in the upgrade.
        op.drop_column(_USERS_TABLE, "permission_version")
        return

    op.drop_constraint(
        "ck_users_permission_version_positive",
        _USERS_TABLE,
        type_="check",
    )
    op.drop_column(_USERS_TABLE, "permission_version")


def _timestamp_columns() -> tuple[sa.Column, sa.Column]:
    return (
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
    )


def _create_roles_table() -> None:
    op.create_table(
        _ROLES_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column(
            "system_role",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "scope_type in ('platform','tenant')",
            name="ck_roles_scope_type",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("code", name="uq_roles_code"),
        sa.UniqueConstraint("id", "scope_type", name="uq_roles_id_scope_type"),
    )


def _create_permissions_table() -> None:
    op.create_table(
        _PERMISSIONS_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=160), nullable=False),
        sa.Column("resource", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "target_type in ('scope','field')",
            name="ck_permissions_target_type",
        ),
        sa.CheckConstraint(
            "target_type <> 'scope' or "
            "target in ('own','team','department','branch','tenant','platform')",
            name="ck_permissions_scope_target",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_permissions"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )


def _create_role_permissions_table() -> None:
    op.create_table(
        _ROLE_PERMISSIONS_TABLE,
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_role_permissions_role_id_roles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_role_permissions_permission_id_permissions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "role_id",
            "permission_id",
            name="pk_role_permissions",
        ),
    )


def _create_user_roles_table() -> None:
    op.create_table(
        _USER_ROLES_TABLE,
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role_scope_type",
            sa.String(length=16),
            server_default="tenant",
            nullable=False,
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "role_scope_type = 'tenant'",
            name="ck_user_roles_tenant_role_scope",
        ),
        sa.CheckConstraint(
            "active in (false, true)",
            name="ck_user_roles_active",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_user_roles_tenant_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id", "role_scope_type"],
            ["roles.id", "roles.scope_type"],
            name="fk_user_roles_role_id_scope_roles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "user_id",
            "role_id",
            name="pk_user_roles",
        ),
    )
    op.create_index(
        "ix_user_roles_tenant_user_active",
        _USER_ROLES_TABLE,
        ["tenant_id", "user_id", "active"],
        unique=False,
    )


def _seed_catalog() -> None:
    roles_seed = sa.table(
        _ROLES_TABLE,
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("name", sa.Text()),
        sa.column("description", sa.Text()),
        sa.column("scope_type", sa.String()),
        sa.column("system_role", sa.Boolean()),
    )
    op.bulk_insert(
        roles_seed,
        [
            {
                "id": role_id,
                "code": code,
                "name": name,
                "description": description,
                "scope_type": scope_type,
                "system_role": True,
            }
            for role_id, code, name, description, scope_type in _ROLE_ROWS
        ],
        multiinsert=False,
    )

    permissions_seed = sa.table(
        _PERMISSIONS_TABLE,
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("resource", sa.String()),
        sa.column("action", sa.String()),
        sa.column("target", sa.String()),
        sa.column("target_type", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        permissions_seed,
        [
            {
                "id": permission_id,
                "code": code,
                "resource": code.split(":")[0],
                "action": code.split(":")[1],
                "target": code.split(":")[2],
                "target_type": "scope",
                "description": description,
            }
            for permission_id, code, description in _PERMISSION_ROWS
        ],
        multiinsert=False,
    )

    role_ids = {code: role_id for role_id, code, *_rest in _ROLE_ROWS}
    permission_ids = {
        code: permission_id for permission_id, code, _description in _PERMISSION_ROWS
    }
    role_permissions_seed = sa.table(
        _ROLE_PERMISSIONS_TABLE,
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
        sa.column("permission_id", postgresql.UUID(as_uuid=True)),
    )
    op.bulk_insert(
        role_permissions_seed,
        [
            {
                "role_id": role_ids[role_code],
                "permission_id": permission_ids[permission_code],
            }
            for role_code, permission_codes in _ROLE_GRANTS.items()
            for permission_code in permission_codes
        ],
        multiinsert=False,
    )


def _backfill_user_roles() -> None:
    role_ids = {code: role_id for role_id, code, *_rest in _ROLE_ROWS}
    statement = sa.text(
        "insert into user_roles (tenant_id, user_id, role_id, role_scope_type, active) "
        "select tenant_id, id, "
        "case when can_invite_users = true then :tenant_admin_id else :employee_id end, "
        "'tenant', true from users"
    ).bindparams(
        sa.bindparam(
            "tenant_admin_id",
            value=role_ids["tenant_admin"],
            type_=postgresql.UUID(as_uuid=True),
        ),
        sa.bindparam(
            "employee_id",
            value=role_ids["employee"],
            type_=postgresql.UUID(as_uuid=True),
        ),
    )
    op.execute(statement)


def _configure_postgresql_security() -> None:
    _reset_postgresql_acl(_USERS_TABLE, _USER_COLUMNS)
    grant_table_privileges(
        op,
        table_name=_USERS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT",),
    )
    grant_column_privilege(
        op,
        table_name=_USERS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="INSERT",
        column_names=_USER_RUNTIME_INSERT_COLUMNS,
    )
    grant_column_privilege(
        op,
        table_name=_USERS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_USER_RUNTIME_UPDATE_COLUMNS,
    )

    for table_name, column_names in (
        (_ROLES_TABLE, _ROLE_COLUMNS),
        (_PERMISSIONS_TABLE, _PERMISSION_COLUMNS),
        (_ROLE_PERMISSIONS_TABLE, _ROLE_PERMISSION_COLUMNS),
    ):
        _reset_postgresql_acl(table_name, column_names)
        for role_name in (TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE):
            grant_table_privileges(
                op,
                table_name=table_name,
                role_name=role_name,
                privileges=("SELECT",),
            )

    _reset_postgresql_acl(_USER_ROLES_TABLE, _USER_ROLE_COLUMNS)
    enable_forced_row_security(op, table_name=_USER_ROLES_TABLE)
    create_tenant_isolation_policy(
        op,
        table_name=_USER_ROLES_TABLE,
        policy_name=_TENANT_POLICY,
        role_name=TENANT_APPLICATION_ROLE,
    )
    grant_table_privileges(
        op,
        table_name=_USER_ROLES_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT", "UPDATE"),
    )


def _remove_postgresql_security() -> None:
    _reset_postgresql_acl(_USER_ROLES_TABLE, _USER_ROLE_COLUMNS)
    drop_policy(
        op,
        table_name=_USER_ROLES_TABLE,
        policy_name=_TENANT_POLICY,
    )
    disable_forced_row_security(op, table_name=_USER_ROLES_TABLE)

    for table_name, column_names in (
        (_ROLE_PERMISSIONS_TABLE, _ROLE_PERMISSION_COLUMNS),
        (_PERMISSIONS_TABLE, _PERMISSION_COLUMNS),
        (_ROLES_TABLE, _ROLE_COLUMNS),
    ):
        _reset_postgresql_acl(table_name, column_names)

    _reset_postgresql_acl(_USERS_TABLE, _USER_COLUMNS)
    grant_table_privileges(
        op,
        table_name=_USERS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT",),
    )
    grant_column_privilege(
        op,
        table_name=_USERS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="INSERT",
        column_names=_USER_RUNTIME_INSERT_COLUMNS,
    )
    grant_column_privilege(
        op,
        table_name=_USERS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_PRE_F2D_USER_RUNTIME_UPDATE_COLUMNS,
    )


def _reset_postgresql_acl(table_name: str, column_names: tuple[str, ...]) -> None:
    quoted_columns = ", ".join(f'"{column_name}"' for column_name in column_names)
    op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{table_name}" FROM PUBLIC'))
    op.execute(
        sa.text(
            f'REVOKE ALL PRIVILEGES ({quoted_columns}) '
            f'ON TABLE "{table_name}" FROM PUBLIC'
        )
    )
    for role_name in (TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE):
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


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
