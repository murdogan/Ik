"""add employee date order check

Revision ID: 0005_employee_date_order
Revises: 0004_create_leave_requests
Create Date: 2026-07-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_employee_date_order"
down_revision: str | None = "0004_create_leave_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("employees") as batch_op:
        batch_op.create_check_constraint(
            "ck_employees_date_order",
            "employment_end_date is null or employment_end_date >= employment_start_date",
        )


def downgrade() -> None:
    with op.batch_alter_table("employees") as batch_op:
        batch_op.drop_constraint("ck_employees_date_order", type_="check")
