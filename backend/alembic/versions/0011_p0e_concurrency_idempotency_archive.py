"""harden concurrency, idempotency, and employee archive semantics

Revision ID: 0011_p0e_concurrency_idempotency_archive
Revises: 0010_contract_tenant_relational_integrity
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_p0e_concurrency_idempotency_archive"
down_revision: str | None = "0010_contract_tenant_relational_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMPLOYEE_HISTORY_FOREIGN_KEYS = (
    (
        "leave_requests",
        "fk_leave_requests_tenant_employee_id_employees",
        ("tenant_id", "employee_id"),
    ),
    (
        "leave_balance_summaries",
        "fk_leave_balance_summaries_tenant_employee_id_employees",
        ("tenant_id", "employee_id"),
    ),
)


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_employees_tenant_archived_at",
        "employees",
        ["tenant_id", "archived_at"],
        unique=False,
    )
    op.create_table(
        "command_idempotency",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("command_name", sa.String(length=96), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(resource_id is null and response_payload is null and completed_at is null) "
            "or (resource_id is not null and response_payload is not null "
            "and completed_at is not null)",
            name="ck_command_idempotency_completion",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_command_idempotency_tenant_key",
        ),
    )
    op.create_index(
        "ix_command_idempotency_tenant_id",
        "command_idempotency",
        ["tenant_id"],
        unique=False,
    )
    _replace_employee_history_foreign_keys(ondelete="RESTRICT")


def downgrade() -> None:
    _assert_downgrade_is_safe()
    _replace_employee_history_foreign_keys(ondelete="CASCADE")
    op.drop_index(
        "ix_command_idempotency_tenant_id",
        table_name="command_idempotency",
    )
    op.drop_table("command_idempotency")
    op.drop_index("ix_employees_tenant_archived_at", table_name="employees")
    op.drop_column("employees", "archived_at")


def _assert_downgrade_is_safe() -> None:
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                """
                DO $p0e_downgrade_preflight$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM employees WHERE archived_at IS NOT NULL
                    ) OR EXISTS (
                        SELECT 1 FROM command_idempotency
                    ) THEN
                        RAISE EXCEPTION
                            'P0E downgrade preflight failed; export/remediate archived '
                            'employees and idempotency receipts before retrying';
                    END IF;
                END
                $p0e_downgrade_preflight$
                """
            )
        )
        return

    connection = op.get_bind()
    archived_employee_count = int(
        connection.scalar(
            sa.text("select count(*) from employees where archived_at is not null")
        )
        or 0
    )
    receipt_count = int(
        connection.scalar(sa.text("select count(*) from command_idempotency")) or 0
    )
    if archived_employee_count == 0 and receipt_count == 0:
        return

    raise RuntimeError(
        "P0E downgrade preflight failed; export/remediate retained state before retrying: "
        f"archived_employees={archived_employee_count}, "
        f"command_idempotency={receipt_count}"
    )


def _replace_employee_history_foreign_keys(*, ondelete: str) -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table_name, constraint_name, local_columns in _EMPLOYEE_HISTORY_FOREIGN_KEYS:
            op.drop_constraint(constraint_name, table_name, type_="foreignkey")
            op.create_foreign_key(
                constraint_name,
                table_name,
                "employees",
                list(local_columns),
                ["tenant_id", "id"],
                ondelete=ondelete,
            )
        return

    for table_name, constraint_name, local_columns in _EMPLOYEE_HISTORY_FOREIGN_KEYS:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="foreignkey")
            batch_op.create_foreign_key(
                constraint_name,
                "employees",
                list(local_columns),
                ["tenant_id", "id"],
                ondelete=ondelete,
            )
