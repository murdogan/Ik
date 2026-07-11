"""add F2A user identity and activation-token persistence

Revision ID: 0016_f2a_identity_activation
Revises: 0015_f1d_feature_flags
Create Date: 2026-07-12
"""

from collections.abc import Sequence

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

revision: str = "0016_f2a_identity_activation"
down_revision: str | None = "0015_f1d_feature_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USERS_TABLE = "users"
_ACTIVATION_TABLE = "user_activation_tokens"
_TENANT_POLICY = "tenant_isolation_app"

_USER_COLUMNS = (
    "id",
    "tenant_id",
    "email",
    "email_normalized",
    "full_name",
    "status",
    "password_hash",
    "can_invite_users",
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
    "updated_at",
)
_ACTIVATION_COLUMNS = (
    "id",
    "tenant_id",
    "user_id",
    "token_hash",
    "expires_at",
    "consumed_at",
    "revoked_at",
    "created_at",
    "updated_at",
)


def upgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        # FORCE RLS also applies to the table owner. The migration must examine every existing
        # identity before installing the normalized unique key, then restore the flags in the
        # same transactional revision. A failed preflight rolls the flag change back as well.
        disable_forced_row_security(op, table_name=_USERS_TABLE)

    _assert_normalized_emails_are_safe()
    _add_user_identity_columns()

    if is_postgresql:
        enable_forced_row_security(op, table_name=_USERS_TABLE)

    _create_activation_table()

    if is_postgresql:
        _configure_postgresql_security()


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        _restore_postgresql_user_security()
        drop_policy(
            op,
            table_name=_ACTIVATION_TABLE,
            policy_name=_TENANT_POLICY,
        )

    op.drop_table(_ACTIVATION_TABLE)
    _drop_user_identity_columns()


def _assert_normalized_emails_are_safe() -> None:
    normalized = "lower(ltrim(rtrim(email)))"
    collision_count_sql = (
        "select count(*) from ("
        "select tenant_id, "
        f"{normalized} as normalized_email "
        "from users group by tenant_id, normalized_email having count(*) > 1"
        ") as normalized_email_collisions"
    )
    blank_count_sql = f"select count(*) from users where length({normalized}) = 0"

    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $f2a_email_normalization_preflight$
                DECLARE
                    collision_count bigint;
                    blank_count bigint;
                BEGIN
                    collision_count := ({collision_count_sql});
                    blank_count := ({blank_count_sql});
                    IF collision_count > 0 OR blank_count > 0 THEN
                        RAISE EXCEPTION
                            'F2A identity preflight failed: normalized_email_collisions=%, '
                            'blank_normalized_emails=%', collision_count, blank_count;
                    END IF;
                END
                $f2a_email_normalization_preflight$
                """
            )
        )
        return

    connection = op.get_bind()
    collision_count = int(connection.execute(sa.text(collision_count_sql)).scalar_one())
    blank_count = int(connection.execute(sa.text(blank_count_sql)).scalar_one())
    if collision_count or blank_count:
        raise RuntimeError(
            "F2A identity preflight failed: "
            f"normalized_email_collisions={collision_count}, "
            f"blank_normalized_emails={blank_count}"
        )


def _add_user_identity_columns() -> None:
    email_normalized = sa.Column(
        "email_normalized",
        sa.String(length=320),
        sa.Computed("lower(ltrim(rtrim(email)))", persisted=True),
        nullable=False,
    )
    can_invite_users = sa.Column(
        "can_invite_users",
        sa.Boolean(),
        server_default=sa.false(),
        nullable=False,
    )

    if op.get_bind().dialect.name == "sqlite":
        # SQLite cannot add a STORED generated column in place. Batch recreation also preserves
        # the published raw-email unique key while adding its normalized companion.
        with op.batch_alter_table(_USERS_TABLE, recreate="always") as batch_op:
            batch_op.add_column(email_normalized)
            batch_op.add_column(can_invite_users)
            batch_op.create_unique_constraint(
                "uq_users_tenant_email_normalized",
                ["tenant_id", "email_normalized"],
            )
            batch_op.create_check_constraint(
                "ck_users_email_normalized_not_empty",
                "length(email_normalized) > 0",
            )
        return

    op.add_column(_USERS_TABLE, email_normalized)
    op.add_column(_USERS_TABLE, can_invite_users)
    op.create_unique_constraint(
        "uq_users_tenant_email_normalized",
        _USERS_TABLE,
        ["tenant_id", "email_normalized"],
    )
    op.create_check_constraint(
        "ck_users_email_normalized_not_empty",
        _USERS_TABLE,
        "length(email_normalized) > 0",
    )


def _drop_user_identity_columns() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(_USERS_TABLE, recreate="always") as batch_op:
            batch_op.drop_constraint(
                "ck_users_email_normalized_not_empty",
                type_="check",
            )
            batch_op.drop_constraint(
                "uq_users_tenant_email_normalized",
                type_="unique",
            )
            batch_op.drop_column("can_invite_users")
            batch_op.drop_column("email_normalized")
        return

    op.drop_constraint(
        "ck_users_email_normalized_not_empty",
        _USERS_TABLE,
        type_="check",
    )
    op.drop_constraint(
        "uq_users_tenant_email_normalized",
        _USERS_TABLE,
        type_="unique",
    )
    op.drop_column(_USERS_TABLE, "can_invite_users")
    op.drop_column(_USERS_TABLE, "email_normalized")


def _create_activation_table() -> None:
    op.create_table(
        _ACTIVATION_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
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
            "length(token_hash) = 64",
            name="ck_user_activation_tokens_hash_length",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_user_activation_tokens_expiry_order",
        ),
        sa.CheckConstraint(
            "consumed_at is null or consumed_at >= created_at",
            name="ck_user_activation_tokens_consumed_order",
        ),
        sa.CheckConstraint(
            "revoked_at is null or revoked_at >= created_at",
            name="ck_user_activation_tokens_revoked_order",
        ),
        sa.CheckConstraint(
            "consumed_at is null or revoked_at is null",
            name="ck_user_activation_tokens_terminal_state",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_user_activation_tokens_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_user_activation_tokens_tenant_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_activation_tokens"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_user_activation_tokens_token_hash",
        ),
    )
    op.create_index(
        "ix_user_activation_tokens_tenant_user_expires_at",
        _ACTIVATION_TABLE,
        ["tenant_id", "user_id", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_activation_tokens_expires_at",
        _ACTIVATION_TABLE,
        ["expires_at"],
        unique=False,
    )


def _configure_postgresql_security() -> None:
    _reset_postgresql_acl(_USERS_TABLE, _USER_COLUMNS)
    _reset_postgresql_acl(_ACTIVATION_TABLE, _ACTIVATION_COLUMNS)

    enable_forced_row_security(op, table_name=_ACTIVATION_TABLE)
    create_tenant_isolation_policy(
        op,
        table_name=_ACTIVATION_TABLE,
        policy_name=_TENANT_POLICY,
        role_name=TENANT_APPLICATION_ROLE,
    )

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
    grant_table_privileges(
        op,
        table_name=_ACTIVATION_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT", "UPDATE"),
    )


def _restore_postgresql_user_security() -> None:
    _reset_postgresql_acl(_USERS_TABLE, _USER_COLUMNS)
    _reset_postgresql_acl(_ACTIVATION_TABLE, _ACTIVATION_COLUMNS)
    grant_table_privileges(
        op,
        table_name=_USERS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT",),
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
