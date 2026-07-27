"""Add a least-privilege profile lock gateway for employee lifecycle commands.

Revision ID: 0043_p11_employee_lifecycle_profile_lock
Revises: 0042_p9_privacy_evidence_hardening
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)

revision: str = "0043_p11_employee_lifecycle_profile_lock"
down_revision: str | None = "0042_p9_privacy_evidence_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EXECUTOR_ROLE = "wealthy_falcon_identity_recovery"
_IDENTITY_PROJECTION_ROLE = "wealthy_falcon_identity_projection"
_LOCK_FUNCTION_SIGNATURE = "public.lock_employee_profile_for_command(uuid)"
_ACTIVE_EMPLOYEE_GUARD_FUNCTION_SIGNATURE = (
    "public.guard_employee_profile_change_request_active_employee()"
)
_ACTIVE_EMPLOYEE_GUARD_TRIGGER = "trg_employee_profile_change_request_active_employee"
_CHANGE_REQUESTS_TABLE = "employee_profile_change_requests"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    _assert_executor_owner_transfer_is_safe()
    op.execute(
        sa.text(
            """
            CREATE FUNCTION public.lock_employee_profile_for_command(
                requested_employee_id uuid
            ) RETURNS boolean
            LANGUAGE plpgsql
            VOLATILE
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $p11_employee_lifecycle_profile_lock$
            DECLARE
                current_tenant_id uuid;
                current_actor_id uuid;
                current_membership_id uuid;
            BEGIN
                current_tenant_id := NULLIF(
                    pg_catalog.current_setting('app.tenant_id', true), ''
                )::uuid;
                current_actor_id := NULLIF(
                    pg_catalog.current_setting('app.actor_id', true), ''
                )::uuid;
                current_membership_id := NULLIF(
                    pg_catalog.current_setting('app.membership_id', true), ''
                )::uuid;

                IF requested_employee_id IS NULL
                   OR current_tenant_id IS NULL
                   OR current_actor_id IS NULL
                   OR current_membership_id IS NULL
                   OR NOT EXISTS (
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
                                     'wealthy_falcon_app',
                                     'SET'
                                 )
                             )
                         )
                   )
                   OR NOT public.is_current_tenant_membership_link_eligible(
                       current_membership_id
                   )
                   OR NOT EXISTS (
                       SELECT 1
                       FROM public.tenant_memberships AS memberships
                       WHERE memberships.tenant_id = current_tenant_id
                         AND memberships.id = current_membership_id
                         AND memberships.legacy_user_id = current_actor_id
                   )
                   OR NOT EXISTS (
                       SELECT 1
                       FROM public.membership_roles
                       JOIN public.role_permissions
                         ON role_permissions.role_id = membership_roles.role_id
                       JOIN public.permissions
                         ON permissions.id = role_permissions.permission_id
                       WHERE membership_roles.tenant_id = current_tenant_id
                         AND membership_roles.membership_id = current_membership_id
                         AND membership_roles.active IS TRUE
                         AND permissions.code = 'employee:update:tenant'
                   ) THEN
                    RETURN FALSE;
                END IF;

                PERFORM profiles.id
                FROM public.employee_profiles AS profiles
                WHERE profiles.tenant_id = current_tenant_id
                  AND profiles.employee_id = requested_employee_id
                FOR UPDATE OF profiles;
                IF NOT FOUND THEN
                    RETURN FALSE;
                END IF;
                PERFORM pg_catalog.pg_advisory_xact_lock(
                    pg_catalog.hashtextextended(requested_employee_id::text, 11043)
                );
                RETURN TRUE;
            END
            $p11_employee_lifecycle_profile_lock$
            """
        )
    )
    _reset_function_acl(_LOCK_FUNCTION_SIGNATURE)
    op.execute(
        sa.text(
            f'GRANT EXECUTE ON FUNCTION {_LOCK_FUNCTION_SIGNATURE} TO "{TENANT_APPLICATION_ROLE}"'
        )
    )
    _create_active_employee_guard()
    _reset_function_acl(_ACTIVE_EMPLOYEE_GUARD_FUNCTION_SIGNATURE)
    op.execute(
        sa.text(
            f'CREATE TRIGGER "{_ACTIVE_EMPLOYEE_GUARD_TRIGGER}" '
            f'BEFORE INSERT ON "{_CHANGE_REQUESTS_TABLE}" '
            "FOR EACH ROW EXECUTE FUNCTION "
            f"{_ACTIVE_EMPLOYEE_GUARD_FUNCTION_SIGNATURE}"
        )
    )
    _transfer_function_ownership()


def _create_active_employee_guard() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION public.guard_employee_profile_change_request_active_employee()
            RETURNS trigger
            LANGUAGE plpgsql
            VOLATILE
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $p11_employee_profile_change_request_active_employee$
            BEGIN
                PERFORM pg_catalog.pg_advisory_xact_lock(
                    pg_catalog.hashtextextended(NEW.employee_id::text, 11043)
                );
                PERFORM employees.id
                FROM public.employees AS employees
                WHERE employees.tenant_id = NEW.tenant_id
                  AND employees.id = NEW.employee_id
                  AND employees.archived_at IS NULL;
                IF NOT FOUND THEN
                    RETURN NULL;
                END IF;
                RETURN NEW;
            END
            $p11_employee_profile_change_request_active_employee$
            """
        )
    )


