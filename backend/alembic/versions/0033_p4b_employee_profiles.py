"""add focused P4B employee personal and employment profiles

Revision ID: 0033_p4b_employee_profiles
Revises: 0032_p4a_employee_directory
Create Date: 2026-07-14
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
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

revision: str = "0033_p4b_employee_profiles"
down_revision: str | None = "0032_p4a_employee_directory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMPLOYEES_TABLE = "employees"
_PERSONAL_TABLE = "employee_profiles"
_EMPLOYMENT_TABLE = "employee_employments"
_PROFILE_TABLES = (_PERSONAL_TABLE, _EMPLOYMENT_TABLE)
_TENANT_POLICY = "tenant_isolation_app"
_UUID = postgresql.UUID(as_uuid=True)

_TABLE_COLUMNS = {
    _PERSONAL_TABLE: (
        "id",
        "tenant_id",
        "employee_id",
        "preferred_name",
        "birth_date",
        "phone",
        "version",
        "created_at",
        "updated_at",
    ),
    _EMPLOYMENT_TABLE: (
        "id",
        "tenant_id",
        "employee_id",
        "contract_type",
        "work_type",
        "version",
        "created_at",
        "updated_at",
    ),
}
_UPDATE_COLUMNS = {
    _PERSONAL_TABLE: (
        "preferred_name",
        "birth_date",
        "phone",
        "version",
        "updated_at",
    ),
    _EMPLOYMENT_TABLE: (
        "contract_type",
        "work_type",
        "version",
        "updated_at",
    ),
}


def upgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        # The migration owner is subject to FORCE RLS. Temporarily expose the complete
        # employee population for the transactional one-to-one backfill.
        disable_forced_row_security(op, table_name=_EMPLOYEES_TABLE)

    _assert_generated_ids_are_safe()
    _create_personal_profiles()
    _create_employment_profiles()
    _backfill_profiles()
    _assert_backfill_is_complete()

    if is_postgresql:
        for table_name in _PROFILE_TABLES:
            _reset_postgresql_acl(table_name)
            enable_forced_row_security(op, table_name=table_name)
            create_tenant_isolation_policy(
                op,
                table_name=table_name,
                policy_name=_TENANT_POLICY,
                role_name=TENANT_APPLICATION_ROLE,
            )
            grant_table_privileges(
                op,
                table_name=table_name,
                role_name=TENANT_APPLICATION_ROLE,
                privileges=("SELECT", "INSERT"),
            )
            grant_column_privilege(
                op,
                table_name=table_name,
                role_name=TENANT_APPLICATION_ROLE,
                privilege="UPDATE",
                column_names=_UPDATE_COLUMNS[table_name],
            )
        enable_forced_row_security(op, table_name=_EMPLOYEES_TABLE)


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        for table_name in _PROFILE_TABLES:
            disable_forced_row_security(op, table_name=table_name)

    _assert_downgrade_is_safe()

    if is_postgresql:
        for table_name in reversed(_PROFILE_TABLES):
            revoke_column_privilege(
                op,
                table_name=table_name,
                role_name=TENANT_APPLICATION_ROLE,
                privilege="UPDATE",
                column_names=_UPDATE_COLUMNS[table_name],
            )
            revoke_table_privileges(
                op,
                table_name=table_name,
                role_name=TENANT_APPLICATION_ROLE,
                privileges=("SELECT", "INSERT"),
            )
            drop_policy(
                op,
                table_name=table_name,
                policy_name=_TENANT_POLICY,
            )

    op.drop_table(_EMPLOYMENT_TABLE)
    op.drop_table(_PERSONAL_TABLE)


def _assert_generated_ids_are_safe() -> None:
    personal_uuid = (
        "md5('p4b:personal:' || tenant_id::text || ':' || id::text)::uuid"
    )
    employment_uuid = (
        "md5('p4b:employment:' || tenant_id::text || ':' || id::text)::uuid"
    )
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $p4b_employee_profile_id_preflight$
                BEGIN
                    IF EXISTS (
                        SELECT generated_id FROM (
                            SELECT {personal_uuid} AS generated_id FROM employees
                        ) AS generated_personal_ids
                        GROUP BY generated_id HAVING count(*) > 1
                    ) OR EXISTS (
                        SELECT generated_id FROM (
                            SELECT {employment_uuid} AS generated_id FROM employees
                        ) AS generated_employment_ids
                        GROUP BY generated_id HAVING count(*) > 1
                    ) THEN
                        RAISE EXCEPTION
                            'P4B employee profile preflight failed: generated_id_collision';
                    END IF;
                END
                $p4b_employee_profile_id_preflight$
                """
            )
        )
        return

    personal_ids: set[UUID] = set()
    employment_ids: set[UUID] = set()
    rows = op.get_bind().execute(
        sa.text("select tenant_id, id from employees order by tenant_id, id")
    ).mappings()
    for employee in rows:
        tenant_id = _as_uuid(employee["tenant_id"])
        employee_id = _as_uuid(employee["id"])
        personal_id = _deterministic_uuid(f"p4b:personal:{tenant_id}:{employee_id}")
        employment_id = _deterministic_uuid(
            f"p4b:employment:{tenant_id}:{employee_id}"
        )
        if personal_id in personal_ids or employment_id in employment_ids:
            raise RuntimeError(
                "P4B employee profile preflight failed: generated_id_collision"
            )
        personal_ids.add(personal_id)
        employment_ids.add(employment_id)


