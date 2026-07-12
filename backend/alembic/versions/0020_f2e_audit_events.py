"""add F2E append-only tenant and platform audit events

Revision ID: 0020_f2e_audit_events
Revises: 0019_f2d_rbac
Create Date: 2026-07-12
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    disable_forced_row_security,
    drop_policy,
    enable_forced_row_security,
    grant_table_privileges,
    revoke_all_column_privileges,
    revoke_all_table_privileges,
)
from app.platform.db.tenant_access import (
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy.dialects import postgresql

revision: str = "0020_f2e_audit_events"
down_revision: str | None = "0019_f2d_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUDIT_EVENTS_TABLE = "audit_events"
_PERMISSIONS_TABLE = "permissions"
_ROLE_PERMISSIONS_TABLE = "role_permissions"
_TENANT_POLICY = "tenant_audit_isolation_app"
_PLATFORM_POLICY = "platform_audit_isolation_app"
_AUDIT_EVENT_COLUMNS = (
    "id",
    "occurred_at",
    "scope_type",
    "tenant_id",
    "actor_type",
    "actor_user_id",
    "impersonator_user_id",
    "event_type",
    "category",
    "severity",
    "resource_type",
    "resource_id",
    "action",
    "result",
    "request_id",
    "trace_id",
    "session_id",
    "ip_address",
    "user_agent",
    "reason",
    "support_ticket_id",
    "changed_fields",
    "before_data",
    "after_data",
    "metadata",
    "data_classification",
    "visibility_class",
    "integrity_hash",
)

_SUPER_ADMIN_ROLE_ID = UUID("d2000000-0000-4000-8000-000000000001")
_TENANT_ADMIN_ROLE_ID = UUID("d2000000-0000-4000-8000-000000000002")
_IT_ADMIN_ROLE_ID = UUID("d2000000-0000-4000-8000-000000000005")
_TENANT_AUDIT_PERMISSION_ID = UUID("d3000000-0000-4000-8000-000000000024")
_PLATFORM_AUDIT_PERMISSION_ID = UUID("d3000000-0000-4000-8000-000000000030")


def upgrade() -> None:
    _create_audit_events_table()
    _extend_authorization_catalog()
    if op.get_bind().dialect.name == "postgresql":
        _configure_postgresql_security()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _remove_postgresql_security()
    _contract_authorization_catalog()
    op.drop_table(_AUDIT_EVENTS_TABLE)


def _create_audit_events_table() -> None:
    audit_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        _AUDIT_EVENTS_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("impersonator_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=32), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("support_ticket_id", sa.String(length=64), nullable=True),
        sa.Column("changed_fields", audit_json, nullable=False),
        sa.Column("before_data", audit_json, nullable=False),
        sa.Column("after_data", audit_json, nullable=False),
        sa.Column("metadata", audit_json, nullable=False),
        sa.Column("data_classification", sa.String(length=64), nullable=False),
        sa.Column("visibility_class", sa.String(length=64), nullable=False),
        sa.Column("integrity_hash", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(scope_type = 'tenant' and tenant_id is not null) or "
            "(scope_type = 'platform' and tenant_id is null)",
            name="ck_audit_events_scope_tenant",
        ),
        sa.CheckConstraint(
            "scope_type in ('platform','tenant')",
            name="ck_audit_events_scope_type",
        ),
        sa.CheckConstraint(
            "(scope_type = 'platform' and category = 'platform_operations') or "
            "(scope_type = 'tenant' and category <> 'platform_operations')",
            name="ck_audit_events_scope_category",
        ),
        sa.CheckConstraint(
            "actor_type in ('user','system','worker','platform_admin','support_session')",
            name="ck_audit_events_actor_type",
        ),
        sa.CheckConstraint(
            "severity in ('info','warning','critical')",
            name="ck_audit_events_severity",
        ),
        sa.CheckConstraint(
            "result in ('success','failure','denied')",
            name="ck_audit_events_result",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_audit_events_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index(
        "ix_audit_events_tenant_occurred_at_id",
        _AUDIT_EVENTS_TABLE,
        ["tenant_id", "occurred_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_tenant_event_occurred_at",
        _AUDIT_EVENTS_TABLE,
        ["tenant_id", "event_type", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_tenant_resource_occurred_at",
        _AUDIT_EVENTS_TABLE,
        ["tenant_id", "resource_type", "resource_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_actor_occurred_at",
        _AUDIT_EVENTS_TABLE,
        ["actor_user_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_scope_occurred_at_id",
        _AUDIT_EVENTS_TABLE,
        ["scope_type", "occurred_at", "id"],
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
                "id": _PLATFORM_AUDIT_PERMISSION_ID,
                "code": "audit:read:platform",
                "resource": "audit",
                "action": "read",
                "target": "platform",
                "target_type": "scope",
                "description": "Read platform operations audit history.",
            }
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
            {
                "role_id": _SUPER_ADMIN_ROLE_ID,
                "permission_id": _PLATFORM_AUDIT_PERMISSION_ID,
            },
            {
                "role_id": _TENANT_ADMIN_ROLE_ID,
                "permission_id": _TENANT_AUDIT_PERMISSION_ID,
            },
            {
                "role_id": _IT_ADMIN_ROLE_ID,
                "permission_id": _TENANT_AUDIT_PERMISSION_ID,
            },
        ],
        multiinsert=False,
    )


def _contract_authorization_catalog() -> None:
    op.execute(
        sa.delete(
            sa.table(_ROLE_PERMISSIONS_TABLE, sa.column("role_id"), sa.column("permission_id"))
        ).where(
            sa.tuple_(
                sa.column("role_id"),
                sa.column("permission_id"),
            ).in_(
                (
                    (_SUPER_ADMIN_ROLE_ID, _PLATFORM_AUDIT_PERMISSION_ID),
                    (_TENANT_ADMIN_ROLE_ID, _TENANT_AUDIT_PERMISSION_ID),
                    (_IT_ADMIN_ROLE_ID, _TENANT_AUDIT_PERMISSION_ID),
                )
            )
        )
    )
    op.execute(
        sa.delete(sa.table(_PERMISSIONS_TABLE, sa.column("id"))).where(
            sa.column("id") == _PLATFORM_AUDIT_PERMISSION_ID
        )
    )


def _configure_postgresql_security() -> None:
    _reset_postgresql_acl()
    enable_forced_row_security(op, table_name=_AUDIT_EVENTS_TABLE)
    tenant_predicate = (
        "scope_type = 'tenant' and tenant_id = "
        "nullif(current_setting('app.tenant_id', true), '')::uuid"
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_TENANT_POLICY}" ON "{_AUDIT_EVENTS_TABLE}" '
            f'AS PERMISSIVE FOR ALL TO "{TENANT_APPLICATION_ROLE}" '
            f"USING ({tenant_predicate}) WITH CHECK ({tenant_predicate})"
        )
    )
    platform_predicate = "scope_type = 'platform' and tenant_id is null"
    op.execute(
        sa.text(
            f'CREATE POLICY "{_PLATFORM_POLICY}" ON "{_AUDIT_EVENTS_TABLE}" '
            f'AS PERMISSIVE FOR ALL TO "{PLATFORM_APPLICATION_ROLE}" '
            f"USING ({platform_predicate}) WITH CHECK ({platform_predicate})"
        )
    )
    for role_name in (TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE):
        grant_table_privileges(
            op,
            table_name=_AUDIT_EVENTS_TABLE,
            role_name=role_name,
            privileges=("SELECT", "INSERT"),
        )


def _remove_postgresql_security() -> None:
    _reset_postgresql_acl()
    drop_policy(
        op,
        table_name=_AUDIT_EVENTS_TABLE,
        policy_name=_PLATFORM_POLICY,
    )
    drop_policy(
        op,
        table_name=_AUDIT_EVENTS_TABLE,
        policy_name=_TENANT_POLICY,
    )
    disable_forced_row_security(op, table_name=_AUDIT_EVENTS_TABLE)


def _reset_postgresql_acl() -> None:
    quoted_columns = ", ".join(f'"{column_name}"' for column_name in _AUDIT_EVENT_COLUMNS)
    op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{_AUDIT_EVENTS_TABLE}" FROM PUBLIC'))
    op.execute(
        sa.text(
            f'REVOKE ALL PRIVILEGES ({quoted_columns}) ON TABLE "{_AUDIT_EVENTS_TABLE}" FROM PUBLIC'
        )
    )
    for role_name in (TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE):
        revoke_all_table_privileges(
            op,
            table_name=_AUDIT_EVENTS_TABLE,
            role_name=role_name,
        )
        revoke_all_column_privileges(
            op,
            table_name=_AUDIT_EVENTS_TABLE,
            role_name=role_name,
            column_names=_AUDIT_EVENT_COLUMNS,
        )


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
