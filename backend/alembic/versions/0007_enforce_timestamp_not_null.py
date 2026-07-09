"""enforce timestamp not null

Revision ID: 0007_enforce_timestamp_not_null
Revises: 0006_create_leave_balance_summaries
Create Date: 2026-07-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_enforce_timestamp_not_null"
down_revision: str | None = "0006_create_leave_balance_summaries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP_TABLES = (
    "tenants",
    "users",
    "employees",
    "leave_requests",
    "leave_balance_summaries",
)


def _current_timestamp_sql() -> str:
    if op.get_bind().dialect.name == "sqlite":
        return "CURRENT_TIMESTAMP"
    return "now()"


def _backfill_null_timestamps() -> None:
    current_timestamp = _current_timestamp_sql()
    for table_name in TIMESTAMP_TABLES:
        op.execute(
            sa.text(
                f"""
                update {table_name}
                set
                    created_at = coalesce(created_at, {current_timestamp}),
                    updated_at = coalesce(updated_at, {current_timestamp})
                where created_at is null or updated_at is null
                """
            )
        )


def _set_timestamp_nullability(*, nullable: bool) -> None:
    for table_name in TIMESTAMP_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "created_at",
                existing_type=sa.DateTime(timezone=True),
                existing_server_default=sa.text("now()"),
                nullable=nullable,
            )
            batch_op.alter_column(
                "updated_at",
                existing_type=sa.DateTime(timezone=True),
                existing_server_default=sa.text("now()"),
                nullable=nullable,
            )


def upgrade() -> None:
    _backfill_null_timestamps()
    _set_timestamp_nullability(nullable=False)


def downgrade() -> None:
    _set_timestamp_nullability(nullable=True)
