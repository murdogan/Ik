"""add P3F tenant legal entities and branches

Revision ID: 0027_p3f_legal_entities_branches
Revises: 0026_p3e_identity_checkpoint
Create Date: 2026-07-13
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
    revoke_column_privilege,
    revoke_table_privileges,
)
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy.dialects import postgresql

revision: str = "0027_p3f_legal_entities_branches"
down_revision: str | None = "0026_p3e_identity_checkpoint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGAL_ENTITIES_TABLE = "legal_entities"
_BRANCHES_TABLE = "branches"
_TENANTS_TABLE = "tenants"
_PERMISSIONS_TABLE = "permissions"
_ROLE_PERMISSIONS_TABLE = "role_permissions"
_TENANT_POLICY = "tenant_isolation_app"
_PLATFORM_LEGAL_ENTITY_INSERT_POLICY = "platform_provision_legal_entity"

_TENANT_ADMIN_ROLE_ID = UUID("d2000000-0000-4000-8000-000000000002")
_HR_DIRECTOR_ROLE_ID = UUID("d2000000-0000-4000-8000-000000000003")
_HR_SPECIALIST_ROLE_ID = UUID("d2000000-0000-4000-8000-000000000004")
_AUDITOR_ROLE_ID = UUID("d2000000-0000-4000-8000-000000000006")
_ORGANIZATION_READ_PERMISSION_ID = UUID(
    "d3000000-0000-4000-8000-000000000031"
)
_ORGANIZATION_UPDATE_PERMISSION_ID = UUID(
    "d3000000-0000-4000-8000-000000000032"
)

_PERMISSION_ROWS = (
    (
        _ORGANIZATION_READ_PERMISSION_ID,
        "organization:read:tenant",
        "Read current-tenant organization settings.",
    ),
    (
        _ORGANIZATION_UPDATE_PERMISSION_ID,
        "organization:update:tenant",
        "Manage current-tenant organization settings.",
    ),
)
_ROLE_PERMISSION_ROWS = (
    (_TENANT_ADMIN_ROLE_ID, _ORGANIZATION_READ_PERMISSION_ID),
    (_TENANT_ADMIN_ROLE_ID, _ORGANIZATION_UPDATE_PERMISSION_ID),
    (_HR_DIRECTOR_ROLE_ID, _ORGANIZATION_READ_PERMISSION_ID),
    (_HR_DIRECTOR_ROLE_ID, _ORGANIZATION_UPDATE_PERMISSION_ID),
    (_HR_SPECIALIST_ROLE_ID, _ORGANIZATION_READ_PERMISSION_ID),
    (_HR_SPECIALIST_ROLE_ID, _ORGANIZATION_UPDATE_PERMISSION_ID),
    (_AUDITOR_ROLE_ID, _ORGANIZATION_READ_PERMISSION_ID),
)

_LEGAL_ENTITY_COLUMNS = (
    "id",
    "tenant_id",
    "code",
    "code_normalized",
    "name",
    "registered_name",
    "country_code",
    "tax_number",
    "timezone",
    "status",
    "is_default",
    "created_at",
    "updated_at",
)
_BRANCH_COLUMNS = (
    "id",
    "tenant_id",
    "legal_entity_id",
    "code",
    "code_normalized",
    "name",
    "timezone",
    "country_code",
    "city",
    "address",
    "status",
    "archived_at",
    "created_at",
    "updated_at",
)
_LEGAL_ENTITY_UPDATE_COLUMNS = (
    "name",
    "registered_name",
    "country_code",
    "tax_number",
    "timezone",
    "status",
    "updated_at",
)
_BRANCH_UPDATE_COLUMNS = (
    "name",
    "timezone",
    "country_code",
    "city",
    "address",
    "status",
    "archived_at",
    "updated_at",
)


def upgrade() -> None:
    _create_legal_entities_table()
    _create_branches_table()
    _extend_authorization_catalog()

    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        _reset_postgresql_acl()
        # Existing tenant rows are FORCE-RLS, including for a non-BYPASS migration owner.
        # The deterministic owner-only backfill is enclosed by transactional flag restoration.
        disable_forced_row_security(op, table_name=_TENANTS_TABLE)
    _backfill_default_legal_entities()
    if is_postgresql:
        enable_forced_row_security(op, table_name=_TENANTS_TABLE)
        _configure_postgresql_security()


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        # FORCE RLS applies to the migration owner. Transactional DDL restores every flag if the
        # retention preflight refuses to discard organization state.
        disable_forced_row_security(op, table_name=_BRANCHES_TABLE)
        disable_forced_row_security(op, table_name=_LEGAL_ENTITIES_TABLE)
        disable_forced_row_security(op, table_name=_TENANTS_TABLE)

    _assert_downgrade_is_safe()

    if is_postgresql:
        enable_forced_row_security(op, table_name=_TENANTS_TABLE)
        _remove_postgresql_security()
    _contract_authorization_catalog()
    op.drop_table(_BRANCHES_TABLE)
    op.drop_table(_LEGAL_ENTITIES_TABLE)


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


def _create_legal_entities_table() -> None:
    op.create_table(
        _LEGAL_ENTITIES_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column(
            "code_normalized",
            sa.String(length=32),
            sa.Computed("lower(ltrim(rtrim(code)))", persisted=True),
            nullable=False,
        ),
        # Tenant names were historically unbounded text. Preserve every existing value during
        # the default-row backfill; authenticated create/update contracts remain bounded.
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("registered_name", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("tax_number", sa.String(length=64), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "status in ('active','inactive')",
            name="ck_legal_entities_status",
        ),
        sa.CheckConstraint(
            "length(code_normalized) > 0",
            name="ck_legal_entities_code_normalized_not_empty",
        ),
        sa.CheckConstraint(
            "is_default = false or status = 'active'",
            name="ck_legal_entities_default_active",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_legal_entities_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_legal_entities"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_legal_entities_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "code_normalized",
            name="uq_legal_entities_tenant_code_normalized",
        ),
        implicit_returning=False,
    )
    op.create_index(
        "uq_legal_entities_tenant_default",
        _LEGAL_ENTITIES_TABLE,
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
        sqlite_where=sa.text("is_default = 1"),
    )
    op.create_index(
        "ix_legal_entities_tenant_status_code",
        _LEGAL_ENTITIES_TABLE,
        ["tenant_id", "status", "code_normalized"],
        unique=False,
    )


def _create_branches_table() -> None:
    op.create_table(
        _BRANCHES_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legal_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column(
            "code_normalized",
            sa.String(length=32),
            sa.Computed("lower(ltrim(rtrim(code)))", persisted=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="active",
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "status in ('active','archived')",
            name="ck_branches_status",
        ),
        sa.CheckConstraint(
            "length(code_normalized) > 0",
            name="ck_branches_code_normalized_not_empty",
        ),
        sa.CheckConstraint(
            "(status = 'active' and archived_at is null) or "
            "(status = 'archived' and archived_at is not null)",
            name="ck_branches_archive_state",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "legal_entity_id"],
            ["legal_entities.tenant_id", "legal_entities.id"],
            name="fk_branches_tenant_legal_entity_id_legal_entities",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_branches"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_branches_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "code_normalized",
            name="uq_branches_tenant_code_normalized",
        ),
    )
    op.create_index(
        "ix_branches_tenant_status_code",
        _BRANCHES_TABLE,
        ["tenant_id", "status", "code_normalized"],
        unique=False,
    )
    op.create_index(
        "ix_branches_tenant_legal_entity_status",
        _BRANCHES_TABLE,
        ["tenant_id", "legal_entity_id", "status"],
        unique=False,
    )


def _extend_authorization_catalog() -> None:
    permissions = sa.table(
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
        permissions,
        [
            {
                "id": permission_id,
                "code": code,
                "resource": "organization",
                "action": code.split(":")[1],
                "target": "tenant",
                "target_type": "scope",
                "description": description,
            }
            for permission_id, code, description in _PERMISSION_ROWS
        ],
        multiinsert=False,
    )

    role_permissions = sa.table(
        _ROLE_PERMISSIONS_TABLE,
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
        sa.column("permission_id", postgresql.UUID(as_uuid=True)),
    )
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_id, "permission_id": permission_id}
            for role_id, permission_id in _ROLE_PERMISSION_ROWS
        ],
        multiinsert=False,
    )


def _contract_authorization_catalog() -> None:
    role_permissions = sa.table(
        _ROLE_PERMISSIONS_TABLE,
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
        sa.column("permission_id", postgresql.UUID(as_uuid=True)),
    )
    op.execute(
        sa.delete(role_permissions).where(
            sa.tuple_(role_permissions.c.role_id, role_permissions.c.permission_id).in_(
                _ROLE_PERMISSION_ROWS
            )
        )
    )
    permissions = sa.table(
        _PERMISSIONS_TABLE,
        sa.column("id", postgresql.UUID(as_uuid=True)),
    )
    op.execute(
        sa.delete(permissions).where(
            permissions.c.id.in_(
                (
                    _ORGANIZATION_READ_PERMISSION_ID,
                    _ORGANIZATION_UPDATE_PERMISSION_ID,
                )
            )
        )
    )


def _backfill_default_legal_entities() -> None:
    op.execute(
        sa.text(
            "insert into legal_entities ("
            "id, tenant_id, code, name, registered_name, country_code, tax_number, "
            "timezone, status, is_default, created_at, updated_at"
            ") select id, id, 'DEFAULT', name, name, null, null, timezone, "
            "'active', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP from tenants"
        )
    )


def _configure_postgresql_security() -> None:
    for table_name in (_LEGAL_ENTITIES_TABLE, _BRANCHES_TABLE):
        enable_forced_row_security(op, table_name=table_name)
        create_tenant_isolation_policy(
            op,
            table_name=table_name,
            policy_name=_TENANT_POLICY,
            role_name=TENANT_APPLICATION_ROLE,
        )

    op.execute(
        sa.text(
            f'CREATE POLICY "{_PLATFORM_LEGAL_ENTITY_INSERT_POLICY}" '
            f'ON "{_LEGAL_ENTITIES_TABLE}" AS PERMISSIVE FOR INSERT '
            f'TO "{PLATFORM_APPLICATION_ROLE}" WITH CHECK ('
            "id = tenant_id and code = 'DEFAULT' and name = registered_name and "
            "country_code is null and tax_number is null and status = 'active' and "
            "is_default = true)"
        )
    )

    for table_name in (_LEGAL_ENTITIES_TABLE, _BRANCHES_TABLE):
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=TENANT_APPLICATION_ROLE,
            privileges=("SELECT", "INSERT"),
        )
    grant_column_privilege(
        op,
        table_name=_LEGAL_ENTITIES_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_LEGAL_ENTITY_UPDATE_COLUMNS,
    )
    grant_column_privilege(
        op,
        table_name=_BRANCHES_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_BRANCH_UPDATE_COLUMNS,
    )
    grant_table_privileges(
        op,
        table_name=_LEGAL_ENTITIES_TABLE,
        role_name=PLATFORM_APPLICATION_ROLE,
        privileges=("INSERT",),
    )


def _remove_postgresql_security() -> None:
    revoke_table_privileges(
        op,
        table_name=_LEGAL_ENTITIES_TABLE,
        role_name=PLATFORM_APPLICATION_ROLE,
        privileges=("INSERT",),
    )
    revoke_column_privilege(
        op,
        table_name=_BRANCHES_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_BRANCH_UPDATE_COLUMNS,
    )
    revoke_column_privilege(
        op,
        table_name=_LEGAL_ENTITIES_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_LEGAL_ENTITY_UPDATE_COLUMNS,
    )
    for table_name in reversed((_LEGAL_ENTITIES_TABLE, _BRANCHES_TABLE)):
        revoke_table_privileges(
            op,
            table_name=table_name,
            role_name=TENANT_APPLICATION_ROLE,
            privileges=("SELECT", "INSERT"),
        )
    drop_policy(
        op,
        table_name=_LEGAL_ENTITIES_TABLE,
        policy_name=_PLATFORM_LEGAL_ENTITY_INSERT_POLICY,
    )
    for table_name in reversed((_LEGAL_ENTITIES_TABLE, _BRANCHES_TABLE)):
        drop_policy(
            op,
            table_name=table_name,
            policy_name=_TENANT_POLICY,
        )


def _reset_postgresql_acl() -> None:
    table_columns = {
        _LEGAL_ENTITIES_TABLE: _LEGAL_ENTITY_COLUMNS,
        _BRANCHES_TABLE: _BRANCH_COLUMNS,
    }
    for table_name, column_names in table_columns.items():
        quoted_columns = ", ".join(f'"{column_name}"' for column_name in column_names)
        op.execute(
            sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{table_name}" FROM PUBLIC')
        )
        op.execute(
            sa.text(
                f'REVOKE ALL PRIVILEGES ({quoted_columns}) ON TABLE "{table_name}" FROM PUBLIC'
            )
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


def _assert_downgrade_is_safe() -> None:
    custom_state_predicate = (
        "legal_entity.id <> legal_entity.tenant_id or "
        "legal_entity.code <> 'DEFAULT' or "
        "legal_entity.code_normalized <> 'default' or "
        "legal_entity.name <> tenant.name or "
        "legal_entity.registered_name <> tenant.name or "
        "legal_entity.country_code is not null or "
        "legal_entity.tax_number is not null or "
        "legal_entity.timezone <> tenant.timezone or "
        "legal_entity.status <> 'active' or "
        "legal_entity.is_default <> true"
    )
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $p3f_downgrade_preflight$
                BEGIN
                    IF EXISTS (SELECT 1 FROM branches)
                       OR EXISTS (
                           SELECT 1
                           FROM legal_entities AS legal_entity
                           JOIN tenants AS tenant ON tenant.id = legal_entity.tenant_id
                           WHERE {custom_state_predicate}
                       )
                       OR EXISTS (
                           SELECT 1
                           FROM tenants AS tenant
                           LEFT JOIN legal_entities AS legal_entity
                             ON legal_entity.tenant_id = tenant.id
                            AND legal_entity.is_default = true
                           WHERE legal_entity.id IS NULL
                       )
                       OR EXISTS (
                           SELECT 1
                           FROM legal_entities AS legal_entity
                           LEFT JOIN tenants AS tenant ON tenant.id = legal_entity.tenant_id
                           WHERE tenant.id IS NULL
                       ) THEN
                        RAISE EXCEPTION
                            'P3F downgrade preflight failed; archive export and restore only the '
                            'untouched default legal entity for every tenant before retrying';
                    END IF;
                END
                $p3f_downgrade_preflight$
                """
            )
        )
        return

    connection = op.get_bind()
    branch_count = int(
        connection.scalar(sa.text("select count(*) from branches")) or 0
    )
    custom_entity_count = int(
        connection.scalar(
            sa.text(
                "select count(*) from legal_entities as legal_entity "
                "join tenants as tenant on tenant.id = legal_entity.tenant_id "
                f"where {custom_state_predicate}"
            )
        )
        or 0
    )
    missing_default_count = int(
        connection.scalar(
            sa.text(
                "select count(*) from tenants as tenant "
                "left join legal_entities as legal_entity "
                "on legal_entity.tenant_id = tenant.id and legal_entity.is_default = true "
                "where legal_entity.id is null"
            )
        )
        or 0
    )
    orphan_entity_count = int(
        connection.scalar(
            sa.text(
                "select count(*) from legal_entities as legal_entity "
                "left join tenants as tenant on tenant.id = legal_entity.tenant_id "
                "where tenant.id is null"
            )
        )
        or 0
    )
    if not any(
        (
            branch_count,
            custom_entity_count,
            missing_default_count,
            orphan_entity_count,
        )
    ):
        return

    raise RuntimeError(
        "P3F downgrade preflight failed; preserve organization state before retrying: "
        f"branches={branch_count}, custom_legal_entities={custom_entity_count}, "
        f"missing_defaults={missing_default_count}, "
        f"orphan_legal_entities={orphan_entity_count}"
    )


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
