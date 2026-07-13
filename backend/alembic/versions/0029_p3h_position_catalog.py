"""add P3H tenant position catalog

Revision ID: 0029_p3h_position_catalog
Revises: 0028_p3g_department_hierarchy
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    create_tenant_isolation_policy,
    disable_forced_row_security,
    drop_policy,
    enable_forced_row_security,
    grant_column_privilege,
    grant_table_privileges,
    revoke_all_column_privileges,
    revoke_all_table_privileges,
    revoke_column_privilege,
    revoke_table_privileges,
)
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy.dialects import postgresql

revision: str = "0029_p3h_position_catalog"
down_revision: str | None = "0028_p3g_department_hierarchy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POSITIONS_TABLE = "positions"
_TENANT_POLICY = "tenant_isolation_app"
_LIFECYCLE_TRIGGER = "trg_positions_catalog_integrity"
_LIFECYCLE_FUNCTION = "enforce_position_catalog_integrity"

_POSITION_COLUMNS = (
    "id",
    "tenant_id",
    "code",
    "code_normalized",
    "title",
    "title_normalized",
    "status",
    "archived_at",
    "created_at",
    "updated_at",
)
_POSITION_UPDATE_COLUMNS = (
    "title",
    "status",
    "archived_at",
    "updated_at",
)


def upgrade() -> None:
    _create_positions_table()
    if op.get_bind().dialect.name == "postgresql":
        _reset_postgresql_acl()
        _configure_postgresql_security()
        _create_lifecycle_trigger()


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        # FORCE RLS applies to the migration owner. Disable it transactionally so the retention
        # preflight cannot overlook another tenant's catalog history.
        disable_forced_row_security(op, table_name=_POSITIONS_TABLE)

    _assert_downgrade_is_safe()

    if is_postgresql:
        _drop_lifecycle_trigger()
        _remove_postgresql_security()
    op.drop_table(_POSITIONS_TABLE)


def _create_positions_table() -> None:
    op.create_table(
        _POSITIONS_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column(
            "code_normalized",
            sa.String(length=32),
            sa.Computed("lower(ltrim(rtrim(code)))", persisted=True),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "title_normalized",
            sa.String(length=200),
            sa.Computed("lower(ltrim(rtrim(title)))", persisted=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="active",
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            "status in ('active','archived')",
            name="ck_positions_status",
        ),
        sa.CheckConstraint(
            "length(code_normalized) > 0",
            name="ck_positions_code_normalized_not_empty",
        ),
        sa.CheckConstraint(
            "length(title_normalized) > 0",
            name="ck_positions_title_normalized_not_empty",
        ),
        sa.CheckConstraint(
            "(status = 'active' and archived_at is null) or "
            "(status = 'archived' and archived_at is not null)",
            name="ck_positions_archive_state",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_positions_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_positions"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_positions_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "code_normalized",
            name="uq_positions_tenant_code_normalized",
        ),
    )
    op.create_index(
        "ix_positions_tenant_code_cursor",
        _POSITIONS_TABLE,
        ["tenant_id", "code_normalized", "id"],
        unique=False,
    )
    op.create_index(
        "ix_positions_tenant_status_code_cursor",
        _POSITIONS_TABLE,
        ["tenant_id", "status", "code_normalized", "id"],
        unique=False,
    )
    op.create_index(
        "ix_positions_code_normalized_trgm",
        _POSITIONS_TABLE,
        ["code_normalized"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"code_normalized": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_positions_title_normalized_trgm",
        _POSITIONS_TABLE,
        ["title_normalized"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"title_normalized": "gin_trgm_ops"},
    )


def _configure_postgresql_security() -> None:
    enable_forced_row_security(op, table_name=_POSITIONS_TABLE)
    create_tenant_isolation_policy(
        op,
        table_name=_POSITIONS_TABLE,
        policy_name=_TENANT_POLICY,
        role_name=TENANT_APPLICATION_ROLE,
    )
    grant_table_privileges(
        op,
        table_name=_POSITIONS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT"),
    )
    grant_column_privilege(
        op,
        table_name=_POSITIONS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_POSITION_UPDATE_COLUMNS,
    )


def _remove_postgresql_security() -> None:
    revoke_column_privilege(
        op,
        table_name=_POSITIONS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_POSITION_UPDATE_COLUMNS,
    )
    revoke_table_privileges(
        op,
        table_name=_POSITIONS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT"),
    )
    drop_policy(
        op,
        table_name=_POSITIONS_TABLE,
        policy_name=_TENANT_POLICY,
    )


def _reset_postgresql_acl() -> None:
    quoted_columns = ", ".join(f'"{column_name}"' for column_name in _POSITION_COLUMNS)
    op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{_POSITIONS_TABLE}" FROM PUBLIC'))
    op.execute(
        sa.text(
            f'REVOKE ALL PRIVILEGES ({quoted_columns}) ON TABLE "{_POSITIONS_TABLE}" FROM PUBLIC'
        )
    )
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
    ):
        revoke_all_table_privileges(
            op,
            table_name=_POSITIONS_TABLE,
            role_name=role_name,
        )
        revoke_all_column_privileges(
            op,
            table_name=_POSITIONS_TABLE,
            role_name=role_name,
            column_names=_POSITION_COLUMNS,
        )


def _create_lifecycle_trigger() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_LIFECYCLE_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            VOLATILE
            SECURITY INVOKER
            SET search_path = pg_catalog, public
            AS $p3h_position_catalog$
            BEGIN
                IF TG_OP = 'INSERT'
                   AND (NEW.status <> 'active' OR NEW.archived_at IS NOT NULL) THEN
                    RAISE EXCEPTION 'Positions must begin in the active state'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'positions',
                              CONSTRAINT = 'ck_positions_archived_terminal';
                END IF;

                IF TG_OP = 'UPDATE'
                   AND (
                       NEW.id IS DISTINCT FROM OLD.id
                       OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                       OR NEW.code IS DISTINCT FROM OLD.code
                   ) THEN
                    RAISE EXCEPTION 'Position identity, tenant, and code are immutable'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'positions',
                              CONSTRAINT = 'ck_positions_immutable_identity_code';
                END IF;

                IF TG_OP = 'UPDATE' AND OLD.status = 'archived' THEN
                    RAISE EXCEPTION 'Archived positions are immutable history'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'positions',
                              CONSTRAINT = 'ck_positions_archived_terminal';
                END IF;

                IF TG_OP = 'UPDATE'
                   AND OLD.status = 'active'
                   AND NEW.status = 'archived'
                   AND NEW.title IS DISTINCT FROM OLD.title THEN
                    RAISE EXCEPTION 'Archiving cannot rewrite position history'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'positions',
                              CONSTRAINT = 'ck_positions_archived_terminal';
                END IF;

                RETURN NEW;
            END
            $p3h_position_catalog$
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER {_LIFECYCLE_TRIGGER} "
            f"BEFORE INSERT OR UPDATE ON public.{_POSITIONS_TABLE} "
            "FOR EACH ROW "
            f"EXECUTE FUNCTION public.{_LIFECYCLE_FUNCTION}()"
        )
    )
    op.execute(sa.text(f"REVOKE ALL ON FUNCTION public.{_LIFECYCLE_FUNCTION}() FROM PUBLIC"))
    op.execute(
        sa.text(
            f"GRANT EXECUTE ON FUNCTION public.{_LIFECYCLE_FUNCTION}() "
            f'TO "{TENANT_APPLICATION_ROLE}"'
        )
    )


def _drop_lifecycle_trigger() -> None:
    op.execute(
        sa.text(
            f"REVOKE EXECUTE ON FUNCTION public.{_LIFECYCLE_FUNCTION}() "
            f'FROM "{TENANT_APPLICATION_ROLE}"'
        )
    )
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_LIFECYCLE_TRIGGER} ON public.{_POSITIONS_TABLE}"))
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS public.{_LIFECYCLE_FUNCTION}()"))


def _assert_downgrade_is_safe() -> None:
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                """
                DO $p3h_downgrade_preflight$
                BEGIN
                    IF EXISTS (SELECT 1 FROM positions) THEN
                        RAISE EXCEPTION
                            'P3H downgrade preflight failed; export and remove retained '
                            'position catalog history before retrying';
                    END IF;
                END
                $p3h_downgrade_preflight$
                """
            )
        )
        return

    position_count = int(op.get_bind().scalar(sa.text("select count(*) from positions")) or 0)
    if position_count == 0:
        return
    raise RuntimeError(
        "P3H downgrade preflight failed; export and remove retained position catalog "
        f"history before retrying: positions={position_count}"
    )


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
