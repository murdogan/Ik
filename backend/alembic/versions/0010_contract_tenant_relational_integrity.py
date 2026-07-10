"""contract tenant relational integrity constraints

Revision ID: 0010_contract_tenant_relational_integrity
Revises: 0009_expand_tenant_relational_integrity
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_contract_tenant_relational_integrity"
down_revision: str | None = "0009_expand_tenant_relational_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMPOSITE_FOREIGN_KEYS = (
    ("leave_requests", "fk_leave_requests_tenant_employee_id_employees"),
    ("leave_requests", "fk_leave_requests_tenant_requested_by_user_id_users"),
    ("leave_requests", "fk_leave_requests_tenant_decided_by_user_id_users"),
    (
        "leave_balance_summaries",
        "fk_leave_balance_summaries_tenant_employee_id_employees",
    ),
)

_LEGACY_FOREIGN_KEYS = (
    (
        "leave_requests",
        "leave_requests_employee_id_fkey",
        ("employee_id",),
        "employees",
        ("id",),
        "CASCADE",
    ),
    (
        "leave_requests",
        "leave_requests_requested_by_user_id_fkey",
        ("requested_by_user_id",),
        "users",
        ("id",),
        None,
    ),
    (
        "leave_requests",
        "leave_requests_decided_by_user_id_fkey",
        ("decided_by_user_id",),
        "users",
        ("id",),
        None,
    ),
    (
        "leave_balance_summaries",
        "leave_balance_summaries_employee_id_fkey",
        ("employee_id",),
        "employees",
        ("id",),
        "CASCADE",
    ),
)

_SQLITE_LEGACY_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
}


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _postgresql_contract()
    else:
        _portable_contract()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _postgresql_restore_legacy_foreign_keys()
    else:
        _portable_restore_legacy_foreign_keys()


def _postgresql_contract() -> None:
    for table_name, constraint_name in _COMPOSITE_FOREIGN_KEYS:
        op.execute(
            sa.text(
                f'ALTER TABLE "{table_name}" '
                f'VALIDATE CONSTRAINT "{constraint_name}"'
            )
        )

    for table_name, constraint_name, *_rest in _LEGACY_FOREIGN_KEYS:
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")


def _portable_contract() -> None:
    for table_name in ("leave_requests", "leave_balance_summaries"):
        with op.batch_alter_table(
            table_name,
            naming_convention=_SQLITE_LEGACY_NAMING_CONVENTION,
        ) as batch_op:
            for legacy_foreign_key in _LEGACY_FOREIGN_KEYS:
                if legacy_foreign_key[0] != table_name:
                    continue
                generated_name = _sqlite_legacy_constraint_name(legacy_foreign_key)
                batch_op.drop_constraint(generated_name, type_="foreignkey")


def _postgresql_restore_legacy_foreign_keys() -> None:
    for (
        table_name,
        constraint_name,
        local_columns,
        referred_table,
        remote_columns,
        ondelete,
    ) in _LEGACY_FOREIGN_KEYS:
        delete_clause = f" ON DELETE {ondelete}" if ondelete is not None else ""
        op.execute(
            sa.text(
                f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" '
                f"FOREIGN KEY ({_quoted_columns(local_columns)}) "
                f'REFERENCES "{referred_table}" ({_quoted_columns(remote_columns)})'
                f"{delete_clause} NOT VALID"
            )
        )
        op.execute(
            sa.text(
                f'ALTER TABLE "{table_name}" '
                f'VALIDATE CONSTRAINT "{constraint_name}"'
            )
        )


def _portable_restore_legacy_foreign_keys() -> None:
    for table_name in ("leave_requests", "leave_balance_summaries"):
        with op.batch_alter_table(table_name) as batch_op:
            for legacy_foreign_key in _LEGACY_FOREIGN_KEYS:
                (
                    foreign_key_table,
                    _constraint_name,
                    local_columns,
                    referred_table,
                    remote_columns,
                    ondelete,
                ) = legacy_foreign_key
                if foreign_key_table != table_name:
                    continue
                batch_op.create_foreign_key(
                    _sqlite_legacy_constraint_name(legacy_foreign_key),
                    referred_table,
                    list(local_columns),
                    list(remote_columns),
                    ondelete=ondelete,
                )


def _sqlite_legacy_constraint_name(legacy_foreign_key: tuple[object, ...]) -> str:
    table_name = str(legacy_foreign_key[0])
    local_columns = legacy_foreign_key[2]
    referred_table = str(legacy_foreign_key[3])
    assert isinstance(local_columns, tuple)
    return f"fk_{table_name}_{local_columns[0]}_{referred_table}"


def _quoted_columns(columns: tuple[str, ...]) -> str:
    return ", ".join(f'"{column}"' for column in columns)
