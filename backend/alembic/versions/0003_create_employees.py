"""create employees table

Revision ID: 0003_create_employees
Revises: 0002_create_users
Create Date: 2026-07-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_create_employees"
down_revision: str | None = "0002_create_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_number", sa.String(length=64), nullable=False),
        sa.Column("first_name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("position", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("employment_start_date", sa.Date(), nullable=False),
        sa.Column("employment_end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status in ('active','on_leave','terminated')",
            name="ck_employees_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "employee_number",
            name="uq_employees_tenant_employee_number",
        ),
    )
    op.create_index("ix_employees_tenant_id", "employees", ["tenant_id"], unique=False)
    op.create_index(
        "ix_employees_tenant_status",
        "employees",
        ["tenant_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_employees_tenant_status", table_name="employees")
    op.drop_index("ix_employees_tenant_id", table_name="employees")
    op.drop_table("employees")
