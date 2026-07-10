"""add P0F search and keyset query indexes

Revision ID: 0012_p0f_query_performance
Revises: 0011_p0e_concurrency_idempotency_archive
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_p0f_query_performance"
down_revision: str | None = "0011_p0e_concurrency_idempotency_archive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

    department_normalized = sa.Column(
        "department_normalized",
        sa.Text(),
        sa.Computed("lower(ltrim(rtrim(department)))", persisted=True),
        nullable=True,
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("employees") as batch_op:
            batch_op.add_column(department_normalized)
    else:
        op.add_column("employees", department_normalized)

    op.create_index(
        "ix_employees_employee_number_trgm",
        "employees",
        ["employee_number"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"employee_number": "gin_trgm_ops"},
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "ix_employees_email_trgm",
        "employees",
        ["email"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"email": "gin_trgm_ops"},
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "ix_employees_tenant_department_normalized",
        "employees",
        ["tenant_id", "department_normalized"],
        unique=False,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "ix_leave_requests_tenant_created_cursor",
        "leave_requests",
        [
            sa.column("tenant_id"),
            sa.desc(sa.column("created_at")),
            sa.asc(sa.column("start_date")),
            sa.asc(sa.column("id")),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_leave_requests_tenant_created_cursor",
        table_name="leave_requests",
    )
    op.drop_index(
        "ix_employees_tenant_department_normalized",
        table_name="employees",
    )
    op.drop_index("ix_employees_email_trgm", table_name="employees")
    op.drop_index("ix_employees_employee_number_trgm", table_name="employees")

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("employees") as batch_op:
            batch_op.drop_column("department_normalized")
    else:
        op.drop_column("employees", "department_normalized")

    # pg_trgm may be shared by other schemas/applications, so downgrade leaves it installed.
