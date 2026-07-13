"""add P3G tenant department hierarchy

Revision ID: 0028_p3g_department_hierarchy
Revises: 0027_p3f_legal_entities_branches
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

revision: str = "0028_p3g_department_hierarchy"
down_revision: str | None = "0027_p3f_legal_entities_branches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEPARTMENTS_TABLE = "departments"
_HIERARCHY_FENCES_TABLE = "department_hierarchy_write_fences"
_TENANT_POLICY = "tenant_isolation_app"
_HIERARCHY_TRIGGER = "trg_departments_hierarchy_integrity"
_HIERARCHY_FUNCTION = "enforce_department_hierarchy_integrity"
_ACYCLIC_INSERT_TRIGGER = "trg_departments_acyclic_after_insert"
_ACYCLIC_UPDATE_TRIGGER = "trg_departments_acyclic_after_update"
_ACYCLIC_FUNCTION = "validate_department_hierarchy_acyclic"

_DEPARTMENT_COLUMNS = (
    "id",
    "tenant_id",
    "parent_id",
    "code",
    "code_normalized",
    "name",
    "status",
    "archived_at",
    "created_at",
    "updated_at",
)
_DEPARTMENT_UPDATE_COLUMNS = (
    "name",
    "parent_id",
    "status",
    "archived_at",
    "updated_at",
)
_HIERARCHY_FENCE_COLUMNS = (
    "tenant_id",
    "version",
)


def upgrade() -> None:
    _create_hierarchy_fences_table()
    _create_departments_table()
    if op.get_bind().dialect.name == "postgresql":
        _reset_postgresql_acl()
        _configure_postgresql_security()
        _create_hierarchy_trigger()


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        # The migration owner is also subject to FORCE RLS. Disable it transactionally so the
        # retention preflight cannot overlook another tenant's hierarchy.
        disable_forced_row_security(op, table_name=_DEPARTMENTS_TABLE)

    _assert_downgrade_is_safe()

    if is_postgresql:
        _drop_hierarchy_trigger()
        _remove_postgresql_security()
    op.drop_table(_DEPARTMENTS_TABLE)
    op.drop_table(_HIERARCHY_FENCES_TABLE)


def _create_hierarchy_fences_table() -> None:
    """Create the write-version row that makes serialization snapshot-safe."""

    op.create_table(
        _HIERARCHY_FENCES_TABLE,
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.BigInteger(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "version >= 0",
            name="ck_department_hierarchy_write_fences_version",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_department_hierarchy_write_fences_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            name="pk_department_hierarchy_write_fences",
        ),
    )


def _create_departments_table() -> None:
    op.create_table(
        _DEPARTMENTS_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column(
            "code_normalized",
            sa.String(length=32),
            sa.Computed("lower(ltrim(rtrim(code)))", persisted=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
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
            name="ck_departments_status",
        ),
        sa.CheckConstraint(
            "length(code_normalized) > 0",
            name="ck_departments_code_normalized_not_empty",
        ),
        sa.CheckConstraint(
            "(status = 'active' and archived_at is null) or "
            "(status = 'archived' and archived_at is not null)",
            name="ck_departments_archive_state",
        ),
        sa.CheckConstraint(
            "parent_id is null or parent_id <> id",
            name="ck_departments_parent_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_departments_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_departments"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_departments_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "code_normalized",
            name="uq_departments_tenant_code_normalized",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["departments.tenant_id", "departments.id"],
            name="fk_departments_tenant_parent_id_departments",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_departments_tenant_parent_status_code",
        _DEPARTMENTS_TABLE,
        ["tenant_id", "parent_id", "status", "code_normalized", "id"],
        unique=False,
    )
    op.create_index(
        "ix_departments_tenant_status_code",
        _DEPARTMENTS_TABLE,
        ["tenant_id", "status", "code_normalized", "id"],
        unique=False,
    )


def _configure_postgresql_security() -> None:
    enable_forced_row_security(op, table_name=_HIERARCHY_FENCES_TABLE)
    create_tenant_isolation_policy(
        op,
        table_name=_HIERARCHY_FENCES_TABLE,
        policy_name=_TENANT_POLICY,
        role_name=TENANT_APPLICATION_ROLE,
    )
    grant_table_privileges(
        op,
        table_name=_HIERARCHY_FENCES_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT"),
    )
    grant_column_privilege(
        op,
        table_name=_HIERARCHY_FENCES_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=("version",),
    )
    enable_forced_row_security(op, table_name=_DEPARTMENTS_TABLE)
    create_tenant_isolation_policy(
        op,
        table_name=_DEPARTMENTS_TABLE,
        policy_name=_TENANT_POLICY,
        role_name=TENANT_APPLICATION_ROLE,
    )
    grant_table_privileges(
        op,
        table_name=_DEPARTMENTS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT"),
    )
    grant_column_privilege(
        op,
        table_name=_DEPARTMENTS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_DEPARTMENT_UPDATE_COLUMNS,
    )


def _remove_postgresql_security() -> None:
    revoke_column_privilege(
        op,
        table_name=_DEPARTMENTS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_DEPARTMENT_UPDATE_COLUMNS,
    )
    revoke_table_privileges(
        op,
        table_name=_DEPARTMENTS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT"),
    )
    drop_policy(
        op,
        table_name=_DEPARTMENTS_TABLE,
        policy_name=_TENANT_POLICY,
    )
    revoke_column_privilege(
        op,
        table_name=_HIERARCHY_FENCES_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=("version",),
    )
    revoke_table_privileges(
        op,
        table_name=_HIERARCHY_FENCES_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT"),
    )
    drop_policy(
        op,
        table_name=_HIERARCHY_FENCES_TABLE,
        policy_name=_TENANT_POLICY,
    )


def _reset_postgresql_acl() -> None:
    quoted_columns = ", ".join(f'"{column_name}"' for column_name in _DEPARTMENT_COLUMNS)
    op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{_DEPARTMENTS_TABLE}" FROM PUBLIC'))
    op.execute(
        sa.text(
            f'REVOKE ALL PRIVILEGES ({quoted_columns}) '
            f'ON TABLE "{_DEPARTMENTS_TABLE}" FROM PUBLIC'
        )
    )
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
    ):
        revoke_all_table_privileges(
            op,
            table_name=_DEPARTMENTS_TABLE,
            role_name=role_name,
        )
        revoke_all_column_privileges(
            op,
            table_name=_DEPARTMENTS_TABLE,
            role_name=role_name,
            column_names=_DEPARTMENT_COLUMNS,
        )

    quoted_fence_columns = ", ".join(
        f'"{column_name}"' for column_name in _HIERARCHY_FENCE_COLUMNS
    )
    op.execute(
        sa.text(
            f'REVOKE ALL PRIVILEGES ON TABLE "{_HIERARCHY_FENCES_TABLE}" FROM PUBLIC'
        )
    )
    op.execute(
        sa.text(
            f'REVOKE ALL PRIVILEGES ({quoted_fence_columns}) '
            f'ON TABLE "{_HIERARCHY_FENCES_TABLE}" FROM PUBLIC'
        )
    )
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
    ):
        revoke_all_table_privileges(
            op,
            table_name=_HIERARCHY_FENCES_TABLE,
            role_name=role_name,
        )
        revoke_all_column_privileges(
            op,
            table_name=_HIERARCHY_FENCES_TABLE,
            role_name=role_name,
            column_names=_HIERARCHY_FENCE_COLUMNS,
        )


def _create_hierarchy_trigger() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_HIERARCHY_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            VOLATILE
            SECURITY INVOKER
            SET search_path = pg_catalog, public
            AS $p3g_department_hierarchy$
            DECLARE
                locked_tenant_id uuid;
                requested_parent_status text;
            BEGIN
                -- This sentinel lock is deliberately the first hierarchy operation. It is the
                -- same lock acquired by application commands, and serializes every structural
                -- decision for one tenant before ancestry or archive state is inspected.
                SELECT tenants.id INTO locked_tenant_id
                FROM public.tenants AS tenants
                WHERE tenants.id = NEW.tenant_id
                FOR UPDATE OF tenants;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'Department tenant is unavailable'
                        USING ERRCODE = '23503',
                              SCHEMA = 'public',
                              TABLE = 'departments',
                              CONSTRAINT = 'fk_departments_tenant_id_tenants';
                END IF;

                -- A lock-only sentinel is insufficient when a caller already owns a
                -- REPEATABLE READ snapshot: after waiting it could still validate against the
                -- pre-wait graph. Advancing this tenant-owned row makes a stale concurrent
                -- writer fail with a serialization error before any ancestry read. Under READ
                -- COMMITTED it also remains the single serialized write fence for the tenant.
                INSERT INTO public.department_hierarchy_write_fences AS fence (
                    tenant_id,
                    version
                ) VALUES (
                    NEW.tenant_id,
                    1
                )
                ON CONFLICT (tenant_id)
                DO UPDATE SET version = fence.version + 1;

                IF TG_OP = 'UPDATE'
                   AND (
                       NEW.id IS DISTINCT FROM OLD.id
                       OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                       OR NEW.code IS DISTINCT FROM OLD.code
                   ) THEN
                    RAISE EXCEPTION 'Department identity, tenant, and code are immutable'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'departments',
                              CONSTRAINT = 'ck_departments_immutable_identity_code';
                END IF;

                IF TG_OP = 'INSERT'
                   AND (NEW.status <> 'active' OR NEW.archived_at IS NOT NULL) THEN
                    RAISE EXCEPTION 'Departments must begin in the active state'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'departments',
                              CONSTRAINT = 'ck_departments_archived_terminal';
                END IF;

                IF TG_OP = 'UPDATE'
                   AND OLD.status = 'archived'
                   AND (
                       NEW.parent_id IS DISTINCT FROM OLD.parent_id
                       OR NEW.name IS DISTINCT FROM OLD.name
                       OR NEW.status IS DISTINCT FROM OLD.status
                       OR NEW.archived_at IS DISTINCT FROM OLD.archived_at
                       OR NEW.updated_at IS DISTINCT FROM OLD.updated_at
                   ) THEN
                    RAISE EXCEPTION 'Archived departments are immutable history'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'departments',
                              CONSTRAINT = 'ck_departments_archived_terminal';
                END IF;

                IF TG_OP = 'UPDATE'
                   AND OLD.status = 'active'
                   AND NEW.status = 'archived'
                   AND NEW.parent_id IS DISTINCT FROM OLD.parent_id THEN
                    RAISE EXCEPTION 'Archiving cannot rewrite department history'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'departments',
                              CONSTRAINT = 'ck_departments_archived_terminal';
                END IF;

                IF NEW.parent_id IS NOT NULL THEN
                    IF NEW.parent_id = NEW.id THEN
                        RAISE EXCEPTION 'Department hierarchy cycle detected'
                            USING ERRCODE = '23514',
                                  SCHEMA = 'public',
                                  TABLE = 'departments',
                                  CONSTRAINT = 'ck_departments_acyclic';
                    END IF;

                    SELECT departments.status INTO requested_parent_status
                    FROM public.departments AS departments
                    WHERE departments.tenant_id = NEW.tenant_id
                      AND departments.id = NEW.parent_id;
                    IF NOT FOUND THEN
                        RAISE EXCEPTION 'Department parent is unavailable'
                            USING ERRCODE = '23503',
                                  SCHEMA = 'public',
                                  TABLE = 'departments',
                                  CONSTRAINT = 'fk_departments_tenant_parent_id_departments';
                    END IF;
                    IF NEW.status = 'active' AND requested_parent_status <> 'active' THEN
                        RAISE EXCEPTION 'Active departments require an active parent'
                            USING ERRCODE = '23514',
                                  SCHEMA = 'public',
                                  TABLE = 'departments',
                                  CONSTRAINT = 'ck_departments_active_parent';
                    END IF;

                    IF EXISTS (
                        WITH RECURSIVE ancestors(id, parent_id) AS (
                            SELECT departments.id, departments.parent_id
                            FROM public.departments AS departments
                            WHERE departments.tenant_id = NEW.tenant_id
                              AND departments.id = NEW.parent_id
                            UNION
                            SELECT departments.id, departments.parent_id
                            FROM public.departments AS departments
                            JOIN ancestors ON ancestors.parent_id = departments.id
                            WHERE departments.tenant_id = NEW.tenant_id
                        )
                        SELECT 1 FROM ancestors WHERE ancestors.id = NEW.id
                    ) THEN
                        RAISE EXCEPTION 'Department hierarchy cycle detected'
                            USING ERRCODE = '23514',
                                  SCHEMA = 'public',
                                  TABLE = 'departments',
                                  CONSTRAINT = 'ck_departments_acyclic';
                    END IF;
                END IF;

                IF TG_OP = 'UPDATE'
                   AND OLD.status = 'active'
                   AND NEW.status = 'archived'
                   AND EXISTS (
                       SELECT 1
                       FROM public.departments AS children
                       WHERE children.tenant_id = NEW.tenant_id
                         AND children.parent_id = NEW.id
                         AND children.status = 'active'
                   ) THEN
                    RAISE EXCEPTION 'Departments with active children cannot be archived'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'departments',
                              CONSTRAINT = 'ck_departments_no_active_children';
                END IF;

                RETURN NEW;
            END
            $p3g_department_hierarchy$
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER {_HIERARCHY_TRIGGER} "
            f"BEFORE INSERT OR UPDATE ON public.{_DEPARTMENTS_TABLE} "
            "FOR EACH ROW "
            f"EXECUTE FUNCTION public.{_HIERARCHY_FUNCTION}()"
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL ON FUNCTION public.{_HIERARCHY_FUNCTION}() FROM PUBLIC"
        )
    )
    op.execute(
        sa.text(
            f"GRANT EXECUTE ON FUNCTION public.{_HIERARCHY_FUNCTION}() "
            f'TO "{TENANT_APPLICATION_ROLE}"'
        )
    )
    _create_final_graph_validation_triggers()


def _create_final_graph_validation_triggers() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_ACYCLIC_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            VOLATILE
            SECURITY INVOKER
            SET search_path = pg_catalog, public
            AS $p3g_department_final_graph$
            BEGIN
                -- A row trigger cannot be the only proof for a statement that changes several
                -- edges. Start at every affected node and inspect the statement's completed graph;
                -- the path array terminates safely at the first repeated UUID.
                IF EXISTS (
                    WITH RECURSIVE hierarchy_walk(
                        tenant_id,
                        origin_id,
                        current_id,
                        parent_id,
                        visited_ids,
                        cycle_found
                    ) AS (
                        SELECT changed.tenant_id,
                               changed.id,
                               changed.id,
                               changed.parent_id,
                               ARRAY[changed.id]::uuid[],
                               false
                        FROM new_departments AS changed
                        WHERE changed.parent_id IS NOT NULL
                        UNION ALL
                        SELECT hierarchy_walk.tenant_id,
                               hierarchy_walk.origin_id,
                               parent.id,
                               parent.parent_id,
                               hierarchy_walk.visited_ids || parent.id,
                               parent.id = ANY(hierarchy_walk.visited_ids)
                        FROM hierarchy_walk
                        JOIN public.departments AS parent
                          ON parent.tenant_id = hierarchy_walk.tenant_id
                         AND parent.id = hierarchy_walk.parent_id
                        WHERE NOT hierarchy_walk.cycle_found
                    )
                    SELECT 1
                    FROM hierarchy_walk
                    WHERE hierarchy_walk.cycle_found
                ) THEN
                    RAISE EXCEPTION 'Department hierarchy cycle detected'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'departments',
                              CONSTRAINT = 'ck_departments_acyclic';
                END IF;
                RETURN NULL;
            END
            $p3g_department_final_graph$
            """
        )
    )
    for trigger_name, operation in (
        (_ACYCLIC_INSERT_TRIGGER, "INSERT"),
        (_ACYCLIC_UPDATE_TRIGGER, "UPDATE"),
    ):
        op.execute(
            sa.text(
                f"CREATE TRIGGER {trigger_name} "
                f"AFTER {operation} ON public.{_DEPARTMENTS_TABLE} "
                "REFERENCING NEW TABLE AS new_departments "
                "FOR EACH STATEMENT "
                f"EXECUTE FUNCTION public.{_ACYCLIC_FUNCTION}()"
            )
        )
    op.execute(
        sa.text(f"REVOKE ALL ON FUNCTION public.{_ACYCLIC_FUNCTION}() FROM PUBLIC")
    )
    op.execute(
        sa.text(
            f"GRANT EXECUTE ON FUNCTION public.{_ACYCLIC_FUNCTION}() "
            f'TO "{TENANT_APPLICATION_ROLE}"'
        )
    )


