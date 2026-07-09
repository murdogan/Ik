"""enforce employee lifecycle status dates

Revision ID: 0008_employee_lifecycle_status_dates
Revises: 0007_enforce_timestamp_not_null
Create Date: 2026-07-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_employee_lifecycle_status_dates"
down_revision: str | None = "0007_enforce_timestamp_not_null"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("employees") as batch_op:
        batch_op.create_check_constraint(
            "ck_employees_lifecycle_status_dates",
            (
                "(status = 'terminated' and employment_end_date is not null) "
                "or (status in ('active','on_leave') and employment_end_date is null)"
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("employees") as batch_op:
        batch_op.drop_constraint(
            "ck_employees_lifecycle_status_dates",
            type_="check",
        )
