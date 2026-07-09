"""create leave balance summaries table

Revision ID: 0006_create_leave_balance_summaries
Revises: 0005_employee_date_order
Create Date: 2026-07-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_create_leave_balance_summaries"
down_revision: str | None = "0005_employee_date_order"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "leave_balance_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leave_type", sa.String(length=64), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("opening_balance_days", sa.Float(), nullable=False),
        sa.Column("used_days", sa.Float(), nullable=False),
        sa.Column("planned_days", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "period_year >= 1900 and period_year <= 2200",
            name="ck_leave_balance_summaries_period_year",
        ),
        sa.CheckConstraint(
            "opening_balance_days >= 0",
            name="ck_leave_balance_summaries_opening_non_negative",
        ),
        sa.CheckConstraint(
            "used_days >= 0",
            name="ck_leave_balance_summaries_used_non_negative",
        ),
        sa.CheckConstraint(
            "planned_days >= 0",
            name="ck_leave_balance_summaries_planned_non_negative",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "employee_id",
            "leave_type",
            "period_year",
            name="uq_leave_balance_summaries_tenant_employee_type_period",
        ),
    )
    op.create_index(
        "ix_leave_balance_summaries_tenant_id",
        "leave_balance_summaries",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_leave_balance_summaries_tenant_employee_period",
        "leave_balance_summaries",
        ["tenant_id", "employee_id", "period_year"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_leave_balance_summaries_tenant_employee_period",
        table_name="leave_balance_summaries",
    )
    op.drop_index("ix_leave_balance_summaries_tenant_id", table_name="leave_balance_summaries")
    op.drop_table("leave_balance_summaries")