def _drop_hierarchy_trigger() -> None:
    op.execute(
        sa.text(
            f"REVOKE EXECUTE ON FUNCTION public.{_ACYCLIC_FUNCTION}() "
            f'FROM "{TENANT_APPLICATION_ROLE}"'
        )
    )
    op.execute(
        sa.text(
            f"REVOKE EXECUTE ON FUNCTION public.{_HIERARCHY_FUNCTION}() "
            f'FROM "{TENANT_APPLICATION_ROLE}"'
        )
    )
    for trigger_name in (
        _ACYCLIC_UPDATE_TRIGGER,
        _ACYCLIC_INSERT_TRIGGER,
        _HIERARCHY_TRIGGER,
    ):
        op.execute(
            sa.text(
                f"DROP TRIGGER IF EXISTS {trigger_name} "
                f"ON public.{_DEPARTMENTS_TABLE}"
            )
        )
    op.execute(
        sa.text(f"DROP FUNCTION IF EXISTS public.{_ACYCLIC_FUNCTION}()")
    )
    op.execute(
        sa.text(f"DROP FUNCTION IF EXISTS public.{_HIERARCHY_FUNCTION}()")
    )


def _assert_downgrade_is_safe() -> None:
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                """
                DO $p3g_downgrade_preflight$
                BEGIN
                    IF EXISTS (SELECT 1 FROM departments) THEN
                        RAISE EXCEPTION
                            'P3G downgrade preflight failed; export and remove retained '
                            'department history before retrying';
                    END IF;
                END
                $p3g_downgrade_preflight$
                """
            )
        )
        return

    department_count = int(
        op.get_bind().scalar(sa.text("select count(*) from departments")) or 0
    )
    if department_count:
        raise RuntimeError(
            "P3G downgrade preflight failed; export and remove retained department history "
            "before retrying"
        )
