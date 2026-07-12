"""close invitation acceptance and global identity password recovery

Revision ID: 0026_p3e_identity_checkpoint
Revises: 0025_p3d_platform_authentication
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    assert_capability_role_has_no_parent_memberships,
    disable_forced_row_security,
    drop_policy,
    enable_forced_row_security,
    ensure_capability_role,
    grant_schema_usage,
    grant_table_privileges,
    revoke_all_column_privileges,
    revoke_all_schema_privileges,
    revoke_all_table_privileges,
    revoke_schema_usage,
    revoke_table_privileges,
)
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy.dialects import postgresql

revision: str = "0026_p3e_identity_checkpoint"
down_revision: str | None = "0025_p3d_platform_authentication"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RESET_TABLE = "password_reset_tokens"
_IDENTITIES_TABLE = "identities"
_MEMBERSHIPS_TABLE = "tenant_memberships"
_USERS_TABLE = "users"
_TENANT_FAMILIES_TABLE = "refresh_session_families"
_PLATFORM_FAMILIES_TABLE = "platform_refresh_session_families"
_SELECTION_TRANSACTIONS_TABLE = "organization_selection_transactions"
_AUDIT_TABLE = "audit_events"
_SYNC_FUNCTION = "sync_current_tenant_identity_membership"
_ACCEPT_FUNCTION = "accept_existing_identity_membership"
_ISSUE_RESET_FUNCTION = "issue_identity_password_reset"
_COMPLETE_RESET_FUNCTION = "complete_identity_password_reset"
_PROJECTION_ROLE = "wealthy_falcon_identity_projection"
_RECOVERY_ROLE = "wealthy_falcon_identity_recovery"

_RESET_RECOVERY_POLICY = "identity_recovery_password_reset_access"
_RECOVERY_IDENTITY_POLICY = "identity_recovery_identity_access"
_RECOVERY_MEMBERSHIP_POLICY = "identity_recovery_membership_read"
_RECOVERY_USER_POLICY = "identity_recovery_user_access"
_RECOVERY_TENANT_FAMILY_POLICY = "identity_recovery_tenant_session_access"
_RECOVERY_PLATFORM_FAMILY_POLICY = "identity_recovery_platform_session_access"
_RECOVERY_SELECTION_POLICY = "identity_recovery_selection_access"
_RECOVERY_AUDIT_POLICY = "authentication_password_recovery_audit_insert"

_RESET_COLUMNS = (
    "id",
    "identity_id",
    "token_hash",
    "expires_at",
    "consumed_at",
    "revoked_at",
    "created_at",
    "updated_at",
)


def upgrade() -> None:
    _create_reset_table()
    _expand_rate_limit_scopes()
    if op.get_bind().dialect.name == "postgresql":
        _configure_postgresql_security()
        _create_existing_identity_acceptance_function()
        _create_password_reset_issue_function()
        _create_password_reset_completion_function()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _drop_password_reset_completion_function()
        _drop_password_reset_issue_function()
        _drop_existing_identity_acceptance_function()
        _remove_postgresql_security()
    _contract_rate_limit_scopes()
    op.drop_table(_RESET_TABLE)


def _expand_rate_limit_scopes() -> None:
    _replace_rate_limit_scope_constraint(
        "scope in ('login_source','login_identity','activation_source',"
        "'activation_token','password_reset_source','password_reset_identity',"
        "'password_reset_confirm_source','password_reset_confirm_token')"
    )


def _contract_rate_limit_scopes() -> None:
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"
    if is_postgresql:
        # The table is FORCE-RLS, including for its non-BYPASS migration owner. Downgrade must
        # remove P3E-only rows before restoring P3B's narrower check constraint.
        disable_forced_row_security(
            op,
            table_name="authentication_rate_limit_buckets",
        )
    bind.execute(
        sa.text(
            "delete from authentication_rate_limit_buckets "
            "where scope not in ('login_source','login_identity')"
        )
    )
    _replace_rate_limit_scope_constraint("scope in ('login_source','login_identity')")
    if is_postgresql:
        enable_forced_row_security(
            op,
            table_name="authentication_rate_limit_buckets",
        )


def _replace_rate_limit_scope_constraint(predicate: str) -> None:
    table_name = "authentication_rate_limit_buckets"
    constraint_name = "ck_authentication_rate_limit_buckets_scope"
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            batch_op.drop_constraint(constraint_name, type_="check")
            batch_op.create_check_constraint(constraint_name, predicate)
        return
    op.drop_constraint(constraint_name, table_name, type_="check")
    op.create_check_constraint(constraint_name, table_name, predicate)


def _create_reset_table() -> None:
    op.create_table(
        _RESET_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            name="ck_password_reset_tokens_hash_length",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_password_reset_tokens_expiry_order",
        ),
        sa.CheckConstraint(
            "consumed_at is null or consumed_at >= created_at",
            name="ck_password_reset_tokens_consumed_order",
        ),
        sa.CheckConstraint(
            "revoked_at is null or revoked_at >= created_at",
            name="ck_password_reset_tokens_revoked_order",
        ),
        sa.CheckConstraint(
            "consumed_at is null or revoked_at is null",
            name="ck_password_reset_tokens_terminal_state",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["identities.id"],
            name="fk_password_reset_tokens_identity_id_identities",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_password_reset_tokens"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_password_reset_tokens_token_hash",
        ),
    )
    op.create_index(
        "ix_password_reset_tokens_identity_expires_at",
        _RESET_TABLE,
        ["identity_id", "expires_at"],
    )
    op.create_index(
        "ix_password_reset_tokens_expires_at",
        _RESET_TABLE,
        ["expires_at"],
    )


def _assert_recovery_owner_role_is_private() -> None:
    op.execute(
        sa.text(
            f"""
            DO $p3e_recovery_owner_preflight$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_auth_members AS membership
                    JOIN pg_catalog.pg_roles AS owner_role
                      ON owner_role.oid = membership.roleid
                    JOIN pg_catalog.pg_roles AS member_role
                      ON member_role.oid = membership.member
                    WHERE owner_role.rolname = '{_RECOVERY_ROLE}'
                      AND member_role.rolname <> current_user
                ) THEN
                    RAISE EXCEPTION
                        'P3E recovery owner preflight failed: role {_RECOVERY_ROLE} '
                        'must not be granted to an application or gateway role';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_namespace AS namespace
                    JOIN pg_catalog.pg_roles AS owner_role
                      ON owner_role.oid = namespace.nspowner
                    WHERE namespace.nspname = 'public'
                      AND owner_role.rolname = '{_RECOVERY_ROLE}'
                ) OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_class AS object
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = object.relnamespace
                    JOIN pg_catalog.pg_roles AS owner_role
                      ON owner_role.oid = object.relowner
                    WHERE namespace.nspname = 'public'
                      AND owner_role.rolname = '{_RECOVERY_ROLE}'
                ) OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_proc AS routine
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = routine.pronamespace
                    JOIN pg_catalog.pg_roles AS owner_role
                      ON owner_role.oid = routine.proowner
                    WHERE namespace.nspname = 'public'
                      AND owner_role.rolname = '{_RECOVERY_ROLE}'
                ) THEN
                    RAISE EXCEPTION
                        'P3E recovery owner preflight failed: reused role {_RECOVERY_ROLE} '
                        'owns a pre-existing public object';
                END IF;
            END
            $p3e_recovery_owner_preflight$
            """
        )
    )


def _revoke_stale_recovery_object_privileges() -> None:
    quoted_role = f'"{_RECOVERY_ROLE}"'
    for object_kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
        op.execute(
            sa.text(
                f"REVOKE ALL PRIVILEGES ON ALL {object_kind} IN SCHEMA public FROM {quoted_role}"
            )
        )
    op.execute(
        sa.text(
            f"""
            DO $p3e_revoke_stale_recovery_columns$
            DECLARE
                stale_grant record;
            BEGIN
                FOR stale_grant IN
                    SELECT table_schema, table_name, column_name, privilege_type
                    FROM information_schema.column_privileges
                    WHERE grantee = '{_RECOVERY_ROLE}'
                      AND table_schema = 'public'
                LOOP
                    EXECUTE format(
                        'REVOKE %s (%I) ON TABLE %I.%I FROM %I',
                        stale_grant.privilege_type,
                        stale_grant.column_name,
                        stale_grant.table_schema,
                        stale_grant.table_name,
                        '{_RECOVERY_ROLE}'
                    );
                END LOOP;
            END
            $p3e_revoke_stale_recovery_columns$
            """
        )
    )


def _configure_postgresql_security() -> None:
    ensure_capability_role(op, _RECOVERY_ROLE)
    assert_capability_role_has_no_parent_memberships(op, _RECOVERY_ROLE)
    _assert_recovery_owner_role_is_private()
    revoke_all_schema_privileges(op, schema_name="public", role_name=_RECOVERY_ROLE)
    _revoke_stale_recovery_object_privileges()
    grant_schema_usage(op, schema_name="public", role_name=_RECOVERY_ROLE)

    op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{_RESET_TABLE}" FROM PUBLIC'))
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
        _RECOVERY_ROLE,
    ):
        revoke_all_table_privileges(
            op,
            table_name=_RESET_TABLE,
            role_name=role_name,
        )
        revoke_all_column_privileges(
            op,
            table_name=_RESET_TABLE,
            role_name=role_name,
            column_names=_RESET_COLUMNS,
        )
    enable_forced_row_security(op, table_name=_RESET_TABLE)

    _create_policy(
        table_name=_RESET_TABLE,
        policy_name=_RESET_RECOVERY_POLICY,
        role_name=_RECOVERY_ROLE,
        command="ALL",
    )
    _create_policy(
        table_name=_IDENTITIES_TABLE,
        policy_name=_RECOVERY_IDENTITY_POLICY,
        role_name=_RECOVERY_ROLE,
        command="ALL",
    )
    _create_policy(
        table_name=_MEMBERSHIPS_TABLE,
        policy_name=_RECOVERY_MEMBERSHIP_POLICY,
        role_name=_RECOVERY_ROLE,
        command="SELECT",
    )
    _create_policy(
        table_name=_USERS_TABLE,
        policy_name=_RECOVERY_USER_POLICY,
        role_name=_RECOVERY_ROLE,
        command="ALL",
    )
    _create_policy(
        table_name=_TENANT_FAMILIES_TABLE,
        policy_name=_RECOVERY_TENANT_FAMILY_POLICY,
        role_name=_RECOVERY_ROLE,
        command="ALL",
    )
    _create_policy(
        table_name=_PLATFORM_FAMILIES_TABLE,
        policy_name=_RECOVERY_PLATFORM_FAMILY_POLICY,
        role_name=_RECOVERY_ROLE,
        command="ALL",
    )
    _create_policy(
        table_name=_SELECTION_TRANSACTIONS_TABLE,
        policy_name=_RECOVERY_SELECTION_POLICY,
        role_name=_RECOVERY_ROLE,
        command="ALL",
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_RECOVERY_AUDIT_POLICY}" ON "{_AUDIT_TABLE}" '
            f'AS PERMISSIVE FOR INSERT TO "{AUTHENTICATION_APPLICATION_ROLE}" '
            f"WITH CHECK ({_password_recovery_audit_predicate()})"
        )
    )

    for table_name, privileges in (
        (_RESET_TABLE, ("SELECT", "INSERT", "UPDATE")),
        (_IDENTITIES_TABLE, ("SELECT", "UPDATE")),
        (_MEMBERSHIPS_TABLE, ("SELECT",)),
        (_USERS_TABLE, ("SELECT", "UPDATE")),
        (_TENANT_FAMILIES_TABLE, ("SELECT", "UPDATE")),
        (_PLATFORM_FAMILIES_TABLE, ("SELECT", "UPDATE")),
        (_SELECTION_TRANSACTIONS_TABLE, ("SELECT", "UPDATE")),
    ):
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=_RECOVERY_ROLE,
            privileges=privileges,
        )


def _remove_postgresql_security() -> None:
    for table_name, privileges in (
        (_SELECTION_TRANSACTIONS_TABLE, ("SELECT", "UPDATE")),
        (_PLATFORM_FAMILIES_TABLE, ("SELECT", "UPDATE")),
        (_TENANT_FAMILIES_TABLE, ("SELECT", "UPDATE")),
        (_USERS_TABLE, ("SELECT", "UPDATE")),
        (_MEMBERSHIPS_TABLE, ("SELECT",)),
        (_IDENTITIES_TABLE, ("SELECT", "UPDATE")),
        (_RESET_TABLE, ("SELECT", "INSERT", "UPDATE")),
    ):
        revoke_table_privileges(
            op,
            table_name=table_name,
            role_name=_RECOVERY_ROLE,
            privileges=privileges,
        )
    for table_name, policy_name in (
        (_AUDIT_TABLE, _RECOVERY_AUDIT_POLICY),
        (_SELECTION_TRANSACTIONS_TABLE, _RECOVERY_SELECTION_POLICY),
        (_PLATFORM_FAMILIES_TABLE, _RECOVERY_PLATFORM_FAMILY_POLICY),
        (_TENANT_FAMILIES_TABLE, _RECOVERY_TENANT_FAMILY_POLICY),
        (_USERS_TABLE, _RECOVERY_USER_POLICY),
        (_MEMBERSHIPS_TABLE, _RECOVERY_MEMBERSHIP_POLICY),
        (_IDENTITIES_TABLE, _RECOVERY_IDENTITY_POLICY),
        (_RESET_TABLE, _RESET_RECOVERY_POLICY),
    ):
        drop_policy(op, table_name=table_name, policy_name=policy_name)
    revoke_schema_usage(op, schema_name="public", role_name=_RECOVERY_ROLE)


def _create_policy(
    *,
    table_name: str,
    policy_name: str,
    role_name: str,
    command: str,
) -> None:
    using = " USING (true)" if command != "INSERT" else ""
    check = " WITH CHECK (true)" if command in {"ALL", "INSERT", "UPDATE"} else ""
    op.execute(
        sa.text(
            f'CREATE POLICY "{policy_name}" ON "{table_name}" '
            f'AS PERMISSIVE FOR {command} TO "{role_name}"{using}{check}'
        )
    )


def _create_existing_identity_acceptance_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_ACCEPT_FUNCTION}(
                requested_user_id uuid,
                verified_password_hash text
            )
            RETURNS void
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $p3e_accept$
            DECLARE
                current_tenant_id uuid;
                legacy_user public.users%ROWTYPE;
                canonical_identity public.identities%ROWTYPE;
            BEGIN
                current_tenant_id := nullif(
                    current_setting('app.tenant_id', true), ''
                )::uuid;
                IF current_tenant_id IS NULL THEN
                    RAISE EXCEPTION 'P3E membership acceptance requires tenant context';
                END IF;

                SELECT * INTO legacy_user
                FROM public.users
                WHERE tenant_id = current_tenant_id AND id = requested_user_id;
                IF NOT FOUND OR legacy_user.status <> 'active' THEN
                    RAISE EXCEPTION 'P3E membership acceptance user is invalid'
                        USING ERRCODE = 'WF002';
                END IF;

                SELECT * INTO canonical_identity
                FROM public.identities
                WHERE email_normalized = legacy_user.email_normalized
                FOR UPDATE;
                IF NOT FOUND
                   OR canonical_identity.status <> 'active'
                   OR canonical_identity.password_hash IS DISTINCT FROM verified_password_hash
                   OR legacy_user.password_hash IS DISTINCT FROM verified_password_hash THEN
                    RAISE EXCEPTION 'P3E verified identity changed before membership acceptance'
                        USING ERRCODE = 'WF002';
                END IF;

                PERFORM public.{_SYNC_FUNCTION}(requested_user_id, false);
            END
            $p3e_accept$
            """
        )
    )
    op.execute(
        sa.text(
            f'ALTER FUNCTION public.{_ACCEPT_FUNCTION}(uuid, text) OWNER TO "{_PROJECTION_ROLE}"'
        )
    )
    op.execute(sa.text(f"REVOKE ALL ON FUNCTION public.{_ACCEPT_FUNCTION}(uuid, text) FROM PUBLIC"))
    op.execute(
        sa.text(
            f"GRANT EXECUTE ON FUNCTION public.{_ACCEPT_FUNCTION}(uuid, text) "
            f'TO "{TENANT_APPLICATION_ROLE}"'
        )
    )


