"""Harden Phase 9 own-evidence isolation and privacy coverage execution.

Revision ID: 0042_p9_privacy_evidence_hardening
Revises: 0041_p9_privacy_compliance
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    assert_capability_role_has_no_parent_memberships,
    create_tenant_isolation_policy,
    drop_policy,
    ensure_capability_role,
    grant_schema_usage,
    grant_table_privileges,
    revoke_all_schema_privileges,
    revoke_all_table_privileges,
)
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)

revision: str = "0042_p9_privacy_evidence_hardening"
down_revision: str | None = "0041_p9_privacy_compliance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EXECUTOR_ROLE = "wealthy_falcon_privacy_coverage"
_FUNCTION_SIGNATURE = "public.p9_privacy_notice_coverage(uuid[])"

_OWN_EVIDENCE_TABLES = (
    "privacy_notice_acknowledgements",
    "privacy_consent_states",
    "privacy_consent_events",
)
_EXECUTOR_TENANT_TABLES = (
    "users",
    "tenant_memberships",
    "user_roles",
    "privacy_notices",
    "privacy_notice_acknowledgements",
)
_EXECUTOR_GLOBAL_TABLES = (
    "role_permissions",
    "permissions",
)
_ALL_EXECUTOR_TABLES = _EXECUTOR_TENANT_TABLES + _EXECUTOR_GLOBAL_TABLES


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    _configure_private_executor()
    _replace_own_evidence_policies()
    _create_coverage_function()


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_SIGNATURE}"))
    for table_name in _EXECUTOR_TENANT_TABLES:
        drop_policy(
            op,
            table_name=table_name,
            policy_name=_executor_policy_name(table_name),
        )
    for table_name in _OWN_EVIDENCE_TABLES:
        policy_name = _tenant_policy_name(table_name)
        drop_policy(op, table_name=table_name, policy_name=policy_name)
        create_tenant_isolation_policy(
            op,
            table_name=table_name,
            policy_name=policy_name,
            role_name=TENANT_APPLICATION_ROLE,
        )
    for table_name in _ALL_EXECUTOR_TABLES:
        revoke_all_table_privileges(
            op,
            table_name=table_name,
            role_name=_EXECUTOR_ROLE,
        )
    revoke_all_schema_privileges(op, schema_name="public", role_name=_EXECUTOR_ROLE)


def _configure_private_executor() -> None:
    ensure_capability_role(op, _EXECUTOR_ROLE)
    assert_capability_role_has_no_parent_memberships(op, _EXECUTOR_ROLE)
    _assert_executor_has_no_members()
    revoke_all_schema_privileges(op, schema_name="public", role_name=_EXECUTOR_ROLE)
    grant_schema_usage(op, schema_name="public", role_name=_EXECUTOR_ROLE)
    # PostgreSQL requires the new function owner to have CREATE on its schema. The grant exists
    # only for the ownership transfer and is revoked immediately after the fixed function is made.
    op.execute(sa.text(f'GRANT CREATE ON SCHEMA public TO "{_EXECUTOR_ROLE}"'))
    for table_name in _ALL_EXECUTOR_TABLES:
        revoke_all_table_privileges(
            op,
            table_name=table_name,
            role_name=_EXECUTOR_ROLE,
        )
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=_EXECUTOR_ROLE,
            privileges=("SELECT",),
        )
    for table_name in _EXECUTOR_TENANT_TABLES:
        policy_name = _executor_policy_name(table_name)
        drop_policy(op, table_name=table_name, policy_name=policy_name)
        tenant_expression = (
            "tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid"
        )
        op.execute(
            sa.text(
                f'CREATE POLICY "{policy_name}" ON "{table_name}" '
                f'AS PERMISSIVE FOR SELECT TO "{_EXECUTOR_ROLE}" '
                f"USING ({tenant_expression})"
            )
        )


def _assert_executor_has_no_members() -> None:
    op.execute(
        sa.text(
            f"""
            DO $p9_privacy_executor_membership_preflight$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_auth_members AS membership
                    JOIN pg_catalog.pg_roles AS executor
                      ON executor.oid = membership.roleid
                    WHERE executor.rolname = '{_EXECUTOR_ROLE}'
                ) THEN
                    RAISE EXCEPTION
                        'P9 privacy coverage executor preflight failed: private owner has members';
                END IF;
            END
            $p9_privacy_executor_membership_preflight$
            """
        )
    )


def _replace_own_evidence_policies() -> None:
    own_expression = (
        "tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid "
        "AND user_id = NULLIF(pg_catalog.current_setting('app.actor_id', true), '')::uuid "
        "AND membership_id = "
        "NULLIF(pg_catalog.current_setting('app.membership_id', true), '')::uuid"
    )
    for table_name in _OWN_EVIDENCE_TABLES:
        policy_name = _tenant_policy_name(table_name)
        drop_policy(op, table_name=table_name, policy_name=policy_name)
        op.execute(
            sa.text(
                f'CREATE POLICY "{policy_name}" ON "{table_name}" '
                f'TO "{TENANT_APPLICATION_ROLE}" USING ({own_expression}) '
                f'WITH CHECK ({own_expression})'
            )
        )


def _create_coverage_function() -> None:
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_SIGNATURE}"))
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {_FUNCTION_SIGNATURE.removesuffix('(uuid[])')}(
                requested_notice_ids uuid[]
            )
            RETURNS TABLE (
                notice_id uuid,
                acknowledged_count bigint,
                eligible_count bigint
            )
            LANGUAGE sql
            STABLE
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $function$
                WITH request_context AS (
                    SELECT
                        NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid
                            AS tenant_id,
                        NULLIF(pg_catalog.current_setting('app.actor_id', true), '')::uuid
                            AS actor_id,
                        NULLIF(pg_catalog.current_setting('app.membership_id', true), '')::uuid
                            AS membership_id
                ),
                authorized AS (
                    SELECT request_context.tenant_id
                    FROM request_context
                    JOIN public.users
                      ON users.tenant_id = request_context.tenant_id
                     AND users.id = request_context.actor_id
                     AND users.status = 'active'
                    JOIN public.tenant_memberships
                      ON tenant_memberships.tenant_id = request_context.tenant_id
                     AND tenant_memberships.id = request_context.membership_id
                     AND tenant_memberships.legacy_user_id = request_context.actor_id
                     AND tenant_memberships.status = 'active'
                     AND tenant_memberships.permission_version = users.permission_version
                    WHERE EXISTS (
                        SELECT 1
                        FROM pg_catalog.pg_roles AS login_role
                        WHERE login_role.rolname = session_user
                          AND login_role.rolcanlogin IS TRUE
                          AND (
                              login_role.rolsuper IS TRUE
                              OR (
                                  login_role.rolsuper IS FALSE
                                  AND login_role.rolbypassrls IS FALSE
                                  AND pg_catalog.pg_has_role(
                                      session_user,
                                      '{TENANT_APPLICATION_ROLE}',
                                      'SET'
                                  )
                              )
                          )
                    )
                      AND EXISTS (
                        SELECT 1
                        FROM public.user_roles
                        JOIN public.role_permissions
                          ON role_permissions.role_id = user_roles.role_id
                        JOIN public.permissions
                          ON permissions.id = role_permissions.permission_id
                        WHERE user_roles.tenant_id = request_context.tenant_id
                          AND user_roles.user_id = request_context.actor_id
                          AND user_roles.active IS TRUE
                          AND permissions.code IN (
                              'privacy_compliance:read:tenant',
                              'privacy_notice:manage:tenant'
                          )
                    )
                ),
                eligible_memberships AS (
                    SELECT tenant_memberships.id, users.id AS user_id
                    FROM authorized
                    JOIN public.users ON users.tenant_id = authorized.tenant_id
                    JOIN public.tenant_memberships
                      ON tenant_memberships.tenant_id = users.tenant_id
                     AND tenant_memberships.legacy_user_id = users.id
                    WHERE users.status = 'active'
                      AND tenant_memberships.status = 'active'
                      AND tenant_memberships.permission_version = users.permission_version
                      AND EXISTS (
                          SELECT 1
                          FROM public.user_roles
                          JOIN public.role_permissions
                            ON role_permissions.role_id = user_roles.role_id
                          JOIN public.permissions
                            ON permissions.id = role_permissions.permission_id
                          WHERE user_roles.tenant_id = authorized.tenant_id
                            AND user_roles.user_id = users.id
                            AND user_roles.active IS TRUE
                            AND permissions.code = 'privacy_notice:read:own'
                      )
                ),
                eligible AS (
                    SELECT count(*)::bigint AS total
                    FROM eligible_memberships
                ),
                acknowledgement_counts AS (
                    SELECT
                        acknowledgements.notice_id,
                        count(DISTINCT acknowledgements.membership_id)::bigint AS total
                    FROM authorized
                    JOIN public.privacy_notice_acknowledgements AS acknowledgements
                      ON acknowledgements.tenant_id = authorized.tenant_id
                    JOIN eligible_memberships
                      ON eligible_memberships.id = acknowledgements.membership_id
                     AND eligible_memberships.user_id = acknowledgements.user_id
                    WHERE acknowledgements.notice_id = ANY(
                        coalesce(requested_notice_ids, ARRAY[]::uuid[])
                    )
                    GROUP BY acknowledgements.notice_id
                )
                SELECT
                    notices.id,
                    coalesce(acknowledgement_counts.total, 0)::bigint,
                    eligible.total
                FROM authorized
                JOIN public.privacy_notices AS notices
                  ON notices.tenant_id = authorized.tenant_id
                CROSS JOIN eligible
                LEFT JOIN acknowledgement_counts
                  ON acknowledgement_counts.notice_id = notices.id
                WHERE notices.id = ANY(
                    coalesce(requested_notice_ids, ARRAY[]::uuid[])
                )
            $function$
            """
        )
    )
    op.execute(sa.text(f'ALTER FUNCTION {_FUNCTION_SIGNATURE} OWNER TO "{_EXECUTOR_ROLE}"'))
    op.execute(sa.text(f"REVOKE ALL PRIVILEGES ON FUNCTION {_FUNCTION_SIGNATURE} FROM PUBLIC"))
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
    ):
        op.execute(
            sa.text(f'REVOKE ALL PRIVILEGES ON FUNCTION {_FUNCTION_SIGNATURE} FROM "{role_name}"')
        )
    op.execute(
        sa.text(
            f'GRANT EXECUTE ON FUNCTION {_FUNCTION_SIGNATURE} TO "{TENANT_APPLICATION_ROLE}"'
        )
    )
    op.execute(sa.text(f'REVOKE CREATE ON SCHEMA public FROM "{_EXECUTOR_ROLE}"'))


def _tenant_policy_name(table_name: str) -> str:
    return f"p9_{table_name}_tenant_isolation"


def _executor_policy_name(table_name: str) -> str:
    return f"p9_privacy_coverage_{table_name}_read"


__all__ = ["downgrade", "upgrade"]