def _reset_function_acl(signature: str) -> None:
    op.execute(sa.text(f"REVOKE ALL PRIVILEGES ON FUNCTION {signature} FROM PUBLIC"))
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
        _IDENTITY_PROJECTION_ROLE,
    ):
        op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON FUNCTION {signature} FROM "{role_name}"'))


def _assert_executor_owner_transfer_is_safe() -> None:
    op.execute(
        sa.text(
            f"""
            DO $p11_employee_lifecycle_owner_preflight$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_roles
                    WHERE rolname = '{_EXECUTOR_ROLE}'
                      AND rolcanlogin = false
                      AND rolsuper = false
                      AND rolcreatedb = false
                      AND rolcreaterole = false
                      AND rolinherit = false
                      AND rolbypassrls = false
                      AND rolreplication = false
                ) THEN
                    RAISE EXCEPTION
                        'P11 employee lifecycle owner preflight failed: '
                        'private owner is missing or unsafe';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_auth_members AS membership
                    JOIN pg_catalog.pg_roles AS owner_role
                      ON owner_role.oid = membership.member
                    WHERE owner_role.rolname = '{_EXECUTOR_ROLE}'
                ) OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_auth_members AS membership
                    JOIN pg_catalog.pg_roles AS owner_role
                      ON owner_role.oid = membership.roleid
                    JOIN pg_catalog.pg_roles AS member_role
                      ON member_role.oid = membership.member
                    WHERE owner_role.rolname = '{_EXECUTOR_ROLE}'
                      AND member_role.rolname <> current_user
                ) THEN
                    RAISE EXCEPTION
                        'P11 employee lifecycle owner preflight failed: '
                        'private owner membership is unsafe';
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_roles
                    WHERE rolname = current_user
                      AND (
                          rolsuper = true
                          OR pg_catalog.pg_has_role(
                              current_user, '{_EXECUTOR_ROLE}', 'SET'
                          )
                      )
                ) THEN
                    RAISE EXCEPTION
                        'P11 employee lifecycle owner preflight failed: '
                        'migration owner cannot SET private owner';
                END IF;

                IF NOT pg_catalog.has_schema_privilege(
                    current_user, 'public', 'CREATE'
                ) THEN
                    RAISE EXCEPTION
                        'P11 employee lifecycle owner preflight failed: '
                        'migration owner lacks public CREATE';
                END IF;

                IF pg_catalog.has_schema_privilege(
                    '{_EXECUTOR_ROLE}', 'public', 'CREATE'
                ) THEN
                    RAISE EXCEPTION
                        'P11 employee lifecycle owner preflight failed: '
                        'private owner has unexpected public CREATE';
                END IF;
            END
            $p11_employee_lifecycle_owner_preflight$
            """
        )
    )


def _transfer_function_ownership() -> None:
    # Ownership transfer requires the target role to CREATE in the containing schema.
    # Keep that capability inside one statement and explicitly revoke it on the error
    # path; Alembic's transaction-per-revision is an additional rollback boundary.
    op.execute(
        sa.text(
            f"""
            DO $p11_employee_lifecycle_owner_transfer$
            BEGIN
                EXECUTE 'GRANT CREATE ON SCHEMA public TO "{_EXECUTOR_ROLE}"';
                BEGIN
                    EXECUTE 'ALTER FUNCTION {_LOCK_FUNCTION_SIGNATURE} '
                            'OWNER TO "{_EXECUTOR_ROLE}"';
                    EXECUTE 'ALTER FUNCTION {_ACTIVE_EMPLOYEE_GUARD_FUNCTION_SIGNATURE} '
                            'OWNER TO "{_EXECUTOR_ROLE}"';
                EXCEPTION WHEN OTHERS THEN
                    EXECUTE 'REVOKE CREATE ON SCHEMA public FROM "{_EXECUTOR_ROLE}"';
                    RAISE;
                END;
                EXECUTE 'REVOKE CREATE ON SCHEMA public FROM "{_EXECUTOR_ROLE}"';
            END
            $p11_employee_lifecycle_owner_transfer$
            """
        )
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            f'DROP TRIGGER IF EXISTS "{_ACTIVE_EMPLOYEE_GUARD_TRIGGER}" '
            f'ON "{_CHANGE_REQUESTS_TABLE}"'
        )
    )
    op.execute(sa.text(f'SET LOCAL ROLE "{_EXECUTOR_ROLE}"'))
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_ACTIVE_EMPLOYEE_GUARD_FUNCTION_SIGNATURE}"))
    op.execute(
        sa.text(
            f"REVOKE EXECUTE ON FUNCTION {_LOCK_FUNCTION_SIGNATURE} "
            f'FROM "{TENANT_APPLICATION_ROLE}"'
        )
    )
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_LOCK_FUNCTION_SIGNATURE}"))
    op.execute(sa.text("RESET ROLE"))


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
