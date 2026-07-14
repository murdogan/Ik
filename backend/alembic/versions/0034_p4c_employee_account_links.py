"""add canonical P4C employee-to-membership account links

Revision ID: 0034_p4c_employee_account_links
Revises: 0033_p4b_employee_profiles
Create Date: 2026-07-14
"""

from __future__ import annotations

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
    revoke_column_privilege,
    revoke_table_privileges,
)
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy.dialects import postgresql

revision: str = "0034_p4c_employee_account_links"
down_revision: str | None = "0033_p4b_employee_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LINKS_TABLE = "employee_account_links"
_TENANT_POLICY = "tenant_isolation_app"
_ELIGIBILITY_FUNCTION = "is_current_tenant_membership_link_eligible"
_ELIGIBILITY_FUNCTION_SIGNATURE = f"public.{_ELIGIBILITY_FUNCTION}(uuid)"
_ELIGIBILITY_OWNER_ROLE = "wealthy_falcon_identity_recovery"
_IDENTITY_PROJECTION_ROLE = "wealthy_falcon_identity_projection"
_UUID = postgresql.UUID(as_uuid=True)

_TABLE_COLUMNS = (
    "id",
    "tenant_id",
    "employee_id",
    "membership_id",
    "version",
    "created_at",
    "updated_at",
)
_UPDATE_COLUMNS = ("membership_id", "version", "updated_at")


def upgrade() -> None:
    _create_links_table()
    if op.get_bind().dialect.name == "postgresql":
        _reset_postgresql_acl()
        enable_forced_row_security(op, table_name=_LINKS_TABLE)
        create_tenant_isolation_policy(
            op,
            table_name=_LINKS_TABLE,
            policy_name=_TENANT_POLICY,
            role_name=TENANT_APPLICATION_ROLE,
        )
        grant_table_privileges(
            op,
            table_name=_LINKS_TABLE,
            role_name=TENANT_APPLICATION_ROLE,
            privileges=("SELECT", "INSERT", "DELETE"),
        )
        grant_column_privilege(
            op,
            table_name=_LINKS_TABLE,
            role_name=TENANT_APPLICATION_ROLE,
            privilege="UPDATE",
            column_names=_UPDATE_COLUMNS,
        )
        _create_membership_eligibility_function()


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        # The migration owner is subject to FORCE RLS. Transaction-per-revision restores FORCE if
        # the destructive downgrade preflight below refuses a non-empty current-link table.
        disable_forced_row_security(op, table_name=_LINKS_TABLE)

    _assert_downgrade_is_safe()

    if is_postgresql:
        _drop_membership_eligibility_function()
        revoke_column_privilege(
            op,
            table_name=_LINKS_TABLE,
            role_name=TENANT_APPLICATION_ROLE,
            privilege="UPDATE",
            column_names=_UPDATE_COLUMNS,
        )
        revoke_table_privileges(
            op,
            table_name=_LINKS_TABLE,
            role_name=TENANT_APPLICATION_ROLE,
            privileges=("SELECT", "INSERT", "DELETE"),
        )
        drop_policy(
            op,
            table_name=_LINKS_TABLE,
            policy_name=_TENANT_POLICY,
        )

    op.drop_table(_LINKS_TABLE)


def _create_links_table() -> None:
    op.create_table(
        _LINKS_TABLE,
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("employee_id", _UUID, nullable=False),
        sa.Column("membership_id", _UUID, nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
            "version > 0",
            name="ck_employee_account_links_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_employee_account_links_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_employee_account_links_tenant_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            name="fk_employee_account_links_tenant_membership_id_memberships",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_employee_account_links"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_employee_account_links_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "employee_id",
            name="uq_employee_account_links_tenant_employee_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "membership_id",
            name="uq_employee_account_links_tenant_membership_id",
        ),
    )


