"""create leave requests table

Revision ID: 0004_create_leave_requests
Revises: 0003_create_employees
Create Date: 2026-07-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_create_leave_requests"
down_revision: str | None = "0003_create_employees"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "leave_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leave_type", sa.String(length=64), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status in ('pending','approved','rejected','cancelled')",
            name="ck_leave_requests_status",
        ),
        sa.CheckConstraint("end_date >= start_date", name="ck_leave_requests_date_order"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_leave_requests_tenant_id", "leave_requests", ["tenant_id"], unique=False)
    op.create_index(
        "ix_leave_requests_tenant_employee_start_date",
        "leave_requests",
        ["tenant_id", "employee_id", "start_date"],
        unique=False,
    )
    op.create_index(
        "ix_leave_requests_tenant_status_created_at",
        "leave_requests",
        ["tenant_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_leave_requests_tenant_status_created_at", table_name="leave_requests")
    op.drop_index("ix_leave_requests_tenant_employee_start_date", table_name="leave_requests")
    op.drop_index("ix_leave_requests_tenant_id", table_name="leave_requests")
    op.drop_table("leave_requests")
