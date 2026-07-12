"""add P3D tenantless platform authentication realm persistence

Revision ID: 0025_p3d_platform_authentication
Revises: 0024_p3c_organization_selection
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
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

revision: str = "0025_p3d_platform_authentication"
down_revision: str | None = "0024_p3c_organization_selection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IDENTITIES_TABLE = "identities"
_ROLES_TABLE = "roles"
_PERMISSIONS_TABLE = "permissions"
_ROLE_PERMISSIONS_TABLE = "role_permissions"
_AUDIT_EVENTS_TABLE = "audit_events"
_PLATFORM_ROLES_TABLE = "platform_identity_roles"
_PLATFORM_FAMILIES_TABLE = "platform_refresh_session_families"
_PLATFORM_TOKENS_TABLE = "platform_refresh_session_tokens"

_PLATFORM_ROLES_POLICY = "authentication_platform_identity_roles"
_PLATFORM_FAMILIES_POLICY = "authentication_platform_session_families"
_PLATFORM_TOKENS_POLICY = "authentication_platform_session_tokens"
_OLD_AUTH_AUDIT_POLICY = "authentication_failure_insert"
_P3D_AUTH_AUDIT_POLICY = "authentication_platform_security_insert"

_PLATFORM_ROLE_COLUMNS = (
    "identity_id",
    "role_id",
    "role_scope_type",
    "active",
    "created_at",
    "updated_at",
)
_PLATFORM_FAMILY_COLUMNS = (
    "id",
    "identity_id",
    "permission_version",
    "authentication_strength",
    "expires_at",
    "revoked_at",
    "created_at",
    "updated_at",
)
_PLATFORM_TOKEN_COLUMNS = (
    "id",
    "family_id",
    "token_hash",
    "consumed_at",
    "created_at",
    "updated_at",
)
_P3D_AUTH_IDENTITY_COLUMNS = (
    "email",
    "platform_permission_version",
    "created_at",
    "updated_at",
)


def upgrade() -> None:
    _add_platform_permission_version()
    _create_platform_identity_roles_table()
    _create_platform_session_families_table()
    _create_platform_session_tokens_table()
    if op.get_bind().dialect.name == "postgresql":
        _configure_postgresql_security()


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        for table_name in (
            _IDENTITIES_TABLE,
            _PLATFORM_ROLES_TABLE,
            _PLATFORM_FAMILIES_TABLE,
            _PLATFORM_TOKENS_TABLE,
        ):
            disable_forced_row_security(op, table_name=table_name)
    _assert_downgrade_is_safe()
    if is_postgresql:
        _remove_postgresql_security()
    op.drop_table(_PLATFORM_TOKENS_TABLE)
    op.drop_table(_PLATFORM_FAMILIES_TABLE)
    op.drop_table(_PLATFORM_ROLES_TABLE)
    _drop_platform_permission_version()
    if is_postgresql:
        enable_forced_row_security(op, table_name=_IDENTITIES_TABLE)


def _add_platform_permission_version() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.add_column(
            _IDENTITIES_TABLE,
            sa.Column(
                "platform_permission_version",
                sa.Integer(),
                sa.CheckConstraint(
                    "platform_permission_version >= 1",
                    name="ck_identities_platform_permission_version_positive",
                ),
                server_default=sa.text("1"),
                nullable=False,
            ),
        )
        return
    op.add_column(
        _IDENTITIES_TABLE,
        sa.Column(
            "platform_permission_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_identities_platform_permission_version_positive",
        _IDENTITIES_TABLE,
        "platform_permission_version >= 1",
    )


def _drop_platform_permission_version() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.drop_column(_IDENTITIES_TABLE, "platform_permission_version")
        return
    op.drop_constraint(
        "ck_identities_platform_permission_version_positive",
        _IDENTITIES_TABLE,
        type_="check",
    )
    op.drop_column(_IDENTITIES_TABLE, "platform_permission_version")


def _timestamps() -> tuple[sa.Column, sa.Column]:
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


def _create_platform_identity_roles_table() -> None:
    op.create_table(
        _PLATFORM_ROLES_TABLE,
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role_scope_type",
            sa.String(length=16),
            server_default="platform",
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "role_scope_type = 'platform'",
            name="ck_platform_identity_roles_platform_scope",
        ),
        sa.CheckConstraint(
            "active in (false, true)",
            name="ck_platform_identity_roles_active",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["identities.id"],
            name="fk_platform_identity_roles_identity_id_identities",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id", "role_scope_type"],
            ["roles.id", "roles.scope_type"],
            name="fk_platform_identity_roles_role_id_scope_roles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "identity_id",
            "role_id",
            name="pk_platform_identity_roles",
        ),
    )
    op.create_index(
        "ix_platform_identity_roles_identity_active",
        _PLATFORM_ROLES_TABLE,
        ["identity_id", "active"],
    )


def _create_platform_session_families_table() -> None:
    op.create_table(
        _PLATFORM_FAMILIES_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "permission_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "authentication_strength",
            sa.String(length=32),
            server_default="single_factor",
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "permission_version >= 1",
            name="ck_platform_session_families_permission_version_positive",
        ),
        sa.CheckConstraint(
            "authentication_strength in ('single_factor','multi_factor','step_up')",
            name="ck_platform_refresh_session_families_authentication_strength",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_platform_refresh_session_families_expiry_order",
        ),
        sa.CheckConstraint(
            "revoked_at is null or revoked_at >= created_at",
            name="ck_platform_refresh_session_families_revoked_order",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["identities.id"],
            name="fk_platform_refresh_session_families_identity_id_identities",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_platform_refresh_session_families"),
    )
    op.create_index(
        "ix_platform_refresh_session_families_identity_expires_at",
        _PLATFORM_FAMILIES_TABLE,
        ["identity_id", "expires_at"],
    )
    op.create_index(
        "ix_platform_refresh_session_families_expires_at",
        _PLATFORM_FAMILIES_TABLE,
        ["expires_at"],
    )


def _create_platform_session_tokens_table() -> None:
    op.create_table(
        _PLATFORM_TOKENS_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "length(token_hash) = 64",
            name="ck_platform_refresh_session_tokens_hash_length",
        ),
        sa.CheckConstraint(
            "consumed_at is null or consumed_at >= created_at",
            name="ck_platform_refresh_session_tokens_consumed_order",
        ),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["platform_refresh_session_families.id"],
            name="fk_platform_refresh_session_tokens_family_id_families",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_platform_refresh_session_tokens"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_platform_refresh_session_tokens_token_hash",
        ),
    )
    op.create_index(
        "ix_platform_refresh_session_tokens_family_created_at",
        _PLATFORM_TOKENS_TABLE,
        ["family_id", "created_at"],
    )


def _configure_postgresql_security() -> None:
    for table_name, columns in (
        (_PLATFORM_ROLES_TABLE, _PLATFORM_ROLE_COLUMNS),
        (_PLATFORM_FAMILIES_TABLE, _PLATFORM_FAMILY_COLUMNS),
        (_PLATFORM_TOKENS_TABLE, _PLATFORM_TOKEN_COLUMNS),
    ):
        _reset_new_table_acl(table_name, columns)
        enable_forced_row_security(op, table_name=table_name)

    _create_authentication_policy(
        table_name=_PLATFORM_ROLES_TABLE,
        policy_name=_PLATFORM_ROLES_POLICY,
        command="SELECT",
    )
    _create_authentication_policy(
        table_name=_PLATFORM_FAMILIES_TABLE,
        policy_name=_PLATFORM_FAMILIES_POLICY,
        command="ALL",
    )
    _create_authentication_policy(
        table_name=_PLATFORM_TOKENS_TABLE,
        policy_name=_PLATFORM_TOKENS_POLICY,
        command="ALL",
    )

    grant_table_privileges(
        op,
        table_name=_PLATFORM_ROLES_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privileges=("SELECT",),
    )
    for table_name in (_PLATFORM_FAMILIES_TABLE, _PLATFORM_TOKENS_TABLE):
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=AUTHENTICATION_APPLICATION_ROLE,
            privileges=("SELECT", "INSERT", "UPDATE"),
        )

    grant_column_privilege(
        op,
        table_name=_IDENTITIES_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privilege="SELECT",
        column_names=_P3D_AUTH_IDENTITY_COLUMNS,
    )
    for table_name in (_ROLES_TABLE, _PERMISSIONS_TABLE, _ROLE_PERMISSIONS_TABLE):
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=AUTHENTICATION_APPLICATION_ROLE,
            privileges=("SELECT",),
        )

    drop_policy(
        op,
        table_name=_AUDIT_EVENTS_TABLE,
        policy_name=_OLD_AUTH_AUDIT_POLICY,
    )
    _create_authentication_audit_policy(
        policy_name=_P3D_AUTH_AUDIT_POLICY,
        predicate=f"({_legacy_login_failure_predicate()}) OR ({_platform_audit_predicate()})",
    )


def _remove_postgresql_security() -> None:
    drop_policy(
        op,
        table_name=_AUDIT_EVENTS_TABLE,
        policy_name=_P3D_AUTH_AUDIT_POLICY,
    )
    _create_authentication_audit_policy(
        policy_name=_OLD_AUTH_AUDIT_POLICY,
        predicate=_legacy_login_failure_predicate(),
    )

    for table_name in (_ROLE_PERMISSIONS_TABLE, _PERMISSIONS_TABLE, _ROLES_TABLE):
        revoke_table_privileges(
            op,
            table_name=table_name,
            role_name=AUTHENTICATION_APPLICATION_ROLE,
            privileges=("SELECT",),
        )
    revoke_column_privilege(
        op,
        table_name=_IDENTITIES_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privilege="SELECT",
        column_names=_P3D_AUTH_IDENTITY_COLUMNS,
    )
    for table_name in (_PLATFORM_TOKENS_TABLE, _PLATFORM_FAMILIES_TABLE):
        revoke_table_privileges(
            op,
            table_name=table_name,
            role_name=AUTHENTICATION_APPLICATION_ROLE,
            privileges=("SELECT", "INSERT", "UPDATE"),
        )
    revoke_table_privileges(
        op,
        table_name=_PLATFORM_ROLES_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privileges=("SELECT",),
    )
    for table_name, policy_name in (
        (_PLATFORM_TOKENS_TABLE, _PLATFORM_TOKENS_POLICY),
        (_PLATFORM_FAMILIES_TABLE, _PLATFORM_FAMILIES_POLICY),
        (_PLATFORM_ROLES_TABLE, _PLATFORM_ROLES_POLICY),
    ):
        drop_policy(op, table_name=table_name, policy_name=policy_name)


def _reset_new_table_acl(table_name: str, columns: tuple[str, ...]) -> None:
    quoted_columns = ", ".join(f'"{column_name}"' for column_name in columns)
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
            column_names=columns,
        )


def _create_authentication_policy(
    *,
    table_name: str,
    policy_name: str,
    command: str,
) -> None:
    check = " WITH CHECK (true)" if command == "ALL" else ""
    op.execute(
        sa.text(
            f'CREATE POLICY "{policy_name}" ON "{table_name}" '
            f'AS PERMISSIVE FOR {command} TO "{AUTHENTICATION_APPLICATION_ROLE}" '
            f"USING (true){check}"
        )
    )


def _create_authentication_audit_policy(*, policy_name: str, predicate: str) -> None:
    op.execute(
        sa.text(
            f'CREATE POLICY "{policy_name}" ON "{_AUDIT_EVENTS_TABLE}" '
            f'AS PERMISSIVE FOR INSERT TO "{AUTHENTICATION_APPLICATION_ROLE}" '
            f"WITH CHECK ({predicate})"
        )
    )


def _legacy_login_failure_predicate() -> str:
    return (
        "scope_type = 'platform' and tenant_id is null "
        "and actor_type = 'system' and actor_user_id is null "
        "and impersonator_user_id is null "
        "and event_type = 'auth.login.failed' "
        "and category = 'platform_operations' and severity = 'info' "
        "and resource_type = 'authentication' and resource_id is null "
        "and action = 'login' and result = 'failure' and session_id is null "
        "and ip_address is null and user_agent is null "
        "and reason is null and support_ticket_id is null "
        "and changed_fields = '[]'::jsonb "
        "and before_data = '{}'::jsonb and after_data = '{}'::jsonb "
        'and metadata = \'{"failure_reason":"authentication_failed"}\'::jsonb '
        "and data_classification = 'platform_metadata' "
        "and visibility_class = 'platform_ops' and integrity_hash is null "
        f"and {_correlation_predicate()}"
    )


def _platform_audit_predicate() -> str:
    common = (
        "scope_type = 'platform' and tenant_id is null "
        "and impersonator_user_id is null "
        "and category = 'platform_operations' "
        "and ip_address is null and user_agent is null "
        "and reason is null and support_ticket_id is null "
        "and changed_fields = '[]'::jsonb "
        "and before_data = '{}'::jsonb and after_data = '{}'::jsonb "
        "and data_classification = 'security_metadata' "
        "and visibility_class = 'platform_ops' and integrity_hash is null "
        f"and {_correlation_predicate()}"
    )
    failed = (
        "event_type = 'platform.auth.login.failed' and actor_type = 'system' "
        "and actor_user_id is null and severity = 'info' "
        "and resource_type = 'authentication' and resource_id is null "
        "and action = 'login' and result = 'failure' and session_id is null "
        "and metadata = '{}'::jsonb"
    )
    denied = (
        "event_type = 'platform.auth.login.denied' and actor_type = 'system' "
        "and actor_user_id is null and severity = 'info' "
        "and resource_type = 'authentication' and resource_id is null "
        "and action = 'login' and result = 'denied' and session_id is null "
        "and metadata = '{}'::jsonb"
    )
    succeeded = (
        "event_type = 'platform.auth.login.succeeded' "
        "and actor_type = 'platform_admin' and actor_user_id is not null "
        "and severity = 'info' and resource_type = 'identity' "
        "and resource_id = actor_user_id and action = 'login' "
        "and result = 'success' and session_id is not null "
        "and metadata = '{}'::jsonb"
    )
    started = _platform_session_event_predicate(
        event_type="platform.session.started",
        action="start",
        result="success",
        severity="info",
        metadata="{}",
    )
    refreshed = _platform_session_event_predicate(
        event_type="platform.session.refreshed",
        action="refresh",
        result="success",
        severity="info",
        metadata="{}",
    )
    reuse = _platform_session_event_predicate(
        event_type="platform.session.reuse_detected",
        action="detect_reuse",
        result="denied",
        severity="warning",
        metadata="{}",
    )
    revoked_base = (
        "event_type = 'platform.session.revoked' "
        "and actor_type = 'platform_admin' and actor_user_id is not null "
        "and severity = 'info' and resource_type = 'session' "
        "and resource_id = session_id and session_id is not null "
        "and action = 'revoke' and result = 'success' "
    )
    revoked_metadata = (
        "metadata in ("
        "'{}'::jsonb, "
        '\'{"revocation_reason":"logout"}\'::jsonb, '
        '\'{"revocation_reason":"logout","source":"access_session"}\'::jsonb, '
        '\'{"revocation_reason":"logout","source":"refresh_cookie"}\'::jsonb'
        ")"
    )
    event_shapes = " OR ".join(
        f"({predicate})"
        for predicate in (
            failed,
            denied,
            succeeded,
            started,
            refreshed,
            reuse,
            f"{revoked_base} and {revoked_metadata}",
        )
    )
    return f"{common} and ({event_shapes})"


def _platform_session_event_predicate(
    *,
    event_type: str,
    action: str,
    result: str,
    severity: str,
    metadata: str,
) -> str:
    return (
        f"event_type = '{event_type}' "
        "and actor_type = 'platform_admin' and actor_user_id is not null "
        f"and severity = '{severity}' and resource_type = 'session' "
        "and resource_id = session_id and session_id is not null "
        f"and action = '{action}' and result = '{result}' "
        f"and metadata = '{metadata}'::jsonb"
    )


def _correlation_predicate() -> str:
    return (
        "request_id ~ "
        "'^[A-Za-z0-9]$|^[A-Za-z0-9][A-Za-z0-9._-]{0,126}[A-Za-z0-9]$' "
        "and trace_id ~ '^[0-9a-f]{32}$' "
        "and trace_id <> '00000000000000000000000000000000'"
    )


def _assert_downgrade_is_safe() -> None:
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                """
                DO $p3d_platform_authentication_downgrade_preflight$
                DECLARE
                    platform_role_count bigint;
                    platform_session_count bigint;
                    changed_permission_version_count bigint;
                BEGIN
                    SELECT count(*) INTO platform_role_count
                    FROM platform_identity_roles;
                    SELECT count(*) INTO platform_session_count
                    FROM platform_refresh_session_families;
                    SELECT count(*) INTO changed_permission_version_count
                    FROM identities
                    WHERE platform_permission_version <> 1;
                    IF platform_role_count > 0
                       OR platform_session_count > 0
                       OR changed_permission_version_count > 0 THEN
                        RAISE EXCEPTION
                            'P3D downgrade preflight failed: roles=%, sessions=%, versions=%',
                            platform_role_count,
                            platform_session_count,
                            changed_permission_version_count;
                    END IF;
                END
                $p3d_platform_authentication_downgrade_preflight$
                """
            )
        )
        return
    role_count = int(
        op.get_bind().execute(sa.text(f"select count(*) from {_PLATFORM_ROLES_TABLE}")).scalar_one()
    )
    family_count = int(
        op.get_bind()
        .execute(sa.text(f"select count(*) from {_PLATFORM_FAMILIES_TABLE}"))
        .scalar_one()
    )
    changed_version_count = int(
        op.get_bind()
        .execute(sa.text("select count(*) from identities where platform_permission_version <> 1"))
        .scalar_one()
    )
    if role_count or family_count or changed_version_count:
        raise RuntimeError(
            "P3D downgrade preflight failed: "
            f"platform_roles={role_count}, platform_sessions={family_count}, "
            f"changed_permission_versions={changed_version_count}"
        )


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