def _assert_downgrade_is_safe() -> None:
    link_count_sql = f"select count(*) from {_LINKS_TABLE}"
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $p4c_employee_account_link_downgrade_preflight$
                DECLARE
                    current_link_count bigint;
                BEGIN
                    current_link_count := ({link_count_sql});
                    IF current_link_count > 0 THEN
                        RAISE EXCEPTION
                            'P4C employee account link downgrade refused: current_links=%',
                            current_link_count;
                    END IF;
                END
                $p4c_employee_account_link_downgrade_preflight$
                """
            )
        )
        return

    current_link_count = int(op.get_bind().scalar(sa.text(link_count_sql)) or 0)
    if current_link_count:
        raise RuntimeError(
            "P4C employee account link downgrade refused: "
            f"current_links={current_link_count}"
        )


def _reset_postgresql_acl() -> None:
    quoted_columns = ", ".join(f'"{column_name}"' for column_name in _TABLE_COLUMNS)
    op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{_LINKS_TABLE}" FROM PUBLIC'))
    op.execute(
        sa.text(
            f'REVOKE ALL PRIVILEGES ({quoted_columns}) '
            f'ON TABLE "{_LINKS_TABLE}" FROM PUBLIC'
        )
    )
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
        _IDENTITY_PROJECTION_ROLE,
        _ELIGIBILITY_OWNER_ROLE,
    ):
        revoke_all_table_privileges(
            op,
            table_name=_LINKS_TABLE,
            role_name=role_name,
        )
        revoke_all_column_privileges(
            op,
            table_name=_LINKS_TABLE,
            role_name=role_name,
            column_names=_TABLE_COLUMNS,
        )


def _assert_eligibility_owner_is_private() -> None:
    op.execute(
        sa.text(
            f"""
            DO $p4c_employee_link_owner_preflight$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_roles
                    WHERE rolname = '{_ELIGIBILITY_OWNER_ROLE}'
                      AND rolcanlogin = false
                      AND rolsuper = false
                      AND rolcreatedb = false
                      AND rolcreaterole = false
                      AND rolinherit = false
                      AND rolbypassrls = false
                      AND rolreplication = false
                ) THEN
                    RAISE EXCEPTION
                        'P4C employee link owner preflight failed: '
                        'private owner is missing or unsafe';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_auth_members AS membership
                    JOIN pg_catalog.pg_roles AS owner_role
                      ON owner_role.oid = membership.member
                    WHERE owner_role.rolname = '{_ELIGIBILITY_OWNER_ROLE}'
                ) OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_auth_members AS membership
                    JOIN pg_catalog.pg_roles AS owner_role
                      ON owner_role.oid = membership.roleid
                    JOIN pg_catalog.pg_roles AS member_role
                      ON member_role.oid = membership.member
                    WHERE owner_role.rolname = '{_ELIGIBILITY_OWNER_ROLE}'
                      AND member_role.rolname <> current_user
                ) THEN
                    RAISE EXCEPTION
                        'P4C employee link owner preflight failed: '
                        'private owner membership is unsafe';
                END IF;
            END
            $p4c_employee_link_owner_preflight$
            """
        )
    )


def _create_membership_eligibility_function() -> None:
    _assert_eligibility_owner_is_private()
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_ELIGIBILITY_FUNCTION}(
                requested_membership_id uuid
            ) RETURNS boolean
            LANGUAGE sql
            STABLE
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $p4c_membership_link_eligibility$
                SELECT EXISTS (
                    SELECT 1
                    FROM public.tenant_memberships AS membership
                    JOIN public.users AS legacy_user
                      ON legacy_user.tenant_id = membership.tenant_id
                     AND legacy_user.id = membership.legacy_user_id
                    JOIN public.identities AS canonical_identity
                      ON canonical_identity.id = membership.identity_id
                    WHERE membership.tenant_id = nullif(
                              current_setting('app.tenant_id', true), ''
                          )::uuid
                      AND membership.id = requested_membership_id
                      AND membership.status = 'active'
                      AND legacy_user.status = 'active'
                      AND canonical_identity.status = 'active'
                      AND membership.permission_version = legacy_user.permission_version
                )
            $p4c_membership_link_eligibility$
            """
        )
    )
    op.execute(
        sa.text(
            f'ALTER FUNCTION {_ELIGIBILITY_FUNCTION_SIGNATURE} '
            f'OWNER TO "{_ELIGIBILITY_OWNER_ROLE}"'
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL PRIVILEGES ON FUNCTION {_ELIGIBILITY_FUNCTION_SIGNATURE} "
            "FROM PUBLIC"
        )
    )
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
        _IDENTITY_PROJECTION_ROLE,
    ):
        op.execute(
            sa.text(
                f"REVOKE ALL PRIVILEGES ON FUNCTION {_ELIGIBILITY_FUNCTION_SIGNATURE} "
                f'FROM "{role_name}"'
            )
        )
    op.execute(
        sa.text(
            f"GRANT EXECUTE ON FUNCTION {_ELIGIBILITY_FUNCTION_SIGNATURE} "
            f'TO "{TENANT_APPLICATION_ROLE}"'
        )
    )


def _drop_membership_eligibility_function() -> None:
    op.execute(
        sa.text(
            f"REVOKE EXECUTE ON FUNCTION {_ELIGIBILITY_FUNCTION_SIGNATURE} "
            f'FROM "{TENANT_APPLICATION_ROLE}"'
        )
    )
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_ELIGIBILITY_FUNCTION_SIGNATURE}"))


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
