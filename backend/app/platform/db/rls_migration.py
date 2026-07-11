"""Stable Alembic helpers for PostgreSQL role and row-security migrations.

The helpers deliberately accept explicit identifiers and privilege lists.  Individual revisions
must freeze their table inventory instead of deriving it from live ORM metadata, otherwise an old
migration would silently change when a future model is added.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic.operations import Operations

TENANT_SETTING_SQL = "nullif(current_setting('app.tenant_id', true), '')::uuid"

_IDENTIFIER_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
_ROLE_SECURITY_ATTRIBUTES = (
    "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
    "NOINHERIT NOBYPASSRLS NOREPLICATION"
)
_ALLOWED_TABLE_PRIVILEGES = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})


def ensure_capability_role(operations: Operations, role_name: str) -> None:
    """Create or harden a cluster role without relying on ``CREATE ROLE IF NOT EXISTS``."""

    quoted_role = _quoted_identifier(role_name)
    role_literal = role_name.replace("'", "''")
    operations.execute(
        sa.text(
            f"""
            DO $wealthy_falcon_capability_role$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = '{role_literal}'
                ) THEN
                    CREATE ROLE {quoted_role} WITH {_ROLE_SECURITY_ATTRIBUTES};
                ELSE
                    ALTER ROLE {quoted_role} WITH {_ROLE_SECURITY_ATTRIBUTES};
                END IF;
            END
            $wealthy_falcon_capability_role$
            """
        )
    )


def assert_capability_role_has_no_parent_memberships(
    operations: Operations,
    role_name: str,
) -> None:
    """Fail before grants if a reused capability could assume a broader parent role."""

    role_literal = role_name.replace("'", "''")
    operations.execute(
        sa.text(
            f"""
            DO $wealthy_falcon_role_membership_preflight$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_auth_members membership
                    JOIN pg_catalog.pg_roles member_role
                      ON member_role.oid = membership.member
                    WHERE member_role.rolname = '{role_literal}'
                ) THEN
                    RAISE EXCEPTION
                        'F1C role membership preflight failed: capability role {role_literal} '
                        'must not be a member of another role';
                END IF;
            END
            $wealthy_falcon_role_membership_preflight$
            """
        )
    )


def grant_schema_usage(
    operations: Operations,
    *,
    schema_name: str,
    role_name: str,
) -> None:
    operations.execute(
        sa.text(
            f"GRANT USAGE ON SCHEMA {_quoted_identifier(schema_name)} "
            f"TO {_quoted_identifier(role_name)}"
        )
    )


def revoke_all_schema_privileges(
    operations: Operations,
    *,
    schema_name: str,
    role_name: str,
) -> None:
    """Reset stale direct schema grants before applying a capability's exact contract."""

    operations.execute(
        sa.text(
            f"REVOKE ALL PRIVILEGES ON SCHEMA {_quoted_identifier(schema_name)} "
            f"FROM {_quoted_identifier(role_name)}"
        )
    )


def revoke_schema_usage(
    operations: Operations,
    *,
    schema_name: str,
    role_name: str,
) -> None:
    operations.execute(
        sa.text(
            f"REVOKE USAGE ON SCHEMA {_quoted_identifier(schema_name)} "
            f"FROM {_quoted_identifier(role_name)}"
        )
    )


def grant_table_privileges(
    operations: Operations,
    *,
    table_name: str,
    role_name: str,
    privileges: Sequence[str],
) -> None:
    rendered_privileges = _render_privileges(privileges)
    operations.execute(
        sa.text(
            f"GRANT {rendered_privileges} ON TABLE {_quoted_identifier(table_name)} "
            f"TO {_quoted_identifier(role_name)}"
        )
    )


def grant_column_privilege(
    operations: Operations,
    *,
    table_name: str,
    role_name: str,
    privilege: str,
    column_names: Sequence[str],
) -> None:
    rendered_privilege = _render_column_privilege(privilege)
    rendered_columns = _render_columns(column_names)
    operations.execute(
        sa.text(
            f"GRANT {rendered_privilege} ({rendered_columns}) "
            f"ON TABLE {_quoted_identifier(table_name)} "
            f"TO {_quoted_identifier(role_name)}"
        )
    )


def revoke_all_table_privileges(
    operations: Operations,
    *,
    table_name: str,
    role_name: str,
) -> None:
    """Reset stale direct table grants before applying a capability's exact contract."""

    operations.execute(
        sa.text(
            f"REVOKE ALL PRIVILEGES ON TABLE {_quoted_identifier(table_name)} "
            f"FROM {_quoted_identifier(role_name)}"
        )
    )


def revoke_all_column_privileges(
    operations: Operations,
    *,
    table_name: str,
    role_name: str,
    column_names: Sequence[str],
) -> None:
    """Reset stale direct column grants before applying an exact capability contract."""

    rendered_columns = _render_columns(column_names)
    operations.execute(
        sa.text(
            f"REVOKE ALL PRIVILEGES ({rendered_columns}) "
            f"ON TABLE {_quoted_identifier(table_name)} "
            f"FROM {_quoted_identifier(role_name)}"
        )
    )


