"""grant the tenant runtime permission-version insert required by user creation

Revision ID: 0021_f2f_user_insert_grant
Revises: 0020_f2e_audit_events
Create Date: 2026-07-12
"""

from collections.abc import Sequence

from alembic import op
from app.platform.db.rls_migration import (
    grant_column_privilege,
    revoke_column_privilege,
)
from app.platform.db.tenant_access import TENANT_APPLICATION_ROLE

revision: str = "0021_f2f_user_insert_grant"
down_revision: str | None = "0020_f2e_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        grant_column_privilege(
            op,
            table_name="users",
            role_name=TENANT_APPLICATION_ROLE,
            privilege="INSERT",
            column_names=("permission_version",),
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        revoke_column_privilege(
            op,
            table_name="users",
            role_name=TENANT_APPLICATION_ROLE,
            privilege="INSERT",
            column_names=("permission_version",),
        )


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