def _drop_existing_identity_acceptance_function() -> None:
    op.execute(
        sa.text(
            f"REVOKE EXECUTE ON FUNCTION public.{_ACCEPT_FUNCTION}(uuid, text) "
            f'FROM "{TENANT_APPLICATION_ROLE}"'
        )
    )
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS public.{_ACCEPT_FUNCTION}(uuid, text)"))


def _create_password_reset_completion_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_COMPLETE_RESET_FUNCTION}(
                requested_identity_id uuid,
                requested_token_hash text,
                replacement_password_hash text
            )
            RETURNS boolean
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $p3e_reset$
            DECLARE
                reset_row public.password_reset_tokens%ROWTYPE;
                identity_row public.identities%ROWTYPE;
                reset_at timestamptz := clock_timestamp();
            BEGIN
                IF length(requested_token_hash) <> 64
                   OR replacement_password_hash NOT LIKE '$argon2id$%'
                   OR length(replacement_password_hash) > 1024 THEN
                    RETURN false;
                END IF;

                SELECT tokens.* INTO reset_row
                FROM public.password_reset_tokens AS tokens
                WHERE tokens.identity_id = requested_identity_id
                  AND tokens.token_hash = requested_token_hash
                  AND tokens.consumed_at IS NULL
                  AND tokens.revoked_at IS NULL
                FOR UPDATE;
                IF NOT FOUND OR reset_row.expires_at <= reset_at THEN
                    RETURN false;
                END IF;

                SELECT identities.* INTO identity_row
                FROM public.identities AS identities
                WHERE identities.id = requested_identity_id
                  AND identities.status = 'active'
                FOR UPDATE;
                IF NOT FOUND THEN
                    RETURN false;
                END IF;

                UPDATE public.identities
                SET password_hash = replacement_password_hash,
                    updated_at = reset_at
                WHERE id = requested_identity_id;

                UPDATE public.users AS users
                SET password_hash = replacement_password_hash,
                    updated_at = reset_at
                FROM public.tenant_memberships AS memberships
                WHERE memberships.identity_id = requested_identity_id
                  AND users.tenant_id = memberships.tenant_id
                  AND users.id = memberships.legacy_user_id;

                UPDATE public.password_reset_tokens
                SET consumed_at = reset_at, updated_at = reset_at
                WHERE id = reset_row.id;
                UPDATE public.password_reset_tokens
                SET revoked_at = reset_at, updated_at = reset_at
                WHERE identity_id = requested_identity_id
                  AND id <> reset_row.id
                  AND consumed_at IS NULL
                  AND revoked_at IS NULL;

                UPDATE public.refresh_session_families AS families
                SET revoked_at = reset_at, updated_at = reset_at
                FROM public.tenant_memberships AS memberships
                WHERE memberships.identity_id = requested_identity_id
                  AND families.tenant_id = memberships.tenant_id
                  AND families.membership_id = memberships.id
                  AND families.revoked_at IS NULL;
                UPDATE public.platform_refresh_session_families
                SET revoked_at = reset_at, updated_at = reset_at
                WHERE identity_id = requested_identity_id
                  AND revoked_at IS NULL;
                UPDATE public.organization_selection_transactions
                SET consumed_at = reset_at, updated_at = reset_at
                WHERE identity_id = requested_identity_id
                  AND consumed_at IS NULL;

                RETURN true;
            END
            $p3e_reset$
            """
        )
    )
    op.execute(
        sa.text(
            f"ALTER FUNCTION public.{_COMPLETE_RESET_FUNCTION}(uuid, text, text) "
            f'OWNER TO "{_RECOVERY_ROLE}"'
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL ON FUNCTION public.{_COMPLETE_RESET_FUNCTION}(uuid, text, text) "
            "FROM PUBLIC"
        )
    )
    op.execute(
        sa.text(
            f"GRANT EXECUTE ON FUNCTION public.{_COMPLETE_RESET_FUNCTION}(uuid, text, text) "
            f'TO "{AUTHENTICATION_APPLICATION_ROLE}"'
        )
    )


def _create_password_reset_issue_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_ISSUE_RESET_FUNCTION}(
                requested_identity_id uuid,
                requested_reset_id uuid,
                requested_token_hash text,
                requested_expires_at timestamptz
            )
            RETURNS boolean
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $p3e_reset_issue$
            DECLARE
                locked_identity_id uuid;
                issued_at timestamptz := clock_timestamp();
            BEGIN
                IF requested_token_hash !~ '^[0-9a-f]{{64}}$'
                   OR requested_expires_at <= issued_at
                   OR requested_expires_at > issued_at + interval '1 hour' THEN
                    RETURN false;
                END IF;
                SELECT id INTO locked_identity_id
                FROM public.identities
                WHERE id = requested_identity_id AND status = 'active'
                FOR UPDATE;
                IF NOT FOUND THEN
                    RETURN false;
                END IF;
                UPDATE public.password_reset_tokens
                SET revoked_at = issued_at, updated_at = issued_at
                WHERE identity_id = requested_identity_id
                  AND consumed_at IS NULL
                  AND revoked_at IS NULL;
                INSERT INTO public.password_reset_tokens (
                    id, identity_id, token_hash, expires_at
                ) VALUES (
                    requested_reset_id, requested_identity_id,
                    requested_token_hash, requested_expires_at
                );
                RETURN true;
            END
            $p3e_reset_issue$
            """
        )
    )
    op.execute(
        sa.text(
            f"ALTER FUNCTION public.{_ISSUE_RESET_FUNCTION}(uuid, uuid, text, timestamptz) "
            f'OWNER TO "{_RECOVERY_ROLE}"'
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL ON FUNCTION public.{_ISSUE_RESET_FUNCTION}"
            "(uuid, uuid, text, timestamptz) FROM PUBLIC"
        )
    )
    op.execute(
        sa.text(
            f"GRANT EXECUTE ON FUNCTION public.{_ISSUE_RESET_FUNCTION}"
            "(uuid, uuid, text, timestamptz) "
            f'TO "{AUTHENTICATION_APPLICATION_ROLE}"'
        )
    )


