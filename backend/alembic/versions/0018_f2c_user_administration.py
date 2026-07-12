"""add F2C tenant user administration indexes

Revision ID: 0018_f2c_user_administration
Revises: 0017_f2b_secure_sessions
Create Date: 2026-07-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018_f2c_user_administration"
down_revision: str | None = "0017_f2b_secure_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_users_tenant_created_at_id",
        "users",
        ["tenant_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_users_tenant_status_created_at_id",
        "users",
        ["tenant_id", "status", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_users_email_normalized_trgm",
        "users",
        ["email_normalized"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"email_normalized": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_users_full_name_trgm",
        "users",
        ["full_name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"full_name": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_users_full_name_trgm", table_name="users")
    op.drop_index("ix_users_email_normalized_trgm", table_name="users")
    op.drop_index("ix_users_tenant_status_created_at_id", table_name="users")
    op.drop_index("ix_users_tenant_created_at_id", table_name="users")