def revoke_table_privileges(
    operations: Operations,
    *,
    table_name: str,
    role_name: str,
    privileges: Sequence[str],
) -> None:
    rendered_privileges = _render_privileges(privileges)
    operations.execute(
        sa.text(
            f"REVOKE {rendered_privileges} ON TABLE {_quoted_identifier(table_name)} "
            f"FROM {_quoted_identifier(role_name)}"
        )
    )


def revoke_column_privilege(
    operations: Operations,
    *,
    table_name: str,
    role_name: str,
    privilege: str,
    column_names: Sequence[str],
) -> None:
    rendered_privilege = _render_column_privilege(privilege)
    rendered_columns = _render_columns(column_names)
    operations.execute(
        sa.text(
            f"REVOKE {rendered_privilege} ({rendered_columns}) "
            f"ON TABLE {_quoted_identifier(table_name)} "
            f"FROM {_quoted_identifier(role_name)}"
        )
    )


def enable_forced_row_security(operations: Operations, *, table_name: str) -> None:
    quoted_table = _quoted_identifier(table_name)
    operations.execute(sa.text(f"ALTER TABLE {quoted_table} ENABLE ROW LEVEL SECURITY"))
    operations.execute(sa.text(f"ALTER TABLE {quoted_table} FORCE ROW LEVEL SECURITY"))


def disable_forced_row_security(operations: Operations, *, table_name: str) -> None:
    quoted_table = _quoted_identifier(table_name)
    operations.execute(sa.text(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY"))
    operations.execute(sa.text(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY"))


def create_tenant_isolation_policy(
    operations: Operations,
    *,
    table_name: str,
    policy_name: str,
    role_name: str,
    tenant_column: str = "tenant_id",
) -> None:
    """Create a role-scoped read/write policy that denies an absent tenant setting."""

    predicate = f"{_quoted_identifier(tenant_column)} = {TENANT_SETTING_SQL}"
    operations.execute(
        sa.text(
            f"CREATE POLICY {_quoted_identifier(policy_name)} "
            f"ON {_quoted_identifier(table_name)} AS PERMISSIVE FOR ALL "
            f"TO {_quoted_identifier(role_name)} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    )


def create_unrestricted_role_policy(
    operations: Operations,
    *,
    table_name: str,
    policy_name: str,
    role_name: str,
) -> None:
    """Create an explicit all-row policy for a narrowly granted capability role."""

    operations.execute(
        sa.text(
            f"CREATE POLICY {_quoted_identifier(policy_name)} "
            f"ON {_quoted_identifier(table_name)} AS PERMISSIVE FOR ALL "
            f"TO {_quoted_identifier(role_name)} USING (true) WITH CHECK (true)"
        )
    )


def create_unrestricted_insert_policy(
    operations: Operations,
    *,
    table_name: str,
    policy_name: str,
    role_name: str,
) -> None:
    """Allow a narrowly granted role to insert rows without read/update visibility."""

    operations.execute(
        sa.text(
            f"CREATE POLICY {_quoted_identifier(policy_name)} "
            f"ON {_quoted_identifier(table_name)} AS PERMISSIVE FOR INSERT "
            f"TO {_quoted_identifier(role_name)} WITH CHECK (true)"
        )
    )


def drop_policy(
    operations: Operations,
    *,
    table_name: str,
    policy_name: str,
) -> None:
    operations.execute(
        sa.text(
            f"DROP POLICY IF EXISTS {_quoted_identifier(policy_name)} "
            f"ON {_quoted_identifier(table_name)}"
        )
    )


def _quoted_identifier(value: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"Unsafe PostgreSQL identifier: {value!r}")
    return f'"{value}"'


def _render_privileges(privileges: Sequence[str]) -> str:
    if not privileges:
        raise ValueError("At least one table privilege is required")

    normalized = tuple(privilege.upper() for privilege in privileges)
    if len(set(normalized)) != len(normalized):
        raise ValueError("Table privileges must not contain duplicates")
    invalid = set(normalized) - _ALLOWED_TABLE_PRIVILEGES
    if invalid:
        raise ValueError(f"Unsupported table privileges: {sorted(invalid)}")
    return ", ".join(normalized)


def _render_column_privilege(privilege: str) -> str:
    normalized = privilege.upper()
    if normalized not in {"SELECT", "INSERT", "UPDATE", "REFERENCES"}:
        raise ValueError(f"Unsupported column privilege: {privilege!r}")
    return normalized


def _render_columns(column_names: Sequence[str]) -> str:
    if not column_names:
        raise ValueError("At least one column is required")
    if len(set(column_names)) != len(column_names):
        raise ValueError("Column names must not contain duplicates")
    return ", ".join(_quoted_identifier(column_name) for column_name in column_names)


__all__ = [
    "TENANT_SETTING_SQL",
    "assert_capability_role_has_no_parent_memberships",
    "create_tenant_isolation_policy",
    "create_unrestricted_insert_policy",
    "create_unrestricted_role_policy",
    "disable_forced_row_security",
    "drop_policy",
    "enable_forced_row_security",
    "ensure_capability_role",
    "grant_column_privilege",
    "grant_schema_usage",
    "grant_table_privileges",
    "revoke_all_schema_privileges",
    "revoke_all_column_privileges",
    "revoke_all_table_privileges",
    "revoke_column_privilege",
    "revoke_schema_usage",
    "revoke_table_privileges",
]
