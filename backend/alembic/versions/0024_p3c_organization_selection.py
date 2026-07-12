"""bind sessions to memberships and enable one-use organization selection

Revision ID: 0024_p3c_organization_selection
Revises: 0023_p3b_email_first_login
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    disable_forced_row_security,
    drop_policy,
    enable_forced_row_security,
    grant_column_privilege,
    grant_table_privileges,
    revoke_column_privilege,
    revoke_table_privileges,
)
from app.platform.db.tenant_access import AUTHENTICATION_APPLICATION_ROLE
from sqlalchemy.dialects import postgresql

revision: str = "0024_p3c_organization_selection"
down_revision: str | None = "0023_p3b_email_first_login"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FAMILIES_TABLE = "refresh_session_families"
_MEMBERSHIPS_TABLE = "tenant_memberships"
_TRANSACTIONS_TABLE = "organization_selection_transactions"
_CHOICES_TABLE = "organization_selection_choices"
_FAMILY_MEMBERSHIP_FK = "fk_refresh_session_families_tenant_membership_id_memberships"
_FAMILY_MEMBERSHIP_INDEX = "ix_refresh_session_families_tenant_membership_expires_at"
_TRANSACTION_SELECT_POLICY = "authentication_selection_transaction_select"
_TRANSACTION_UPDATE_POLICY = "authentication_selection_transaction_consume"
_CHOICE_SELECT_POLICY = "authentication_selection_choice_select"


def upgrade() -> None:
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "postgresql":
        # The normal runtime role must never bypass either table. The transactional migration
        # owner temporarily needs the full expand/backfill view before FORCE RLS is restored.
        disable_forced_row_security(op, table_name=_FAMILIES_TABLE)
        disable_forced_row_security(op, table_name=_MEMBERSHIPS_TABLE)
    op.add_column(
        _FAMILIES_TABLE,
        sa.Column(
            "membership_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            "update refresh_session_families as families "
            "set membership_id = ("
            "select memberships.id from tenant_memberships as memberships "
            "where memberships.tenant_id = families.tenant_id "
            "and memberships.legacy_user_id = families.user_id"
            ") where families.membership_id is null"
        )
    )

    if dialect_name == "postgresql":
        op.execute(
            sa.text(
                """
                DO $p3c_session_membership_backfill$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM refresh_session_families
                        WHERE membership_id IS NULL
                    ) THEN
                        RAISE EXCEPTION
                            'P3C cannot bind an existing refresh family to a membership';
                    END IF;
                END
                $p3c_session_membership_backfill$
                """
            )
        )
        op.alter_column(
            _FAMILIES_TABLE,
            "membership_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=False,
        )
        op.create_foreign_key(
            _FAMILY_MEMBERSHIP_FK,
            _FAMILIES_TABLE,
            _MEMBERSHIPS_TABLE,
            ["tenant_id", "membership_id"],
            ["tenant_id", "id"],
            ondelete="CASCADE",
        )
    else:
        with op.batch_alter_table(_FAMILIES_TABLE, recreate="always") as batch_op:
            batch_op.alter_column(
                "membership_id",
                existing_type=postgresql.UUID(as_uuid=True),
                nullable=False,
            )
            batch_op.create_foreign_key(
                _FAMILY_MEMBERSHIP_FK,
                _MEMBERSHIPS_TABLE,
                ["tenant_id", "membership_id"],
                ["tenant_id", "id"],
                ondelete="CASCADE",
            )

    op.create_index(
        _FAMILY_MEMBERSHIP_INDEX,
        _FAMILIES_TABLE,
        ["tenant_id", "membership_id", "expires_at"],
    )
    if dialect_name == "postgresql":
        enable_forced_row_security(op, table_name=_MEMBERSHIPS_TABLE)
        enable_forced_row_security(op, table_name=_FAMILIES_TABLE)
        _enable_selection_consumption()


def downgrade() -> None:
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "postgresql":
        _disable_selection_consumption()
    op.drop_index(_FAMILY_MEMBERSHIP_INDEX, table_name=_FAMILIES_TABLE)
    if dialect_name == "postgresql":
        op.drop_constraint(
            _FAMILY_MEMBERSHIP_FK,
            _FAMILIES_TABLE,
            type_="foreignkey",
        )
        op.drop_column(_FAMILIES_TABLE, "membership_id")
    else:
        with op.batch_alter_table(_FAMILIES_TABLE, recreate="always") as batch_op:
            batch_op.drop_constraint(_FAMILY_MEMBERSHIP_FK, type_="foreignkey")
            batch_op.drop_column("membership_id")


def _enable_selection_consumption() -> None:
    op.execute(
        sa.text(
            f'CREATE POLICY "{_TRANSACTION_SELECT_POLICY}" '
            f'ON "{_TRANSACTIONS_TABLE}" AS PERMISSIVE FOR SELECT '
            f'TO "{AUTHENTICATION_APPLICATION_ROLE}" USING (true)'
        )
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_TRANSACTION_UPDATE_POLICY}" '
            f'ON "{_TRANSACTIONS_TABLE}" AS PERMISSIVE FOR UPDATE '
            f'TO "{AUTHENTICATION_APPLICATION_ROLE}" '
            "USING (consumed_at is null) WITH CHECK (consumed_at is not null)"
        )
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_CHOICE_SELECT_POLICY}" ON "{_CHOICES_TABLE}" '
            f'AS PERMISSIVE FOR SELECT TO "{AUTHENTICATION_APPLICATION_ROLE}" '
            "USING (true)"
        )
    )
    grant_table_privileges(
        op,
        table_name=_TRANSACTIONS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privileges=("SELECT",),
    )
    grant_column_privilege(
        op,
        table_name=_TRANSACTIONS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=("consumed_at", "updated_at"),
    )
    grant_table_privileges(
        op,
        table_name=_CHOICES_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privileges=("SELECT",),
    )


def _disable_selection_consumption() -> None:
    revoke_table_privileges(
        op,
        table_name=_CHOICES_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privileges=("SELECT",),
    )
    revoke_column_privilege(
        op,
        table_name=_TRANSACTIONS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=("consumed_at", "updated_at"),
    )
    revoke_table_privileges(
        op,
        table_name=_TRANSACTIONS_TABLE,
        role_name=AUTHENTICATION_APPLICATION_ROLE,
        privileges=("SELECT",),
    )
    for table_name, policy_name in (
        (_CHOICES_TABLE, _CHOICE_SELECT_POLICY),
        (_TRANSACTIONS_TABLE, _TRANSACTION_UPDATE_POLICY),
        (_TRANSACTIONS_TABLE, _TRANSACTION_SELECT_POLICY),
    ):
        drop_policy(op, table_name=table_name, policy_name=policy_name)
