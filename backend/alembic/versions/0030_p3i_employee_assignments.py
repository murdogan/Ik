"""add P3I effective-dated employee assignments

Revision ID: 0030_p3i_employee_assignments
Revises: 0029_p3h_position_catalog
Create Date: 2026-07-13
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID

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
from sqlalchemy.engine import RowMapping
from sqlalchemy.sql.selectable import TableClause

revision: str = "0030_p3i_employee_assignments"
down_revision: str | None = "0029_p3h_position_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ASSIGNMENTS_TABLE = "employee_assignments"
_TENANT_POLICY = "tenant_isolation_app"
_INTEGRITY_TRIGGER = "trg_employee_assignments_integrity"
_INTEGRITY_FUNCTION = "enforce_employee_assignment_integrity"

_ASSIGNMENT_COLUMNS = (
    "id",
    "tenant_id",
    "employee_id",
    "legal_entity_id",
    "branch_id",
    "department_id",
    "position_id",
    "manager_user_id",
    "supersedes_assignment_id",
    "effective_from",
    "effective_to",
    "change_reason",
    "created_by_user_id",
    "created_at",
    "updated_at",
)
_ASSIGNMENT_UPDATE_COLUMNS = (
    "effective_to",
    "updated_at",
)

# Backfill writes touch catalog tables whose FORCE RLS applies to their owner too. Departments
# additionally update the P3G hierarchy fence from their integrity trigger.
_POSTGRESQL_BACKFILL_TABLES = (
    "tenants",
    "employees",
    "legal_entities",
    "branches",
    "department_hierarchy_write_fences",
    "departments",
    "positions",
)

_UUID = postgresql.UUID(as_uuid=True)

_employees = sa.table(
    "employees",
    sa.column("id", _UUID),
    sa.column("tenant_id", _UUID),
    sa.column("department", sa.Text()),
    sa.column("position", sa.Text()),
    sa.column("status", sa.String()),
    sa.column("employment_start_date", sa.Date()),
    sa.column("employment_end_date", sa.Date()),
)
_legal_entities = sa.table(
    "legal_entities",
    sa.column("id", _UUID),
    sa.column("tenant_id", _UUID),
    sa.column("timezone", sa.String()),
    sa.column("status", sa.String()),
    sa.column("is_default", sa.Boolean()),
)
_branches = sa.table(
    "branches",
    sa.column("id", _UUID),
    sa.column("tenant_id", _UUID),
    sa.column("legal_entity_id", _UUID),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("timezone", sa.String()),
    sa.column("status", sa.String()),
    sa.column("archived_at", sa.DateTime(timezone=True)),
)
_departments = sa.table(
    "departments",
    sa.column("id", _UUID),
    sa.column("tenant_id", _UUID),
    sa.column("parent_id", _UUID),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("status", sa.String()),
    sa.column("archived_at", sa.DateTime(timezone=True)),
)
_positions = sa.table(
    "positions",
    sa.column("id", _UUID),
    sa.column("tenant_id", _UUID),
    sa.column("code", sa.String()),
    sa.column("title", sa.String()),
    sa.column("status", sa.String()),
    sa.column("archived_at", sa.DateTime(timezone=True)),
)
_assignments = sa.table(
    _ASSIGNMENTS_TABLE,
    sa.column("id", _UUID),
    sa.column("tenant_id", _UUID),
    sa.column("employee_id", _UUID),
    sa.column("legal_entity_id", _UUID),
    sa.column("branch_id", _UUID),
    sa.column("department_id", _UUID),
    sa.column("position_id", _UUID),
    sa.column("manager_user_id", _UUID),
    sa.column("supersedes_assignment_id", _UUID),
    sa.column("effective_from", sa.Date()),
    sa.column("effective_to", sa.Date()),
    sa.column("change_reason", sa.String()),
    sa.column("created_by_user_id", _UUID),
)


def upgrade() -> None:
    _create_assignments_table()

    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        for table_name in _POSTGRESQL_BACKFILL_TABLES:
            disable_forced_row_security(op, table_name=table_name)
        _backfill_postgresql()
        _assert_backfill_complete()
        for table_name in _POSTGRESQL_BACKFILL_TABLES:
            enable_forced_row_security(op, table_name=table_name)
        _reset_postgresql_acl()
        _configure_postgresql_security()
        # Runtime integrity is stricter than the one-time expand backfill: historical terminated
        # employees receive closed rows above, while every new assignment must start open-ended.
        _create_integrity_trigger()
        return

    _backfill_sqlite()
    _assert_backfill_complete()


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        # The migration owner is subject to FORCE RLS. Disable it transactionally so retained
        # history in another tenant cannot be overlooked by the downgrade preflight.
        disable_forced_row_security(op, table_name=_ASSIGNMENTS_TABLE)

    _assert_downgrade_is_safe()

    if is_postgresql:
        _drop_integrity_trigger()
        _remove_postgresql_security()
    op.drop_table(_ASSIGNMENTS_TABLE)


def _create_assignments_table() -> None:
    op.create_table(
        _ASSIGNMENTS_TABLE,
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("employee_id", _UUID, nullable=False),
        sa.Column("legal_entity_id", _UUID, nullable=False),
        sa.Column("branch_id", _UUID, nullable=False),
        sa.Column("department_id", _UUID, nullable=False),
        sa.Column("position_id", _UUID, nullable=False),
        sa.Column("manager_user_id", _UUID, nullable=True),
        sa.Column("supersedes_assignment_id", _UUID, nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("change_reason", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", _UUID, nullable=True),
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
            "effective_to is null or effective_to >= effective_from",
            name="ck_employee_assignments_effective_range",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_employee_assignments_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_employee_assignments_tenant_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "legal_entity_id"],
            ["legal_entities.tenant_id", "legal_entities.id"],
            name="fk_employee_assignments_tenant_legal_entity_id_legal_entities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "branch_id"],
            ["branches.tenant_id", "branches.id"],
            name="fk_employee_assignments_tenant_branch_id_branches",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["departments.tenant_id", "departments.id"],
            name="fk_employee_assignments_tenant_department_id_departments",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "position_id"],
            ["positions.tenant_id", "positions.id"],
            name="fk_employee_assignments_tenant_position_id_positions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "manager_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_employee_assignments_tenant_manager_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_employee_assignments_tenant_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supersedes_assignment_id"],
            ["employee_assignments.tenant_id", "employee_assignments.id"],
            name="fk_employee_assignments_tenant_supersedes_employee_assignments",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_employee_assignments"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_employee_assignments_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "supersedes_assignment_id",
            name="uq_employee_assignments_tenant_supersedes_assignment_id",
        ),
    )
    op.create_index(
        "uq_employee_assignments_tenant_employee_open",
        _ASSIGNMENTS_TABLE,
        ["tenant_id", "employee_id"],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL"),
        sqlite_where=sa.text("effective_to IS NULL"),
    )
    op.create_index(
        "ix_employee_assignments_tenant_employee_history",
        _ASSIGNMENTS_TABLE,
        ["tenant_id", "employee_id", "effective_from", "id"],
        unique=False,
    )
    op.create_index(
        "ix_employee_assignments_tenant_manager_scope",
        _ASSIGNMENTS_TABLE,
        [
            "tenant_id",
            "manager_user_id",
            "effective_from",
            "effective_to",
            "employee_id",
        ],
        unique=False,
    )
    op.create_index(
        "ix_employee_assignments_tenant_department_effective",
        _ASSIGNMENTS_TABLE,
        ["tenant_id", "department_id", "effective_from"],
        unique=False,
    )
    op.create_index(
        "ix_employee_assignments_tenant_branch_effective",
        _ASSIGNMENTS_TABLE,
        ["tenant_id", "branch_id", "effective_from"],
        unique=False,
    )


def _backfill_postgresql() -> None:
    """Map every legacy employee with deterministic catalog and assignment rows."""

    statements = (
        """
        CREATE TEMPORARY TABLE p3i_legacy_branch_map ON COMMIT DROP AS
        SELECT employee_tenants.tenant_id,
               legal_entity.id AS legal_entity_id,
               legal_entity.timezone,
               coalesce(
                   existing_branch.id,
                   md5('p3i:branch:' || employee_tenants.tenant_id::text)::uuid
               ) AS branch_id,
               CASE
                   WHEN legacy_code_conflict.id IS NULL THEN 'LEGACY'
                   ELSE 'LEGACY-' || substr(
                       md5('p3i:branch-code:' || employee_tenants.tenant_id::text),
                       1,
                       24
                   )
               END AS branch_code,
               existing_branch.id IS NULL AS needs_insert
        FROM (
            SELECT DISTINCT tenant_id
            FROM public.employees
        ) AS employee_tenants
        JOIN public.legal_entities AS legal_entity
          ON legal_entity.tenant_id = employee_tenants.tenant_id
         AND legal_entity.is_default = true
         AND legal_entity.status = 'active'
        LEFT JOIN LATERAL (
            SELECT branch.id
            FROM public.branches AS branch
            WHERE branch.tenant_id = employee_tenants.tenant_id
              AND branch.legal_entity_id = legal_entity.id
              AND branch.code_normalized = 'legacy'
              AND branch.status = 'active'
              AND branch.archived_at IS NULL
            ORDER BY branch.id
            LIMIT 1
        ) AS existing_branch ON true
        LEFT JOIN LATERAL (
            SELECT branch.id
            FROM public.branches AS branch
            WHERE branch.tenant_id = employee_tenants.tenant_id
              AND branch.code_normalized = 'legacy'
            ORDER BY branch.id
            LIMIT 1
        ) AS legacy_code_conflict ON true
        """,
        """
        INSERT INTO public.branches (
            id,
            tenant_id,
            legal_entity_id,
            code,
            name,
            timezone,
            status,
            archived_at
        )
        SELECT branch_id,
               tenant_id,
               legal_entity_id,
               branch_code,
               'Legacy / Unspecified',
               timezone,
               'active',
               NULL
        FROM p3i_legacy_branch_map
        WHERE needs_insert
        """,
        """
        CREATE TEMPORARY TABLE p3i_legacy_department_map ON COMMIT DROP AS
        WITH legacy_values AS (
            SELECT employee.tenant_id,
                   lower(
                       btrim(
                           CASE
                               WHEN NULLIF(btrim(employee.department), '') IS NULL
                                   THEN 'Unspecified'
                               ELSE employee.department
                           END
                       )
                   ) AS legacy_key,
                   min(
                       btrim(
                           CASE
                               WHEN NULLIF(btrim(employee.department), '') IS NULL
                                   THEN 'Unspecified'
                               ELSE employee.department
                           END
                       )
                   ) AS legacy_label
            FROM public.employees AS employee
            GROUP BY employee.tenant_id,
                     lower(
                         btrim(
                             CASE
                                 WHEN NULLIF(btrim(employee.department), '') IS NULL
                                     THEN 'Unspecified'
                                 ELSE employee.department
                             END
                         )
                     )
        )
        SELECT legacy_values.tenant_id,
               legacy_values.legacy_key,
               left(legacy_values.legacy_label, 200) AS legacy_label,
               coalesce(
                   existing_department.id,
                   md5(
                       'p3i:department:'
                       || legacy_values.tenant_id::text
                       || ':'
                       || legacy_values.legacy_key
                   )::uuid
               ) AS department_id,
               existing_department.id IS NULL AS needs_insert
        FROM legacy_values
        LEFT JOIN LATERAL (
            SELECT department.id
            FROM public.departments AS department
            WHERE department.tenant_id = legacy_values.tenant_id
              AND department.status = 'active'
              AND department.archived_at IS NULL
              AND lower(btrim(department.name)) = legacy_values.legacy_key
            ORDER BY department.id
            LIMIT 1
        ) AS existing_department ON true
        """,
        """
        INSERT INTO public.departments (
            id,
            tenant_id,
            parent_id,
            code,
            name,
            status,
            archived_at
        )
        SELECT department_id,
               tenant_id,
               NULL,
               'LEGACY-' || substr(
                   md5(
                       'p3i:department-code:'
                       || tenant_id::text
                       || ':'
                       || legacy_key
                   ),
                   1,
                   24
               ),
               legacy_label,
               'active',
               NULL
        FROM p3i_legacy_department_map
        WHERE needs_insert
        """,
        """
        CREATE TEMPORARY TABLE p3i_legacy_position_map ON COMMIT DROP AS
        WITH legacy_values AS (
            SELECT employee.tenant_id,
                   lower(
                       btrim(
                           CASE
                               WHEN NULLIF(btrim(employee.position), '') IS NULL
                                   THEN 'Unspecified'
                               ELSE employee.position
                           END
                       )
                   ) AS legacy_key,
                   min(
                       btrim(
                           CASE
                               WHEN NULLIF(btrim(employee.position), '') IS NULL
                                   THEN 'Unspecified'
                               ELSE employee.position
                           END
                       )
                   ) AS legacy_label
            FROM public.employees AS employee
            GROUP BY employee.tenant_id,
                     lower(
                         btrim(
                             CASE
                                 WHEN NULLIF(btrim(employee.position), '') IS NULL
                                     THEN 'Unspecified'
                                 ELSE employee.position
                             END
                         )
                     )
        )
        SELECT legacy_values.tenant_id,
               legacy_values.legacy_key,
               left(legacy_values.legacy_label, 200) AS legacy_label,
               coalesce(
                   existing_position.id,
                   md5(
                       'p3i:position:'
                       || legacy_values.tenant_id::text
                       || ':'
                       || legacy_values.legacy_key
                   )::uuid
               ) AS position_id,
               existing_position.id IS NULL AS needs_insert
        FROM legacy_values
        LEFT JOIN LATERAL (
            SELECT position.id
            FROM public.positions AS position
            WHERE position.tenant_id = legacy_values.tenant_id
              AND position.status = 'active'
              AND position.archived_at IS NULL
              AND lower(btrim(position.title)) = legacy_values.legacy_key
            ORDER BY position.id
            LIMIT 1
        ) AS existing_position ON true
        """,
        """
        INSERT INTO public.positions (
            id,
            tenant_id,
            code,
            title,
            status,
            archived_at
        )
        SELECT position_id,
               tenant_id,
               'LEGACY-' || substr(
                   md5(
                       'p3i:position-code:'
                       || tenant_id::text
                       || ':'
                       || legacy_key
                   ),
                   1,
                   24
               ),
               legacy_label,
               'active',
               NULL
        FROM p3i_legacy_position_map
        WHERE needs_insert
        """,
        """
        INSERT INTO public.employee_assignments (
            id,
            tenant_id,
            employee_id,
            legal_entity_id,
            branch_id,
            department_id,
            position_id,
            manager_user_id,
            supersedes_assignment_id,
            effective_from,
            effective_to,
            change_reason,
            created_by_user_id
        )
        SELECT md5(
                   'p3i:assignment:'
                   || employee.tenant_id::text
                   || ':'
                   || employee.id::text
               )::uuid,
               employee.tenant_id,
               employee.id,
               branch_map.legal_entity_id,
               branch_map.branch_id,
               department_map.department_id,
               position_map.position_id,
               NULL,
               NULL,
               employee.employment_start_date,
               CASE
                   WHEN employee.status = 'terminated'
                       THEN employee.employment_end_date + 1
                   ELSE NULL
               END,
               'P3I legacy employee backfill',
               NULL
        FROM public.employees AS employee
        JOIN p3i_legacy_branch_map AS branch_map
          ON branch_map.tenant_id = employee.tenant_id
        JOIN p3i_legacy_department_map AS department_map
          ON department_map.tenant_id = employee.tenant_id
         AND department_map.legacy_key = lower(
             btrim(
                 CASE
                     WHEN NULLIF(btrim(employee.department), '') IS NULL
                         THEN 'Unspecified'
                     ELSE employee.department
                 END
             )
         )
        JOIN p3i_legacy_position_map AS position_map
          ON position_map.tenant_id = employee.tenant_id
         AND position_map.legacy_key = lower(
             btrim(
                 CASE
                     WHEN NULLIF(btrim(employee.position), '') IS NULL
                         THEN 'Unspecified'
                     ELSE employee.position
                 END
             )
         )
        """,
        "DROP TABLE p3i_legacy_position_map",
        "DROP TABLE p3i_legacy_department_map",
        "DROP TABLE p3i_legacy_branch_map",
    )
    for statement in statements:
        op.execute(sa.text(statement))


def _backfill_sqlite() -> None:
    """SQLite equivalent of the PostgreSQL set-based migration backfill."""

    connection = op.get_bind()
    employee_rows = list(
        connection.execute(
            sa.select(
                _employees.c.id,
                _employees.c.tenant_id,
                _employees.c.department,
                _employees.c.position,
                _employees.c.status,
                _employees.c.employment_start_date,
                _employees.c.employment_end_date,
            )
        ).mappings()
    )
    if not employee_rows:
        return

    tenant_ids = sorted(
        {_as_uuid(row["tenant_id"]) for row in employee_rows},
        key=str,
    )
    legal_entity_rows = list(
        connection.execute(
            sa.select(
                _legal_entities.c.id,
                _legal_entities.c.tenant_id,
                _legal_entities.c.timezone,
            ).where(
                _legal_entities.c.tenant_id.in_(tenant_ids),
                _legal_entities.c.is_default.is_(True),
                _legal_entities.c.status == "active",
            )
        ).mappings()
    )
    default_entities = {
        _as_uuid(row["tenant_id"]): (_as_uuid(row["id"]), row["timezone"])
        for row in legal_entity_rows
    }
    missing_default_tenants = set(tenant_ids) - default_entities.keys()
    if missing_default_tenants:
        raise RuntimeError(
            "P3I employee assignment backfill requires one active default legal entity "
            "for every tenant with employees: missing_tenants="
            + ",".join(sorted(map(str, missing_default_tenants)))
        )

    existing_branch_rows = list(
        connection.execute(
            sa.select(
                _branches.c.id,
                _branches.c.tenant_id,
                _branches.c.legal_entity_id,
                _branches.c.code,
                _branches.c.status,
                _branches.c.archived_at,
            ).where(_branches.c.tenant_id.in_(tenant_ids))
        ).mappings()
    )
    legacy_code_tenants: set[UUID] = set()
    existing_legacy_branch_by_tenant: dict[UUID, UUID] = {}
    for row in sorted(existing_branch_rows, key=lambda item: str(item["id"])):
        if _legacy_key(row["code"]) != "legacy":
            continue
        tenant_id = _as_uuid(row["tenant_id"])
        legacy_code_tenants.add(tenant_id)
        if (
            row["status"] == "active"
            and row["archived_at"] is None
            and _as_uuid(row["legal_entity_id"]) == default_entities[tenant_id][0]
        ):
            existing_legacy_branch_by_tenant.setdefault(
                tenant_id,
                _as_uuid(row["id"]),
            )

    branch_by_tenant: dict[UUID, UUID] = {}
    branch_rows: list[dict[str, object]] = []
    for tenant_id in tenant_ids:
        existing_branch_id = existing_legacy_branch_by_tenant.get(tenant_id)
        if existing_branch_id is not None:
            branch_by_tenant[tenant_id] = existing_branch_id
            continue
        branch_id = _deterministic_uuid(f"p3i:branch:{tenant_id}")
        legal_entity_id, timezone = default_entities[tenant_id]
        branch_by_tenant[tenant_id] = branch_id
        branch_rows.append(
            {
                "id": branch_id,
                "tenant_id": tenant_id,
                "legal_entity_id": legal_entity_id,
                "code": (
                    _legacy_code(f"p3i:branch-code:{tenant_id}")
                    if tenant_id in legacy_code_tenants
                    else "LEGACY"
                ),
                "name": "Legacy / Unspecified",
                "timezone": timezone,
                "status": "active",
                "archived_at": None,
            }
        )
    if branch_rows:
        connection.execute(sa.insert(_branches), branch_rows)

    department_by_key = _backfill_sqlite_catalog(
        employee_rows=employee_rows,
        tenant_ids=tenant_ids,
        legacy_column="department",
        catalog_table=_departments,
        catalog_label_column="name",
        catalog_kind="department",
    )
    position_by_key = _backfill_sqlite_catalog(
        employee_rows=employee_rows,
        tenant_ids=tenant_ids,
        legacy_column="position",
        catalog_table=_positions,
        catalog_label_column="title",
        catalog_kind="position",
    )

    assignment_rows: list[dict[str, object]] = []
    for row in employee_rows:
        tenant_id = _as_uuid(row["tenant_id"])
        employee_id = _as_uuid(row["id"])
        end_date = row["employment_end_date"]
        assignment_rows.append(
            {
                "id": _deterministic_uuid(f"p3i:assignment:{tenant_id}:{employee_id}"),
                "tenant_id": tenant_id,
                "employee_id": employee_id,
                "legal_entity_id": default_entities[tenant_id][0],
                "branch_id": branch_by_tenant[tenant_id],
                "department_id": department_by_key[(tenant_id, _legacy_key(row["department"]))],
                "position_id": position_by_key[(tenant_id, _legacy_key(row["position"]))],
                "manager_user_id": None,
                "supersedes_assignment_id": None,
                "effective_from": row["employment_start_date"],
                "effective_to": (
                    end_date + timedelta(days=1)
                    if row["status"] == "terminated" and end_date is not None
                    else None
                ),
                "change_reason": "P3I legacy employee backfill",
                "created_by_user_id": None,
            }
        )
    connection.execute(sa.insert(_assignments), assignment_rows)


def _backfill_sqlite_catalog(
    *,
    employee_rows: list[RowMapping],
    tenant_ids: list[UUID],
    legacy_column: str,
    catalog_table: TableClause,
    catalog_label_column: str,
    catalog_kind: str,
) -> dict[tuple[UUID, str], UUID]:
    existing_rows = list(
        op.get_bind()
        .execute(
            sa.select(
                catalog_table.c.id,
                catalog_table.c.tenant_id,
                catalog_table.c[catalog_label_column].label("label"),
            ).where(
                catalog_table.c.tenant_id.in_(tenant_ids),
                catalog_table.c.status == "active",
                catalog_table.c.archived_at.is_(None),
            )
        )
        .mappings()
    )
    catalog_by_key: dict[tuple[UUID, str], UUID] = {}
    for row in sorted(existing_rows, key=lambda item: str(item["id"])):
        key = (_as_uuid(row["tenant_id"]), _legacy_key(row["label"]))
        catalog_by_key.setdefault(key, _as_uuid(row["id"]))

    labels_by_key: dict[tuple[UUID, str], list[str]] = {}
    for row in employee_rows:
        tenant_id = _as_uuid(row["tenant_id"])
        raw_value = row[legacy_column]
        key = (tenant_id, _legacy_key(raw_value))
        labels_by_key.setdefault(key, []).append(_legacy_label(raw_value))

    insert_rows: list[dict[str, object]] = []
    for (tenant_id, legacy_key), labels in sorted(
        labels_by_key.items(),
        key=lambda item: (str(item[0][0]), item[0][1]),
    ):
        key = (tenant_id, legacy_key)
        if key in catalog_by_key:
            continue
        catalog_id = _deterministic_uuid(f"p3i:{catalog_kind}:{tenant_id}:{legacy_key}")
        catalog_by_key[key] = catalog_id
        insert_row: dict[str, object] = {
            "id": catalog_id,
            "tenant_id": tenant_id,
            "code": _legacy_code(f"p3i:{catalog_kind}-code:{tenant_id}:{legacy_key}"),
            catalog_label_column: min(labels)[:200],
            "status": "active",
            "archived_at": None,
        }
        if catalog_kind == "department":
            insert_row["parent_id"] = None
        insert_rows.append(insert_row)

    if insert_rows:
        op.get_bind().execute(sa.insert(catalog_table), insert_rows)
    return catalog_by_key


def _legacy_key(value: object) -> str:
    label = _legacy_label(value)
    # Match the generated ``lower(trim(...))`` normalization used by the catalog schema.
    return label.lower()


def _legacy_label(value: object) -> str:
    if value is None:
        return "Unspecified"
    label = str(value).strip()
    return label or "Unspecified"


def _deterministic_uuid(value: str) -> UUID:
    digest = hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()
    return UUID(digest)


def _legacy_code(value: str) -> str:
    digest = hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"LEGACY-{digest[:24]}"


def _as_uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _configure_postgresql_security() -> None:
    enable_forced_row_security(op, table_name=_ASSIGNMENTS_TABLE)
    create_tenant_isolation_policy(
        op,
        table_name=_ASSIGNMENTS_TABLE,
        policy_name=_TENANT_POLICY,
        role_name=TENANT_APPLICATION_ROLE,
    )
    grant_table_privileges(
        op,
        table_name=_ASSIGNMENTS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT"),
    )
    grant_column_privilege(
        op,
        table_name=_ASSIGNMENTS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_ASSIGNMENT_UPDATE_COLUMNS,
    )


def _remove_postgresql_security() -> None:
    revoke_column_privilege(
        op,
        table_name=_ASSIGNMENTS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_ASSIGNMENT_UPDATE_COLUMNS,
    )
    revoke_table_privileges(
        op,
        table_name=_ASSIGNMENTS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privileges=("SELECT", "INSERT"),
    )
    drop_policy(
        op,
        table_name=_ASSIGNMENTS_TABLE,
        policy_name=_TENANT_POLICY,
    )


def _reset_postgresql_acl() -> None:
    quoted_columns = ", ".join(f'"{column_name}"' for column_name in _ASSIGNMENT_COLUMNS)
    op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{_ASSIGNMENTS_TABLE}" FROM PUBLIC'))
    op.execute(
        sa.text(
            f'REVOKE ALL PRIVILEGES ({quoted_columns}) ON TABLE "{_ASSIGNMENTS_TABLE}" FROM PUBLIC'
        )
    )
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
    ):
        revoke_all_table_privileges(
            op,
            table_name=_ASSIGNMENTS_TABLE,
            role_name=role_name,
        )
        revoke_all_column_privileges(
            op,
            table_name=_ASSIGNMENTS_TABLE,
            role_name=role_name,
            column_names=_ASSIGNMENT_COLUMNS,
        )


def _create_integrity_trigger() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_INTEGRITY_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            VOLATILE
            SECURITY INVOKER
            SET search_path = pg_catalog, public
            AS $p3i_employee_assignment_integrity$
            DECLARE
                locked_tenant_id uuid;
                employee_status text;
                employee_archived_at timestamptz;
                employee_start_date date;
                employee_end_date date;
                historical_import_allowed boolean := false;
                legal_entity_status text;
                branch_status text;
                branch_archived_at timestamptz;
                branch_legal_entity_id uuid;
                department_status text;
                department_archived_at timestamptz;
                position_status text;
                position_archived_at timestamptz;
                manager_status text;
                predecessor_employee_id uuid;
                predecessor_effective_to date;
            BEGIN
                -- Serialize organization/reporting-line changes for a tenant before validating
                -- mutable catalog state. Services take this same sentinel lock before audit writes.
                SELECT tenant.id INTO locked_tenant_id
                FROM public.tenants AS tenant
                WHERE tenant.id = NEW.tenant_id
                FOR UPDATE OF tenant;

                IF NOT FOUND THEN
                    RAISE EXCEPTION 'Employee assignment tenant does not exist'
                        USING ERRCODE = '23503',
                              SCHEMA = 'public',
                              TABLE = 'employee_assignments',
                              CONSTRAINT = 'fk_employee_assignments_tenant_id_tenants';
                END IF;

                IF TG_OP = 'UPDATE' THEN
                    IF NEW.id IS DISTINCT FROM OLD.id
                       OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                       OR NEW.employee_id IS DISTINCT FROM OLD.employee_id
                       OR NEW.legal_entity_id IS DISTINCT FROM OLD.legal_entity_id
                       OR NEW.branch_id IS DISTINCT FROM OLD.branch_id
                       OR NEW.department_id IS DISTINCT FROM OLD.department_id
                       OR NEW.position_id IS DISTINCT FROM OLD.position_id
                       OR NEW.manager_user_id IS DISTINCT FROM OLD.manager_user_id
                       OR NEW.supersedes_assignment_id IS DISTINCT FROM OLD.supersedes_assignment_id
                       OR NEW.effective_from IS DISTINCT FROM OLD.effective_from
                       OR NEW.change_reason IS DISTINCT FROM OLD.change_reason
                       OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
                       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                        RAISE EXCEPTION 'Employee assignment history is structurally immutable'
                            USING ERRCODE = '23514',
                                  SCHEMA = 'public',
                                  TABLE = 'employee_assignments',
                                  CONSTRAINT = 'ck_employee_assignments_immutable_history';
                    END IF;

                    IF OLD.effective_to IS NOT NULL OR NEW.effective_to IS NULL THEN
                        RAISE EXCEPTION 'Only an open assignment interval may be closed once'
                            USING ERRCODE = '23514',
                                  SCHEMA = 'public',
                                  TABLE = 'employee_assignments',
                                  CONSTRAINT = 'ck_employee_assignments_close_open_interval';
                    END IF;

                    RETURN NEW;
                END IF;

                SELECT employee.status,
                       employee.archived_at,
                       employee.employment_start_date,
                       employee.employment_end_date
                INTO employee_status,
                     employee_archived_at,
                     employee_start_date,
                     employee_end_date
                FROM public.employees AS employee
                WHERE employee.tenant_id = NEW.tenant_id
                  AND employee.id = NEW.employee_id;

                IF NOT FOUND THEN
                    RAISE EXCEPTION 'Only a current, non-archived employee may be assigned'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'employee_assignments',
                              CONSTRAINT = 'ck_employee_assignments_employee_assignable';
                END IF;

                -- Local owner-run demo/import tooling may bootstrap the exact closed employment
                -- interval for a retained terminated employee. The tenant runtime role can never
                -- use this path, and archived employees remain ineligible for new rows.
                historical_import_allowed :=
                    current_user <> '{TENANT_APPLICATION_ROLE}'
                    AND employee_status = 'terminated'
                    AND employee_archived_at IS NULL
                    AND employee_end_date IS NOT NULL
                    AND NEW.effective_from = employee_start_date
                    AND NEW.effective_to = employee_end_date + 1
                    AND NEW.supersedes_assignment_id IS NULL
                    AND NEW.created_by_user_id IS NULL;

                IF NEW.effective_to IS NOT NULL AND NOT historical_import_allowed THEN
                    RAISE EXCEPTION 'New employee assignments must be open-ended'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'employee_assignments',
                              CONSTRAINT = 'ck_employee_assignments_runtime_insert_open';
                END IF;

                IF employee_archived_at IS NOT NULL
                   OR (
                       employee_status NOT IN ('active', 'on_leave')
                       AND NOT historical_import_allowed
                   ) THEN
                    RAISE EXCEPTION 'Only a current, non-archived employee may be assigned'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'employee_assignments',
                              CONSTRAINT = 'ck_employee_assignments_employee_assignable';
                END IF;

                SELECT legal_entity.status
                INTO legal_entity_status
                FROM public.legal_entities AS legal_entity
                WHERE legal_entity.tenant_id = NEW.tenant_id
                  AND legal_entity.id = NEW.legal_entity_id;

                IF NOT FOUND OR legal_entity_status <> 'active' THEN
                    RAISE EXCEPTION 'Only an active legal entity may be newly assigned'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'employee_assignments',
                              CONSTRAINT = 'ck_employee_assignments_legal_entity_assignable';
                END IF;

                SELECT branch.status, branch.archived_at, branch.legal_entity_id
                INTO branch_status, branch_archived_at, branch_legal_entity_id
                FROM public.branches AS branch
                WHERE branch.tenant_id = NEW.tenant_id
                  AND branch.id = NEW.branch_id;

                IF NOT FOUND
                   OR branch_status <> 'active'
                   OR branch_archived_at IS NOT NULL
                   OR branch_legal_entity_id IS DISTINCT FROM NEW.legal_entity_id THEN
                    RAISE EXCEPTION
                        'Branch must be active and belong to the assigned legal entity'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'employee_assignments',
                              CONSTRAINT = 'ck_employee_assignments_branch_assignable';
                END IF;

                SELECT department.status, department.archived_at
                INTO department_status, department_archived_at
                FROM public.departments AS department
                WHERE department.tenant_id = NEW.tenant_id
                  AND department.id = NEW.department_id;

                IF NOT FOUND
                   OR department_status <> 'active'
                   OR department_archived_at IS NOT NULL THEN
                    RAISE EXCEPTION 'Only an active department may be newly assigned'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'employee_assignments',
                              CONSTRAINT = 'ck_employee_assignments_department_assignable';
                END IF;

                SELECT position.status, position.archived_at
                INTO position_status, position_archived_at
                FROM public.positions AS position
                WHERE position.tenant_id = NEW.tenant_id
                  AND position.id = NEW.position_id;

                IF NOT FOUND
                   OR position_status <> 'active'
                   OR position_archived_at IS NOT NULL THEN
                    RAISE EXCEPTION 'Only an active position may be newly assigned'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'employee_assignments',
                              CONSTRAINT = 'ck_employee_assignments_position_assignable';
                END IF;

                IF NEW.manager_user_id IS NOT NULL THEN
                    SELECT tenant_user.status
                    INTO manager_status
                    FROM public.users AS tenant_user
                    WHERE tenant_user.tenant_id = NEW.tenant_id
                      AND tenant_user.id = NEW.manager_user_id;

                    IF NOT FOUND OR manager_status <> 'active' THEN
                        RAISE EXCEPTION 'Only an active tenant user may be an assignment manager'
                            USING ERRCODE = '23514',
                                  SCHEMA = 'public',
                                  TABLE = 'employee_assignments',
                                  CONSTRAINT = 'ck_employee_assignments_manager_assignable';
                    END IF;
                END IF;

                IF NEW.supersedes_assignment_id IS NULL
                   AND EXISTS (
                       SELECT 1
                       FROM public.employee_assignments AS existing_assignment
                       WHERE existing_assignment.tenant_id = NEW.tenant_id
                         AND existing_assignment.employee_id = NEW.employee_id
                   ) THEN
                    RAISE EXCEPTION
                        'A later employee assignment must identify its predecessor'
                        USING ERRCODE = '23514',
                              SCHEMA = 'public',
                              TABLE = 'employee_assignments',
                              CONSTRAINT = 'ck_employee_assignments_predecessor_chain';
                END IF;

                IF NEW.supersedes_assignment_id IS NOT NULL THEN
                    SELECT predecessor.employee_id, predecessor.effective_to
                    INTO predecessor_employee_id, predecessor_effective_to
                    FROM public.employee_assignments AS predecessor
                    WHERE predecessor.tenant_id = NEW.tenant_id
                      AND predecessor.id = NEW.supersedes_assignment_id
                    FOR SHARE;

                    IF NOT FOUND
                       OR predecessor_employee_id IS DISTINCT FROM NEW.employee_id
                       OR predecessor_effective_to IS DISTINCT FROM NEW.effective_from THEN
                        RAISE EXCEPTION
                            'A successor must continue the same employee at its exclusive boundary'
                            USING ERRCODE = '23514',
                                  SCHEMA = 'public',
                                  TABLE = 'employee_assignments',
                                  CONSTRAINT = 'ck_employee_assignments_predecessor_chain';
                    END IF;
                END IF;

                RETURN NEW;
            END
            $p3i_employee_assignment_integrity$
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER {_INTEGRITY_TRIGGER} "
            f"BEFORE INSERT OR UPDATE ON public.{_ASSIGNMENTS_TABLE} "
            "FOR EACH ROW "
            f"EXECUTE FUNCTION public.{_INTEGRITY_FUNCTION}()"
        )
    )
    op.execute(sa.text(f"REVOKE ALL ON FUNCTION public.{_INTEGRITY_FUNCTION}() FROM PUBLIC"))
    op.execute(
        sa.text(
            f"GRANT EXECUTE ON FUNCTION public.{_INTEGRITY_FUNCTION}() "
            f'TO "{TENANT_APPLICATION_ROLE}"'
        )
    )


def _drop_integrity_trigger() -> None:
    op.execute(
        sa.text(
            f"REVOKE EXECUTE ON FUNCTION public.{_INTEGRITY_FUNCTION}() "
            f'FROM "{TENANT_APPLICATION_ROLE}"'
        )
    )
    op.execute(
        sa.text(f"DROP TRIGGER IF EXISTS {_INTEGRITY_TRIGGER} ON public.{_ASSIGNMENTS_TABLE}")
    )
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS public.{_INTEGRITY_FUNCTION}()"))


def _assert_backfill_complete() -> None:
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                """
                DO $p3i_backfill_preflight$
                BEGIN
                    IF (SELECT count(*) FROM employees)
                       <> (SELECT count(*) FROM employee_assignments) THEN
                        RAISE EXCEPTION
                            'P3I employee assignment backfill failed; every legacy employee '
                            'must have exactly one initial assignment';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM employees AS employee
                        LEFT JOIN employee_assignments AS assignment
                          ON assignment.tenant_id = employee.tenant_id
                         AND assignment.employee_id = employee.id
                        WHERE assignment.id IS NULL
                    ) THEN
                        RAISE EXCEPTION
                            'P3I employee assignment backfill failed; an employee is unmapped';
                    END IF;
                END
                $p3i_backfill_preflight$
                """
            )
        )
        return

    connection = op.get_bind()
    employee_count = int(connection.scalar(sa.select(sa.func.count()).select_from(_employees)) or 0)
    assignment_count = int(
        connection.scalar(sa.select(sa.func.count()).select_from(_assignments)) or 0
    )
    missing_count = int(
        connection.scalar(
            sa.select(sa.func.count())
            .select_from(
                _employees.outerjoin(
                    _assignments,
                    sa.and_(
                        _assignments.c.tenant_id == _employees.c.tenant_id,
                        _assignments.c.employee_id == _employees.c.id,
                    ),
                )
            )
            .where(_assignments.c.id.is_(None))
        )
        or 0
    )
    if employee_count == assignment_count and missing_count == 0:
        return
    raise RuntimeError(
        "P3I employee assignment backfill failed; every legacy employee must have exactly "
        "one initial assignment: "
        f"employees={employee_count}, assignments={assignment_count}, missing={missing_count}"
    )


def _assert_downgrade_is_safe() -> None:
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                """
                DO $p3i_downgrade_preflight$
                BEGIN
                    IF EXISTS (SELECT 1 FROM employee_assignments) THEN
                        RAISE EXCEPTION
                            'P3I downgrade preflight failed; export and remove retained '
                            'employee assignment history before retrying';
                    END IF;
                END
                $p3i_downgrade_preflight$
                """
            )
        )
        return

    assignment_count = int(
        op.get_bind().scalar(sa.select(sa.func.count()).select_from(_assignments)) or 0
    )
    if assignment_count == 0:
        return
    raise RuntimeError(
        "P3I downgrade preflight failed; export and remove retained employee assignment "
        f"history before retrying: employee_assignments={assignment_count}"
    )


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
