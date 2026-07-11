"""add F2B refresh-session families and rotated token history

Revision ID: 0017_f2b_secure_sessions
Revises: 0016_f2a_identity_activation
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    create_tenant_isolation_policy,
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

revision: str = "0017_f2b_secure_sessions"
down_revision: str | None = "0016_f2a_identity_activation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FAMILY_TABLE = "refresh_session_families"
_TOKEN_TABLE = "refresh_session_tokens"
_TENANT_POLICY = "tenant_isolation_app"
_FAMILY_COLUMNS = (
    "id",
    "tenant_id",
    "user_id",
    "expires_at",
    "revoked_at",
    "created_at",
    "updated_at",
)
_TOKEN_COLUMNS = (
    "id",
    "tenant_id",
    "family_id",
    "token_hash",
    "consumed_at",
    "created_at",
    "updated_at",
)


def upgrade() -> None:
    _create_family_table()
    _create_token_table()
    if op.get_bind().dialect.name == "postgresql":
        _configure_postgresql_security()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table_name, column_names in (
            (_TOKEN_TABLE, _TOKEN_COLUMNS),
            (_FAMILY_TABLE, _FAMILY_COLUMNS),
        ):
            _reset_postgresql_acl(table_name, column_names)
            drop_policy(
                op,
                table_name=table_name,
                policy_name=_TENANT_POLICY,
            )
    op.drop_table(_TOKEN_TABLE)
    op.drop_table(_FAMILY_TABLE)


def _create_family_table() -> None:
    op.create_table(
        _FAMILY_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            "expires_at > created_at",
            name="ck_refresh_session_families_expiry_order",
        ),
        sa.CheckConstraint(
            "revoked_at is null or revoked_at >= created_at",
            name="ck_refresh_session_families_revoked_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_refresh_session_families_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_refresh_session_families_tenant_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_session_families"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_refresh_session_families_tenant_id_id",
        ),
    )
    op.create_index(
        "ix_refresh_session_families_tenant_user_expires_at",
        _FAMILY_TABLE,
        ["tenant_id", "user_id", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_refresh_session_families_expires_at",
        _FAMILY_TABLE,
        ["expires_at"],
        unique=False,
    )


def _create_token_table() -> None:
    op.create_table(
        _TOKEN_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
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
            "length(token_hash) = 64",
            name="ck_refresh_session_tokens_hash_length",
        ),
        sa.CheckConstraint(
            "consumed_at is null or consumed_at >= created_at",
            name="ck_refresh_session_tokens_consumed_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_refresh_session_tokens_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "family_id"],
            ["refresh_session_families.tenant_id", "refresh_session_families.id"],
            name="fk_refresh_session_tokens_tenant_family_id_families",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_session_tokens"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_refresh_session_tokens_token_hash",
        ),
    )
    op.create_index(
        "ix_refresh_session_tokens_tenant_family_created_at",
        _TOKEN_TABLE,
        ["tenant_id", "family_id", "created_at"],
        unique=False,
    )


def _configure_postgresql_security() -> None:
    for table_name, column_names in (
        (_FAMILY_TABLE, _FAMILY_COLUMNS),
        (_TOKEN_TABLE, _TOKEN_COLUMNS),
    ):
        _reset_postgresql_acl(table_name, column_names)
        enable_forced_row_security(op, table_name=table_name)
        create_tenant_isolation_policy(
            op,
            table_name=table_name,
            policy_name=_TENANT_POLICY,
            role_name=TENANT_APPLICATION_ROLE,
        )
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=TENANT_APPLICATION_ROLE,
            privileges=("SELECT", "INSERT", "UPDATE"),
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
