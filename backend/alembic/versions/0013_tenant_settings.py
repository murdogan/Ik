"""add typed tenant settings

Revision ID: 0013_tenant_settings
Revises: 0012_p0f_query_performance
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_tenant_settings"
down_revision: str | None = "0012_p0f_query_performance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_settings",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "week_start_day",
            sa.String(length=16),
            server_default=sa.text("'monday'"),
            nullable=False,
        ),
        sa.Column(
            "date_format",
            sa.String(length=16),
            server_default=sa.text("'DD.MM.YYYY'"),
            nullable=False,
        ),
        sa.Column(
            "time_format",
            sa.String(length=8),
            server_default=sa.text("'24h'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "week_start_day in ('monday','sunday')",
            name="ck_tenant_settings_week_start_day",
        ),
        sa.CheckConstraint(
            "date_format in ('DD.MM.YYYY','MM/DD/YYYY','YYYY-MM-DD')",
            name="ck_tenant_settings_date_format",
        ),
        sa.CheckConstraint(
            "time_format in ('24h','12h')",
            name="ck_tenant_settings_time_format",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_settings_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", name="pk_tenant_settings"),
    )
    op.execute(
        sa.text(
            "insert into tenant_settings ("
            "tenant_id, week_start_day, date_format, time_format, created_at, updated_at"
            ") select id, 'monday', 'DD.MM.YYYY', '24h', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP from tenants"
        )
    )


def downgrade() -> None:
    _assert_downgrade_is_safe()
    op.drop_table("tenant_settings")


def _assert_downgrade_is_safe() -> None:
    custom_settings_predicate = (
        "week_start_day <> 'monday' or "
        "date_format <> 'DD.MM.YYYY' or "
        "time_format <> '24h'"
    )
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $f1a_downgrade_preflight$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM tenant_settings
                        WHERE {custom_settings_predicate}
                    ) THEN
                        RAISE EXCEPTION
                            'F1A downgrade preflight failed; export or restore default tenant '
                            'settings before retrying';
                    END IF;
                END
                $f1a_downgrade_preflight$
                """
            )
        )
        return

    custom_settings_count = int(
        op.get_bind().scalar(
            sa.text(
                "select count(*) from tenant_settings where "
                f"{custom_settings_predicate}"
            )
        )
        or 0
    )
    if custom_settings_count == 0:
        return

    raise RuntimeError(
        "F1A downgrade preflight failed; export or restore default tenant settings "
        f"before retrying: custom_tenant_settings={custom_settings_count}"
    )
