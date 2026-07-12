"""add email-first authentication capability and organization selection transactions

Revision ID: 0023_p3b_email_first_login
Revises: 0022_p3a_identity_memberships
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    assert_capability_role_has_no_parent_memberships,
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
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy.dialects import postgresql

revision: str = "0023_p3b_email_first_login"
down_revision: str | None = "0022_p3a_identity_memberships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA_NAME = "public"
_IDENTITIES_TABLE = "identities"
_MEMBERSHIPS_TABLE = "tenant_memberships"
_MEMBERSHIP_ROLES_TABLE = "membership_roles"
_TENANTS_TABLE = "tenants"
_USERS_TABLE = "users"
_AUDIT_EVENTS_TABLE = "audit_events"
_TRANSACTIONS_TABLE = "organization_selection_transactions"
_CHOICES_TABLE = "organization_selection_choices"
_RATE_LIMITS_TABLE = "authentication_rate_limit_buckets"
_SYNC_FUNCTION = "sync_current_tenant_identity_membership"
_PROJECTION_ROLE = "wealthy_falcon_identity_projection"

_AUTH_IDENTITY_POLICY = "authentication_identity_read"
_AUTH_MEMBERSHIP_POLICY = "authentication_membership_read"
_AUTH_TENANT_POLICY = "authentication_tenant_read"
_AUTH_USER_POLICY = "authentication_legacy_user_read"
_AUTH_AUDIT_POLICY = "authentication_failure_insert"
_AUTH_TRANSACTION_POLICY = "authentication_selection_transaction_insert"
_AUTH_CHOICE_POLICY = "authentication_selection_choice_insert"
_AUTH_RATE_LIMIT_POLICY = "authentication_rate_limit_access"
_PROJECTION_IDENTITY_POLICY = "identity_projection_global_access"
_PROJECTION_MEMBERSHIP_POLICY = "identity_projection_membership_access"
_PROJECTION_MEMBERSHIP_ROLE_POLICY = "identity_projection_role_access"
_PROJECTION_USER_POLICY = "identity_projection_user_read"
_PROJECTION_USER_ROLE_POLICY = "identity_projection_user_role_read"

_IDENTITY_COLUMNS = (
    "id",
    "email",
    "email_normalized",
    "status",
    "password_hash",
    "created_at",
    "updated_at",
)
_MEMBERSHIP_COLUMNS = (
    "id",
    "tenant_id",
    "identity_id",
    "legacy_user_id",
    "full_name",
    "status",
    "permission_version",
    "created_at",
    "updated_at",
)
_MEMBERSHIP_ROLE_COLUMNS = (
    "tenant_id",
    "membership_id",
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
_USER_ROLE_COLUMNS = (
    "tenant_id",
    "user_id",
    "role_id",
    "role_scope_type",
    "active",
    "created_at",
    "updated_at",
)
_TRANSACTION_COLUMNS = (
    "id",
    "identity_id",
    "token_hash",
    "expires_at",
    "consumed_at",
    "created_at",
    "updated_at",
)
_CHOICE_COLUMNS = ("selection_key", "transaction_id", "tenant_id")
_RATE_LIMIT_COLUMNS = (
    "bucket_key_hash",
    "scope",
    "window_started_at",
    "expires_at",
    "attempt_count",
    "updated_at",
)
_AUTHENTICATION_IDENTITY_COLUMNS = (
    "id",
    "email_normalized",
    "status",
    "password_hash",
)
_AUTHENTICATION_MEMBERSHIP_COLUMNS = (
    "id",
    "tenant_id",
    "identity_id",
    "legacy_user_id",
    "status",
)


def upgrade() -> None:
    _create_selection_transaction_table()
    _create_selection_choice_table()
    _create_rate_limit_table()
    if op.get_bind().dialect.name == "postgresql":
        _configure_postgresql_security()
        _create_projection_sync_function()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _drop_projection_sync_function()
        _remove_postgresql_security()
    op.drop_table(_RATE_LIMITS_TABLE)
    op.drop_table(_CHOICES_TABLE)
    op.drop_table(_TRANSACTIONS_TABLE)


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


def _create_selection_transaction_table() -> None:
    op.create_table(
        _TRANSACTIONS_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "length(token_hash) = 64",
            name="ck_organization_selection_transactions_hash_length",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_organization_selection_transactions_expiry_order",
        ),
        sa.CheckConstraint(
            "consumed_at is null or consumed_at >= created_at",
            name="ck_organization_selection_transactions_consumed_order",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["identities.id"],
            name="fk_organization_selection_transactions_identity_id_identities",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_selection_transactions"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_organization_selection_transactions_token_hash",
        ),
    )
    op.create_index(
        "ix_organization_selection_transactions_identity_expires_at",
        _TRANSACTIONS_TABLE,
        ["identity_id", "expires_at"],
    )
    op.create_index(
        "ix_organization_selection_transactions_expires_at",
        _TRANSACTIONS_TABLE,
        ["expires_at"],
    )


def _create_selection_choice_table() -> None:
    op.create_table(
        _CHOICES_TABLE,
        sa.Column("selection_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            [f"{_TRANSACTIONS_TABLE}.id"],
            name="fk_organization_selection_choices_transaction_id_transactions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_organization_selection_choices_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("selection_key", name="pk_organization_selection_choices"),
        sa.UniqueConstraint(
            "transaction_id",
            "tenant_id",
            name="uq_organization_selection_choices_transaction_tenant",
        ),
    )


def _create_rate_limit_table() -> None:
    op.create_table(
        _RATE_LIMITS_TABLE,
        sa.Column("bucket_key_hash", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(bucket_key_hash) = 64",
            name="ck_authentication_rate_limit_buckets_hash_length",
        ),
        sa.CheckConstraint(
            "scope in ('login_source','login_identity')",
            name="ck_authentication_rate_limit_buckets_scope",
        ),
        sa.CheckConstraint(
            "attempt_count >= 1",
            name="ck_authentication_rate_limit_buckets_attempt_count_positive",
        ),
        sa.CheckConstraint(
            "expires_at > window_started_at",
            name="ck_authentication_rate_limit_buckets_expiry_order",
        ),
        sa.PrimaryKeyConstraint(
            "bucket_key_hash",
            name="pk_authentication_rate_limit_buckets",
        ),
    )
    op.create_index(
        "ix_authentication_rate_limit_buckets_expires_at",
        _RATE_LIMITS_TABLE,
        ["expires_at"],
    )


def _configure_postgresql_security() -> None:
    ensure_capability_role(op, AUTHENTICATION_APPLICATION_ROLE)
    assert_capability_role_has_no_parent_memberships(
        op, AUTHENTICATION_APPLICATION_ROLE
    )
    revoke_all_schema_privileges(
        op,
        schema_name=_SCHEMA_NAME,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
    )
    _revoke_stale_authentication_object_privileges()
    grant_schema_usage(
        op,
        schema_name=_SCHEMA_NAME,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
    )
    ensure_capability_role(op, _PROJECTION_ROLE)
    assert_capability_role_has_no_parent_memberships(op, _PROJECTION_ROLE)
    revoke_all_schema_privileges(
        op,
        schema_name=_SCHEMA_NAME,
        role_name=_PROJECTION_ROLE,
    )
    grant_schema_usage(op, schema_name=_SCHEMA_NAME, role_name=_PROJECTION_ROLE)

    for table_name, columns in (
        (_IDENTITIES_TABLE, _IDENTITY_COLUMNS),
        (_MEMBERSHIPS_TABLE, _MEMBERSHIP_COLUMNS),
        (_TRANSACTIONS_TABLE, _TRANSACTION_COLUMNS),
        (_CHOICES_TABLE, _CHOICE_COLUMNS),
        (_RATE_LIMITS_TABLE, _RATE_LIMIT_COLUMNS),
    ):
        revoke_all_table_privileges(
            op,
            table_name=table_name,
            role_name=AUTHENTICATION_APPLICATION_ROLE,
        )
        revoke_all_column_privileges(
            op,
            table_name=table_name,
            role_name=AUTHENTICATION_APPLICATION_ROLE,
            column_names=columns,
        )
    for table_name in (_TENANTS_TABLE, _USERS_TABLE, _AUDIT_EVENTS_TABLE):
        revoke_all_table_privileges(
            op,
            table_name=table_name,
            role_name=AUTHENTICATION_APPLICATION_ROLE,
        )

    for table_name, columns in (
        (_MEMBERSHIP_ROLES_TABLE, _MEMBERSHIP_ROLE_COLUMNS),
        (_USERS_TABLE, _USER_COLUMNS),
        ("user_roles", _USER_ROLE_COLUMNS),
    ):
        revoke_all_table_privileges(
            op,
            table_name=table_name,
            role_name=_PROJECTION_ROLE,
        )
        revoke_all_column_privileges(
            op,
            table_name=table_name,
            role_name=_PROJECTION_ROLE,
            column_names=columns,
        )
    for table_name, columns in (
        (_IDENTITIES_TABLE, _IDENTITY_COLUMNS),
        (_MEMBERSHIPS_TABLE, _MEMBERSHIP_COLUMNS),
    ):
        revoke_all_table_privileges(
            op,
            table_name=table_name,
            role_name=_PROJECTION_ROLE,
        )
        revoke_all_column_privileges(
            op,
            table_name=table_name,
            role_name=_PROJECTION_ROLE,
            column_names=columns,
        )

    for table_name, columns in (
        (_TRANSACTIONS_TABLE, _TRANSACTION_COLUMNS),
        (_CHOICES_TABLE, _CHOICE_COLUMNS),
        (_RATE_LIMITS_TABLE, _RATE_LIMIT_COLUMNS),
    ):
        op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{table_name}" FROM PUBLIC'))
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
                column_names=columns,
            )
        enable_forced_row_security(op, table_name=table_name)

    _create_select_policy(
        table_name=_IDENTITIES_TABLE,
        policy_name=_AUTH_IDENTITY_POLICY,
    )
    _create_select_policy(
        table_name=_MEMBERSHIPS_TABLE,
        policy_name=_AUTH_MEMBERSHIP_POLICY,
    )
    _create_select_policy(
        table_name=_TENANTS_TABLE,
        policy_name=_AUTH_TENANT_POLICY,
    )
    _create_select_policy(
        table_name=_USERS_TABLE,
        policy_name=_AUTH_USER_POLICY,
    )
    _create_insert_policy(
        table_name=_TRANSACTIONS_TABLE,
        policy_name=_AUTH_TRANSACTION_POLICY,
    )
    _create_insert_policy(
        table_name=_CHOICES_TABLE,
        policy_name=_AUTH_CHOICE_POLICY,
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_AUTH_RATE_LIMIT_POLICY}" ON "{_RATE_LIMITS_TABLE}" '
            f'AS PERMISSIVE FOR ALL TO "{AUTHENTICATION_APPLICATION_ROLE}" '
            "USING (true) WITH CHECK (true)"
        )
    )
    audit_predicate = (
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
        "and metadata = '{\"failure_reason\":\"authentication_failed\"}'::jsonb "
        "and data_classification = 'platform_metadata' "
        "and visibility_class = 'platform_ops' and integrity_hash is null "
        "and request_id ~ "
        "'^[A-Za-z0-9]$|^[A-Za-z0-9][A-Za-z0-9._-]{0,126}[A-Za-z0-9]$' "
        "and trace_id ~ '^[0-9a-f]{32}$' "
        "and trace_id <> '00000000000000000000000000000000'"
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_AUTH_AUDIT_POLICY}" ON "{_AUDIT_EVENTS_TABLE}" '
            f'AS PERMISSIVE FOR INSERT TO "{AUTHENTICATION_APPLICATION_ROLE}" '
            f"WITH CHECK ({audit_predicate})"
        )
    )

    grant_column_privilege(
        op,
        table_name=_IDENTITIES_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privilege="SELECT",
        column_names=_AUTHENTICATION_IDENTITY_COLUMNS,
    )
    grant_column_privilege(
        op,
        table_name=_MEMBERSHIPS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privilege="SELECT",
        column_names=_AUTHENTICATION_MEMBERSHIP_COLUMNS,
    )
    grant_column_privilege(
        op,
        table_name=_TENANTS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privilege="SELECT",
        column_names=("id", "slug", "name", "status"),
    )
    grant_column_privilege(
        op,
        table_name=_USERS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privilege="SELECT",
        column_names=("id", "tenant_id", "status"),
    )
    grant_table_privileges(
        op,
        table_name=_TRANSACTIONS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privileges=("INSERT",),
    )

    tenant_predicate = (
        "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid"
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_PROJECTION_IDENTITY_POLICY}" ON "{_IDENTITIES_TABLE}" '
            f'AS PERMISSIVE FOR ALL TO "{_PROJECTION_ROLE}" '
            "USING (true) WITH CHECK (true)"
        )
    )
    for table_name, policy_name in (
        (_MEMBERSHIPS_TABLE, _PROJECTION_MEMBERSHIP_POLICY),
        (_MEMBERSHIP_ROLES_TABLE, _PROJECTION_MEMBERSHIP_ROLE_POLICY),
    ):
        op.execute(
            sa.text(
                f'CREATE POLICY "{policy_name}" ON "{table_name}" '
                f'AS PERMISSIVE FOR ALL TO "{_PROJECTION_ROLE}" '
                f"USING ({tenant_predicate}) WITH CHECK ({tenant_predicate})"
            )
        )
    for table_name, policy_name in (
        (_USERS_TABLE, _PROJECTION_USER_POLICY),
        ("user_roles", _PROJECTION_USER_ROLE_POLICY),
    ):
        op.execute(
            sa.text(
                f'CREATE POLICY "{policy_name}" ON "{table_name}" '
                f'AS PERMISSIVE FOR SELECT TO "{_PROJECTION_ROLE}" '
                f"USING ({tenant_predicate})"
            )
        )
    grant_table_privileges(
        op,
        table_name=_IDENTITIES_TABLE,
        role_name=_PROJECTION_ROLE,
        privileges=("SELECT", "INSERT", "UPDATE"),
    )
    grant_table_privileges(
        op,
        table_name=_MEMBERSHIPS_TABLE,
        role_name=_PROJECTION_ROLE,
        privileges=("SELECT", "INSERT", "UPDATE"),
    )
    grant_table_privileges(
        op,
        table_name=_MEMBERSHIP_ROLES_TABLE,
        role_name=_PROJECTION_ROLE,
        privileges=("SELECT", "INSERT", "UPDATE"),
    )
    grant_table_privileges(
        op,
        table_name=_USERS_TABLE,
        role_name=_PROJECTION_ROLE,
        privileges=("SELECT",),
    )
    grant_table_privileges(
        op,
        table_name="user_roles",
        role_name=_PROJECTION_ROLE,
        privileges=("SELECT",),
    )
    grant_table_privileges(
        op,
        table_name=_CHOICES_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privileges=("INSERT",),
    )
    grant_table_privileges(
        op,
        table_name=_RATE_LIMITS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT", "UPDATE"),
    )
    grant_table_privileges(
        op,
        table_name=_AUDIT_EVENTS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privileges=("INSERT",),
    )


def _revoke_stale_authentication_object_privileges() -> None:
    quoted_role = f'"{AUTHENTICATION_APPLICATION_ROLE}"'
    quoted_schema = f'"{_SCHEMA_NAME}"'
    for object_kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
        op.execute(
            sa.text(
                f"REVOKE ALL PRIVILEGES ON ALL {object_kind} IN SCHEMA "
                f"{quoted_schema} FROM {quoted_role}"
            )
        )
    op.execute(
        sa.text(
            f"""
            DO $p3b_revoke_stale_authentication_columns$
            DECLARE
                stale_grant record;
            BEGIN
                FOR stale_grant IN
                    SELECT table_schema, table_name, column_name, privilege_type
                    FROM information_schema.column_privileges
                    WHERE grantee = '{AUTHENTICATION_APPLICATION_ROLE}'
                      AND table_schema = '{_SCHEMA_NAME}'
                LOOP
                    EXECUTE format(
                        'REVOKE %s (%I) ON TABLE %I.%I FROM %I',
                        stale_grant.privilege_type,
                        stale_grant.column_name,
                        stale_grant.table_schema,
                        stale_grant.table_name,
                        '{AUTHENTICATION_APPLICATION_ROLE}'
                    );
                END LOOP;
            END
            $p3b_revoke_stale_authentication_columns$
            """
        )
    )


def _create_select_policy(*, table_name: str, policy_name: str) -> None:
    op.execute(
        sa.text(
            f'CREATE POLICY "{policy_name}" ON "{table_name}" '
            f'AS PERMISSIVE FOR SELECT TO "{AUTHENTICATION_APPLICATION_ROLE}" USING (true)'
        )
    )


def _create_insert_policy(*, table_name: str, policy_name: str) -> None:
    op.execute(
        sa.text(
            f'CREATE POLICY "{policy_name}" ON "{table_name}" '
            f'AS PERMISSIVE FOR INSERT TO "{AUTHENTICATION_APPLICATION_ROLE}" WITH CHECK (true)'
        )
    )


def _remove_postgresql_security() -> None:
    for table_name, privileges in (
        ("user_roles", ("SELECT",)),
        (_USERS_TABLE, ("SELECT",)),
        (_MEMBERSHIP_ROLES_TABLE, ("SELECT", "INSERT", "UPDATE")),
        (_MEMBERSHIPS_TABLE, ("SELECT", "INSERT", "UPDATE")),
        (_IDENTITIES_TABLE, ("SELECT", "INSERT", "UPDATE")),
    ):
        revoke_table_privileges(
            op,
            table_name=table_name,
            role_name=_PROJECTION_ROLE,
            privileges=privileges,
        )
    for table_name, policy_name in (
        ("user_roles", _PROJECTION_USER_ROLE_POLICY),
        (_USERS_TABLE, _PROJECTION_USER_POLICY),
        (_MEMBERSHIP_ROLES_TABLE, _PROJECTION_MEMBERSHIP_ROLE_POLICY),
        (_MEMBERSHIPS_TABLE, _PROJECTION_MEMBERSHIP_POLICY),
        (_IDENTITIES_TABLE, _PROJECTION_IDENTITY_POLICY),
    ):
        drop_policy(op, table_name=table_name, policy_name=policy_name)
    revoke_table_privileges(
        op,
        table_name=_AUDIT_EVENTS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privileges=("INSERT",),
    )
    revoke_table_privileges(
        op,
        table_name=_RATE_LIMITS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT", "UPDATE"),
    )
    for table_name in (_CHOICES_TABLE, _TRANSACTIONS_TABLE):
        revoke_table_privileges(
            op,
            table_name=table_name,
            role_name=AUTHENTICATION_APPLICATION_ROLE,
            privileges=("INSERT",),
        )
    revoke_column_privilege(
        op,
        table_name=_USERS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privilege="SELECT",
        column_names=("id", "tenant_id", "status"),
    )
    revoke_column_privilege(
        op,
        table_name=_TENANTS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privilege="SELECT",
        column_names=("id", "slug", "name", "status"),
    )
    for table_name, column_names in (
        (_MEMBERSHIPS_TABLE, _AUTHENTICATION_MEMBERSHIP_COLUMNS),
        (_IDENTITIES_TABLE, _AUTHENTICATION_IDENTITY_COLUMNS),
    ):
        revoke_column_privilege(
            op,
            table_name=table_name,
            role_name=AUTHENTICATION_APPLICATION_ROLE,
            privilege="SELECT",
            column_names=column_names,
        )

    for table_name, policy_name in (
        (_AUDIT_EVENTS_TABLE, _AUTH_AUDIT_POLICY),
        (_RATE_LIMITS_TABLE, _AUTH_RATE_LIMIT_POLICY),
        (_CHOICES_TABLE, _AUTH_CHOICE_POLICY),
        (_TRANSACTIONS_TABLE, _AUTH_TRANSACTION_POLICY),
        (_USERS_TABLE, _AUTH_USER_POLICY),
        (_TENANTS_TABLE, _AUTH_TENANT_POLICY),
        (_MEMBERSHIPS_TABLE, _AUTH_MEMBERSHIP_POLICY),
        (_IDENTITIES_TABLE, _AUTH_IDENTITY_POLICY),
    ):
        drop_policy(op, table_name=table_name, policy_name=policy_name)
    revoke_schema_usage(
        op,
        schema_name=_SCHEMA_NAME,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
    )
    revoke_schema_usage(
        op,
        schema_name=_SCHEMA_NAME,
        role_name=_PROJECTION_ROLE,
    )


def _create_projection_sync_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_SYNC_FUNCTION}(
                requested_user_id uuid,
                require_pending_identity boolean DEFAULT false
            )
            RETURNS void
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $p3b_sync$
            DECLARE
                current_tenant_id uuid;
                legacy_user public.users%ROWTYPE;
                canonical_identity public.identities%ROWTYPE;
                canonical_status text;
            BEGIN
                current_tenant_id := nullif(
                    current_setting('app.tenant_id', true), ''
                )::uuid;
                IF current_tenant_id IS NULL THEN
                    RAISE EXCEPTION 'P3B identity projection requires tenant context';
                END IF;

                SELECT * INTO legacy_user
                FROM public.users
                WHERE tenant_id = current_tenant_id AND id = requested_user_id;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'P3B identity projection user is outside tenant context';
                END IF;

                SELECT * INTO canonical_identity
                FROM public.identities
                WHERE email_normalized = legacy_user.email_normalized
                FOR UPDATE;

                IF require_pending_identity
                   AND legacy_user.status = 'active'
                   AND canonical_identity.id IS NOT NULL
                   AND canonical_identity.status <> 'pending' THEN
                    RAISE EXCEPTION
                        'P3B activation identity changed before projection commit'
                        USING ERRCODE = 'WF001';
                END IF;

                canonical_status := CASE
                    WHEN legacy_user.status = 'invited' THEN 'pending'
                    ELSE legacy_user.status
                END;
                IF canonical_identity.id IS NULL THEN
                    INSERT INTO public.identities (
                        id, email, status, password_hash, created_at, updated_at
                    ) VALUES (
                        legacy_user.id,
                        legacy_user.email,
                        canonical_status,
                        legacy_user.password_hash,
                        legacy_user.created_at,
                        legacy_user.updated_at
                    )
                    RETURNING * INTO canonical_identity;
                ELSIF canonical_identity.status = 'pending'
                      AND legacy_user.status = 'active' THEN
                    UPDATE public.identities
                    SET email = legacy_user.email,
                        status = 'active',
                        password_hash = legacy_user.password_hash,
                        updated_at = legacy_user.updated_at
                    WHERE id = canonical_identity.id
                    RETURNING * INTO canonical_identity;
                END IF;

                INSERT INTO public.tenant_memberships (
                    id, tenant_id, identity_id, legacy_user_id, full_name,
                    status, permission_version, created_at, updated_at
                ) VALUES (
                    legacy_user.id,
                    legacy_user.tenant_id,
                    canonical_identity.id,
                    legacy_user.id,
                    legacy_user.full_name,
                    legacy_user.status,
                    legacy_user.permission_version,
                    legacy_user.created_at,
                    legacy_user.updated_at
                )
                ON CONFLICT (tenant_id, identity_id) DO UPDATE
                SET full_name = EXCLUDED.full_name,
                    status = EXCLUDED.status,
                    permission_version = EXCLUDED.permission_version,
                    updated_at = EXCLUDED.updated_at;

                INSERT INTO public.membership_roles (
                    tenant_id, membership_id, role_id, role_scope_type,
                    active, created_at, updated_at
                )
                SELECT
                    roles.tenant_id,
                    legacy_user.id,
                    roles.role_id,
                    roles.role_scope_type,
                    roles.active,
                    roles.created_at,
                    roles.updated_at
                FROM public.user_roles AS roles
                WHERE roles.tenant_id = current_tenant_id
                  AND roles.user_id = legacy_user.id
                ON CONFLICT (tenant_id, membership_id, role_id) DO UPDATE
                SET active = EXCLUDED.active,
                    updated_at = EXCLUDED.updated_at;
            END
            $p3b_sync$
            """
        )
    )
    op.execute(
        sa.text(
            f'ALTER FUNCTION public.{_SYNC_FUNCTION}(uuid, boolean) '
            f'OWNER TO "{_PROJECTION_ROLE}"'
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL ON FUNCTION public.{_SYNC_FUNCTION}(uuid, boolean) FROM PUBLIC"
        )
    )
    op.execute(
        sa.text(
            f"GRANT EXECUTE ON FUNCTION public.{_SYNC_FUNCTION}(uuid, boolean) "
            f'TO "{TENANT_APPLICATION_ROLE}"'
        )
    )


def _drop_projection_sync_function() -> None:
    op.execute(
        sa.text(
            f"REVOKE EXECUTE ON FUNCTION public.{_SYNC_FUNCTION}(uuid, boolean) "
            f'FROM "{TENANT_APPLICATION_ROLE}"'
        )
    )
    op.execute(
        sa.text(
            f"DROP FUNCTION IF EXISTS public.{_SYNC_FUNCTION}(uuid, boolean)"
        )
    )


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