def _create_personal_profiles() -> None:
    op.create_table(
        _PERSONAL_TABLE,
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("employee_id", _UUID, nullable=False),
        sa.Column("preferred_name", sa.String(length=200), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
            "version > 0",
            name="ck_employee_profiles_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_employee_profiles_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_employee_profiles_tenant_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_employee_profiles"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_employee_profiles_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "employee_id",
            name="uq_employee_profiles_tenant_employee_id",
        ),
    )


def _create_employment_profiles() -> None:
    op.create_table(
        _EMPLOYMENT_TABLE,
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("employee_id", _UUID, nullable=False),
        sa.Column("contract_type", sa.String(length=32), nullable=True),
        sa.Column("work_type", sa.String(length=32), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
            "version > 0",
            name="ck_employee_employments_version_positive",
        ),
        sa.CheckConstraint(
            "contract_type is null or contract_type in ('indefinite','fixed_term')",
            name="ck_employee_employments_contract_type",
        ),
        sa.CheckConstraint(
            "work_type is null or work_type in ('full_time','part_time')",
            name="ck_employee_employments_work_type",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_employee_employments_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_employee_employments_tenant_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_employee_employments"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_employee_employments_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "employee_id",
            name="uq_employee_employments_tenant_employee_id",
        ),
    )


def _backfill_profiles() -> None:
    if op.get_context().as_sql:
        _render_postgresql_backfill()
        return

    connection = op.get_bind()
    employees = connection.execute(
        sa.text("select tenant_id, id from employees order by tenant_id, id")
    ).mappings()
    personal_rows: list[dict[str, object]] = []
    employment_rows: list[dict[str, object]] = []
    personal_ids: set[UUID] = set()
    employment_ids: set[UUID] = set()
    for employee in employees:
        tenant_id = _as_uuid(employee["tenant_id"])
        employee_id = _as_uuid(employee["id"])
        personal_id = _deterministic_uuid(f"p4b:personal:{tenant_id}:{employee_id}")
        employment_id = _deterministic_uuid(
            f"p4b:employment:{tenant_id}:{employee_id}"
        )
        if personal_id in personal_ids or employment_id in employment_ids:
            raise RuntimeError("P4B employee profile preflight failed: generated_id_collision")
        personal_ids.add(personal_id)
        employment_ids.add(employment_id)
        common = {"tenant_id": tenant_id, "employee_id": employee_id}
        personal_rows.append({"id": personal_id, **common})
        employment_rows.append({"id": employment_id, **common})

    if personal_rows:
        connection.execute(
            sa.insert(
                sa.table(
                    _PERSONAL_TABLE,
                    sa.column("id", _UUID),
                    sa.column("tenant_id", _UUID),
                    sa.column("employee_id", _UUID),
                )
            ),
            personal_rows,
        )
        connection.execute(
            sa.insert(
                sa.table(
                    _EMPLOYMENT_TABLE,
                    sa.column("id", _UUID),
                    sa.column("tenant_id", _UUID),
                    sa.column("employee_id", _UUID),
                )
            ),
            employment_rows,
        )