def _drop_password_reset_issue_function() -> None:
    op.execute(
        sa.text(
            f"REVOKE EXECUTE ON FUNCTION public.{_ISSUE_RESET_FUNCTION}"
            "(uuid, uuid, text, timestamptz) "
            f'FROM "{AUTHENTICATION_APPLICATION_ROLE}"'
        )
    )
    op.execute(
        sa.text(
            f"DROP FUNCTION IF EXISTS public.{_ISSUE_RESET_FUNCTION}(uuid, uuid, text, timestamptz)"
        )
    )


def _drop_password_reset_completion_function() -> None:
    op.execute(
        sa.text(
            f"REVOKE EXECUTE ON FUNCTION public.{_COMPLETE_RESET_FUNCTION}(uuid, text, text) "
            f'FROM "{AUTHENTICATION_APPLICATION_ROLE}"'
        )
    )
    op.execute(
        sa.text(f"DROP FUNCTION IF EXISTS public.{_COMPLETE_RESET_FUNCTION}(uuid, text, text)")
    )


def _password_recovery_audit_predicate() -> str:
    common = (
        "scope_type = 'platform' and tenant_id is null "
        "and actor_type = 'system' and actor_user_id is null "
        "and impersonator_user_id is null "
        "and category = 'platform_operations' and severity = 'info' "
        "and result = 'success' and session_id is null "
        "and ip_address is null and user_agent is null "
        "and reason is null and support_ticket_id is null "
        "and changed_fields = '[]'::jsonb "
        "and before_data = '{}'::jsonb and after_data = '{}'::jsonb "
        "and metadata = '{}'::jsonb "
        "and data_classification = 'security_metadata' "
        "and visibility_class = 'platform_ops' and integrity_hash is null "
        "and request_id ~ "
        "'^[A-Za-z0-9]$|^[A-Za-z0-9][A-Za-z0-9._-]{0,126}[A-Za-z0-9]$' "
        "and trace_id ~ '^[0-9a-f]{32}$' "
        "and trace_id <> '00000000000000000000000000000000'"
    )
    requested = (
        "event_type = 'auth.password_reset.requested' "
        "and resource_type = 'authentication' and resource_id is null "
        "and action = 'request_password_reset'"
    )
    completed = (
        "event_type = 'auth.password_reset.completed' "
        "and resource_type = 'identity' and resource_id is not null "
        "and action = 'complete_password_reset'"
    )
    return f"{common} and (({requested}) or ({completed}))"


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
