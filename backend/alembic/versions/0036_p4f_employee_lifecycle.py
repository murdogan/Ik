"""Add the persisted P4F termination reason code.

Revision ID: 0036_p4f_employee_lifecycle
Revises: 0035_p4e_employee_change_requests
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0036_p4f_employee_lifecycle"
down_revision: str | None = "0035_p4e_employee_change_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("termination_reason", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "ck_employees_termination_reason",
        "employees",
        "termination_reason is null or ("
        "status = 'terminated' and termination_reason in "
        "('resignation','dismissal','retirement','contract_end','other')"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_employees_termination_reason",
        "employees",
        type_="check",
    )
    op.drop_column("employees", "termination_reason")