def _render_postgresql_backfill() -> None:
    personal_uuid = (
        "md5('p4b:personal:' || tenant_id::text || ':' || id::text)::uuid"
    )
    employment_uuid = (
        "md5('p4b:employment:' || tenant_id::text || ':' || id::text)::uuid"
    )
    op.execute(
        sa.text(
            f"INSERT INTO {_PERSONAL_TABLE} (id, tenant_id, employee_id) "
            f"SELECT {personal_uuid}, tenant_id, id FROM employees"
        )
    )
    op.execute(
        sa.text(
            f"INSERT INTO {_EMPLOYMENT_TABLE} (id, tenant_id, employee_id) "
            f"SELECT {employment_uuid}, tenant_id, id FROM employees"
        )
    )


def _assert_backfill_is_complete() -> None:
    missing_personal_sql = (
        "select count(*) from employees as e left join employee_profiles as p "
        "on p.tenant_id = e.tenant_id and p.employee_id = e.id where p.id is null"
    )
    missing_employment_sql = (
        "select count(*) from employees as e left join employee_employments as m "
        "on m.tenant_id = e.tenant_id and m.employee_id = e.id where m.id is null"
    )
    orphan_personal_sql = (
        "select count(*) from employee_profiles as p left join employees as e "
        "on e.tenant_id = p.tenant_id and e.id = p.employee_id where e.id is null"
    )
    orphan_employment_sql = (
        "select count(*) from employee_employments as m left join employees as e "
        "on e.tenant_id = m.tenant_id and e.id = m.employee_id where e.id is null"
    )
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $p4b_employee_profile_backfill_preflight$
                BEGIN
                    IF ({missing_personal_sql}) > 0
                       OR ({missing_employment_sql}) > 0
                       OR ({orphan_personal_sql}) > 0
                       OR ({orphan_employment_sql}) > 0 THEN
                        RAISE EXCEPTION 'P4B employee profile backfill failed';
                    END IF;
                END
                $p4b_employee_profile_backfill_preflight$
                """
            )
        )
        return

    connection = op.get_bind()
    counts = tuple(
        int(connection.scalar(sa.text(statement)) or 0)
        for statement in (
            missing_personal_sql,
            missing_employment_sql,
            orphan_personal_sql,
            orphan_employment_sql,
        )
    )
    if any(counts):
        raise RuntimeError(
            "P4B employee profile backfill failed: "
            f"missing_personal={counts[0]}, missing_employment={counts[1]}, "
            f"orphan_personal={counts[2]}, orphan_employment={counts[3]}"
        )


def _assert_downgrade_is_safe() -> None:
    personal_changes_sql = (
        "select count(*) from employee_profiles where version <> 1 "
        "or preferred_name is not null or birth_date is not null or phone is not null"
    )
    employment_changes_sql = (
        "select count(*) from employee_employments where version <> 1 "
        "or contract_type is not null or work_type is not null"
    )
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $p4b_employee_profile_downgrade_preflight$
                DECLARE
                    personal_change_count bigint;
                    employment_change_count bigint;
                BEGIN
                    personal_change_count := ({personal_changes_sql});
                    employment_change_count := ({employment_changes_sql});
                    IF personal_change_count > 0 OR employment_change_count > 0 THEN
                        RAISE EXCEPTION
                            'P4B employee profile downgrade refused: personal_changes=%, '
                            'employment_changes=%',
                            personal_change_count, employment_change_count;
                    END IF;
                END
                $p4b_employee_profile_downgrade_preflight$
                """
            )
        )
        return

    connection = op.get_bind()
    personal_changes = int(
        connection.scalar(sa.text(personal_changes_sql)) or 0
    )
    employment_changes = int(
        connection.scalar(sa.text(employment_changes_sql)) or 0
    )
    if personal_changes or employment_changes:
        raise RuntimeError(
            "P4B employee profile downgrade refused: "
            f"personal_changes={personal_changes}, "
            f"employment_changes={employment_changes}"
        )


def _reset_postgresql_acl(table_name: str) -> None:
    quoted_columns = ", ".join(
        f'"{column_name}"' for column_name in _TABLE_COLUMNS[table_name]
    )
    op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{table_name}" FROM PUBLIC'))
    op.execute(
        sa.text(
            f'REVOKE ALL PRIVILEGES ({quoted_columns}) '
            f'ON TABLE "{table_name}" FROM PUBLIC'
        )
    )
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
    ):
        revoke_all_table_privileges(
            op,
            table_name=table_name,
            role_name=role_name,
        )
        revoke_all_column_privileges(
            op,
            table_name=table_name,
            role_name=role_name,
            column_names=_TABLE_COLUMNS[table_name],
        )


def _deterministic_uuid(value: str) -> UUID:
    digest = hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()
    return UUID(digest)


def _as_uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
