from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.platform.db import constraint_name_from_error, sqlstate_from_error
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"
PRE_P4B_REVISION = "0032_p4a_employee_directory"
P4B_REVISION = "0033_p4b_employee_profiles"

TENANT_A_ID = UUID("b4000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("b4000000-0000-4000-8000-000000000002")
ACTIVE_EMPLOYEE_A_ID = UUID("b4100000-0000-4000-8000-000000000001")
ARCHIVED_EMPLOYEE_A_ID = UUID("b4100000-0000-4000-8000-000000000002")
TERMINATED_EMPLOYEE_A_ID = UUID("b4100000-0000-4000-8000-000000000003")
ACTIVE_EMPLOYEE_B_ID = UUID("b4100000-0000-4000-8000-000000000004")

PROFILE_TABLES = ("employee_profiles", "employee_employments")
EXPECTED_COLUMNS = {
    "employee_profiles": {
        "id",
        "tenant_id",
        "employee_id",
        "preferred_name",
        "birth_date",
        "phone",
        "version",
        "created_at",
        "updated_at",
    },
    "employee_employments": {
        "id",
        "tenant_id",
        "employee_id",
        "contract_type",
        "work_type",
        "version",
        "created_at",
        "updated_at",
    },
}


def test_p4b_postgresql_backfill_catalog_constraints_rls_acl_and_safe_round_trip(
    postgres_database_url: URL,
) -> None:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_P4B_REVISION)
    asyncio.run(_seed_pre_p4b_fixture(postgres_database_url))
    asyncio.run(_grant_hostile_default_table_privileges(postgres_database_url))
    alembic_command.upgrade(config, P4B_REVISION)

    asyncio.run(_assert_p4b_postgresql_contract(postgres_database_url))

    alembic_command.downgrade(config, PRE_P4B_REVISION)
    assert asyncio.run(_current_revision(postgres_database_url)) == PRE_P4B_REVISION
    assert asyncio.run(_profile_table_presence(postgres_database_url)) == {
        "employee_profiles": False,
        "employee_employments": False,
    }
    assert asyncio.run(_employee_count(postgres_database_url)) == 4

    alembic_command.upgrade(config, P4B_REVISION)
    assert asyncio.run(_profile_counts(postgres_database_url)) == {
        "employee_profiles": 4,
        "employee_employments": 4,
    }


def test_p4b_postgresql_downgrade_refuses_changed_profiles_and_restores_force_rls(
    postgres_database_url: URL,
) -> None:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_P4B_REVISION)
    asyncio.run(_seed_pre_p4b_fixture(postgres_database_url))
    alembic_command.upgrade(config, P4B_REVISION)
    asyncio.run(_change_profile_state(postgres_database_url))

    with pytest.raises(
        RuntimeError,
        match="P4B employee profile downgrade refused",
    ):
        alembic_command.downgrade(config, PRE_P4B_REVISION)

    assert asyncio.run(_current_revision(postgres_database_url)) == P4B_REVISION
    assert asyncio.run(_row_security_flags(postgres_database_url)) == {
        "employee_profiles": (True, True),
        "employee_employments": (True, True),
    }
    assert asyncio.run(
        _single_table_row_security_flags(postgres_database_url, "employees")
    ) == (True, True)
    assert asyncio.run(_changed_profile_state(postgres_database_url)) == {
        "personal": ("Ada", 2),
        "employment": ("fixed_term", 2),
    }


async def _assert_p4b_postgresql_contract(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        await _assert_backfill(engine)
        await _assert_catalog(engine)
        await _assert_constraints(engine)
        await _assert_tenant_rls(engine)
    finally:
        await engine.dispose()


async def _assert_backfill(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    text(
                        "select e.id, e.tenant_id, e.status, e.archived_at is not null, "
                        "p.employee_id, p.tenant_id, p.preferred_name, p.birth_date, "
                        "p.phone, p.version, m.employee_id, m.tenant_id, "
                        "m.contract_type, m.work_type, m.version "
                        "from employees as e "
                        "join employee_profiles as p "
                        "on p.tenant_id = e.tenant_id and p.employee_id = e.id "
                        "join employee_employments as m "
                        "on m.tenant_id = e.tenant_id and m.employee_id = e.id "
                        "order by e.id"
                    )
                )
            )
            .tuples()
            .all()
        )
        pair_counts = {
            row.table_name: row.row_count
            for row in (
                await connection.execute(
                    text(
                        "select 'employee_profiles' as table_name, count(*) as row_count "
                        "from employee_profiles union all "
                        "select 'employee_employments', count(*) "
                        "from employee_employments"
                    )
                )
            )
        }

    assert pair_counts == {
        "employee_profiles": 4,
        "employee_employments": 4,
    }
    assert [(row[0], row[2], row[3]) for row in rows] == [
        (ACTIVE_EMPLOYEE_A_ID, "active", False),
        (ARCHIVED_EMPLOYEE_A_ID, "active", True),
        (TERMINATED_EMPLOYEE_A_ID, "terminated", False),
        (ACTIVE_EMPLOYEE_B_ID, "active", False),
    ]
    for row in rows:
        assert row[4:10] == (row[0], row[1], None, None, None, 1)
        assert row[10:15] == (row[0], row[1], None, None, 1)


async def _assert_catalog(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        column_rows = (
            (
                await connection.execute(
                    text(
                        "select table_name, column_name, data_type, is_nullable, "
                        "column_default from information_schema.columns "
                        "where table_schema = 'public' "
                        "and table_name in ('employee_profiles', 'employee_employments')"
                    )
                )
            )
            .mappings()
            .all()
        )
        columns = {
            table_name: {
                row["column_name"]: row for row in column_rows if row["table_name"] == table_name
            }
            for table_name in PROFILE_TABLES
        }
        for table_name in PROFILE_TABLES:
            assert set(columns[table_name]) == EXPECTED_COLUMNS[table_name]
            assert columns[table_name]["id"]["data_type"] == "uuid"
            assert columns[table_name]["tenant_id"]["data_type"] == "uuid"
            assert columns[table_name]["employee_id"]["data_type"] == "uuid"
            assert columns[table_name]["version"]["data_type"] == "integer"
            assert columns[table_name]["version"]["column_default"] == "1"
            for required_column in (
                "id",
                "tenant_id",
                "employee_id",
                "version",
                "created_at",
                "updated_at",
            ):
                assert columns[table_name][required_column]["is_nullable"] == "NO"
            for timestamp_column in ("created_at", "updated_at"):
                assert columns[table_name][timestamp_column]["data_type"] == (
                    "timestamp with time zone"
                )
                assert columns[table_name][timestamp_column]["column_default"] is not None
        assert columns["employee_profiles"]["birth_date"]["data_type"] == "date"

        constraints = {
            row["constraint_name"]: (row["table_name"], row["constraint_type"])
            for row in (
                (
                    await connection.execute(
                        text(
                            "select table_name, constraint_name, constraint_type "
                            "from information_schema.table_constraints "
                            "where table_schema = 'public' "
                            "and table_name in "
                            "('employee_profiles', 'employee_employments')"
                        )
                    )
                )
                .mappings()
                .all()
            )
        }
        for table_name in PROFILE_TABLES:
            assert constraints[f"ck_{table_name}_version_positive"] == (
                table_name,
                "CHECK",
            )
            assert constraints[f"uq_{table_name}_tenant_id_id"] == (
                table_name,
                "UNIQUE",
            )
            assert constraints[f"uq_{table_name}_tenant_employee_id"] == (
                table_name,
                "UNIQUE",
            )
            assert constraints[f"fk_{table_name}_tenant_id_tenants"] == (
                table_name,
                "FOREIGN KEY",
            )
            assert constraints[f"fk_{table_name}_tenant_employee_id_employees"] == (
                table_name,
                "FOREIGN KEY",
            )

        foreign_keys = {
            row.constraint_name: row.definition
            for row in (
                await connection.execute(
                    text(
                        "select constraint_record.conname as constraint_name, "
                        "pg_get_constraintdef(constraint_record.oid) as definition "
                        "from pg_catalog.pg_constraint as constraint_record "
                        "join pg_catalog.pg_class as table_record "
                        "on table_record.oid = constraint_record.conrelid "
                        "where table_record.relname in "
                        "('employee_profiles', 'employee_employments') "
                        "and constraint_record.contype = 'f'"
                    )
                )
            )
        }
        for table_name in PROFILE_TABLES:
            assert foreign_keys[f"fk_{table_name}_tenant_id_tenants"] == (
                "FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE"
            )
            assert foreign_keys[f"fk_{table_name}_tenant_employee_id_employees"] == (
                "FOREIGN KEY (tenant_id, employee_id) "
                "REFERENCES employees(tenant_id, id) ON DELETE RESTRICT"
            )

        index_names = set(
            await connection.scalars(
                text(
                    "select indexname from pg_catalog.pg_indexes "
                    "where schemaname = 'public' "
                    "and tablename in ('employee_profiles', 'employee_employments')"
                )
            )
        )
        for table_name in PROFILE_TABLES:
            assert {
                f"pk_{table_name}",
                f"uq_{table_name}_tenant_id_id",
                f"uq_{table_name}_tenant_employee_id",
            } <= index_names

            row_security = (
                await connection.execute(
                    text(
                        "select relrowsecurity, relforcerowsecurity "
                        "from pg_catalog.pg_class "
                        "where oid = cast(:table_name as regclass)"
                    ),
                    {"table_name": f"public.{table_name}"},
                )
            ).one()
            assert row_security == (True, True)

            policy = (
                (
                    await connection.execute(
                        text(
                            "select policyname, roles, cmd, qual, with_check "
                            "from pg_catalog.pg_policies "
                            "where schemaname = 'public' and tablename = :table_name"
                        ),
                        {"table_name": table_name},
                    )
                )
                .mappings()
                .one()
            )
            assert policy["policyname"] == "tenant_isolation_app"
            assert tuple(policy["roles"]) == (TENANT_APPLICATION_ROLE,)
            assert policy["cmd"] == "ALL"
            assert "app.tenant_id" in policy["qual"]
            assert policy["with_check"] == policy["qual"]

            assert await _table_privileges(
                connection,
                table_name=table_name,
                role_name=TENANT_APPLICATION_ROLE,
            ) == {"SELECT", "INSERT"}
            expected_update_columns = {
                "employee_profiles": {
                    "preferred_name",
                    "birth_date",
                    "phone",
                    "version",
                    "updated_at",
                },
                "employee_employments": {
                    "contract_type",
                    "work_type",
                    "version",
                    "updated_at",
                },
            }[table_name]
            assert await _column_update_privileges(
                connection,
                table_name=table_name,
                role_name=TENANT_APPLICATION_ROLE,
            ) == expected_update_columns
            for role_name in (
                PLATFORM_APPLICATION_ROLE,
                AUTHENTICATION_APPLICATION_ROLE,
                "PUBLIC",
            ):
                assert (
                    await _table_privileges(
                        connection,
                        table_name=table_name,
                        role_name=role_name,
                    )
                    == set()
                )
                assert (
                    await _column_update_privileges(
                        connection,
                        table_name=table_name,
                        role_name=role_name,
                    )
                    == set()
                )

        employee_row_security = (
            await connection.execute(
                text(
                    "select relrowsecurity, relforcerowsecurity "
                    "from pg_catalog.pg_class where oid = 'public.employees'::regclass"
                )
            )
        ).one()
        assert employee_row_security == (True, True)


async def _assert_constraints(engine: AsyncEngine) -> None:
    for table_name in PROFILE_TABLES:
        await _assert_rejected_mutation(
            engine,
            text(
                f"insert into {table_name} (id, tenant_id, employee_id, version) "
                "values (:id, :tenant_id, :employee_id, 1)"
            ),
            {
                "id": uuid4(),
                "tenant_id": TENANT_A_ID,
                "employee_id": ACTIVE_EMPLOYEE_A_ID,
            },
            sqlstate="23505",
            constraint_name=f"uq_{table_name}_tenant_employee_id",
        )
        await _assert_rejected_mutation(
            engine,
            text(
                f"update {table_name} set version = 0 "
                "where tenant_id = :tenant_id and employee_id = :employee_id"
            ),
            {
                "tenant_id": TENANT_A_ID,
                "employee_id": ACTIVE_EMPLOYEE_A_ID,
            },
            sqlstate="23514",
            constraint_name=f"ck_{table_name}_version_positive",
        )
        if table_name == "employee_employments":
            for column_name, invalid_value in (
                ("contract_type", "contractor"),
                ("work_type", "hybrid"),
            ):
                await _assert_rejected_mutation(
                    engine,
                    text(
                        f"update employee_employments set {column_name} = :invalid_value "
                        "where tenant_id = :tenant_id and employee_id = :employee_id"
                    ),
                    {
                        "invalid_value": invalid_value,
                        "tenant_id": TENANT_A_ID,
                        "employee_id": ACTIVE_EMPLOYEE_A_ID,
                    },
                    sqlstate="23514",
                    constraint_name=f"ck_employee_employments_{column_name}",
                )
        await _assert_rejected_mutation(
            engine,
            text(
                f"insert into {table_name} (id, tenant_id, employee_id, version) "
                "values (:id, :tenant_id, :employee_id, 1)"
            ),
            {
                "id": uuid4(),
                "tenant_id": TENANT_A_ID,
                "employee_id": ACTIVE_EMPLOYEE_B_ID,
            },
            sqlstate="23503",
            constraint_name=f"fk_{table_name}_tenant_employee_id_employees",
        )


async def _assert_tenant_rls(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        for table_name in PROFILE_TABLES:
            assert await connection.scalar(text(f"select count(*) from {table_name}")) == 3

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_B_ID)
        for table_name in PROFILE_TABLES:
            assert await connection.scalar(text(f"select count(*) from {table_name}")) == 1
            assert (
                await connection.scalar(
                    text(f"select count(*) from {table_name} where employee_id = :employee_id"),
                    {"employee_id": ACTIVE_EMPLOYEE_A_ID},
                )
                == 0
            )
            update = await connection.execute(
                text(
                    f"update {table_name} set updated_at = updated_at "
                    "where employee_id = :employee_id"
                ),
                {"employee_id": ACTIVE_EMPLOYEE_A_ID},
            )
            assert update.rowcount == 0

    for table_name in PROFILE_TABLES:
        with pytest.raises(DBAPIError) as cross_tenant_insert:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_B_ID)
                await connection.execute(
                    text(
                        f"insert into {table_name} "
                        "(id, tenant_id, employee_id, version) "
                        "values (:id, :tenant_id, :employee_id, 1)"
                    ),
                    {
                        "id": uuid4(),
                        "tenant_id": TENANT_B_ID,
                        "employee_id": ACTIVE_EMPLOYEE_A_ID,
                    },
                )
        assert sqlstate_from_error(cross_tenant_insert.value) == "23503"
        assert constraint_name_from_error(cross_tenant_insert.value) == (
            f"fk_{table_name}_tenant_employee_id_employees"
        )


async def _assert_rejected_mutation(
    engine: AsyncEngine,
    statement,
    parameters: dict[str, object],
    *,
    sqlstate: str,
    constraint_name: str,
) -> None:
    with pytest.raises(DBAPIError) as error:
        async with engine.begin() as connection:
            await connection.execute(statement, parameters)
    assert sqlstate_from_error(error.value) == sqlstate
    assert constraint_name_from_error(error.value) == constraint_name


async def _seed_pre_p4b_fixture(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone"
                    ") values "
                    "(:tenant_a, 'p4b-tenant-a', 'P4B Tenant A', 'active', "
                    "'core', 'tr-1', 'en-US', 'UTC'), "
                    "(:tenant_b, 'p4b-tenant-b', 'P4B Tenant B', 'active', "
                    "'core', 'tr-1', 'en-US', 'UTC')"
                ),
                {"tenant_a": TENANT_A_ID, "tenant_b": TENANT_B_ID},
            )
            await _insert_employee(
                connection,
                employee_id=ACTIVE_EMPLOYEE_A_ID,
                tenant_id=TENANT_A_ID,
                employee_number="P4B-ACTIVE-A",
            )
            await _insert_employee(
                connection,
                employee_id=ARCHIVED_EMPLOYEE_A_ID,
                tenant_id=TENANT_A_ID,
                employee_number="P4B-ARCHIVED-A",
                archived_at=datetime(2026, 7, 11, 12, tzinfo=UTC),
            )
            await _insert_employee(
                connection,
                employee_id=TERMINATED_EMPLOYEE_A_ID,
                tenant_id=TENANT_A_ID,
                employee_number="P4B-TERMINATED-A",
                status="terminated",
                employment_end_date=date(2026, 7, 10),
            )
            await _insert_employee(
                connection,
                employee_id=ACTIVE_EMPLOYEE_B_ID,
                tenant_id=TENANT_B_ID,
                employee_number="P4B-ACTIVE-B",
            )
    finally:
        await engine.dispose()


async def _grant_hostile_default_table_privileges(database_url: URL) -> None:
    """Prove 0033 resets inherited defaults before granting its exact capability."""

    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            for role_name in (
                "PUBLIC",
                PLATFORM_APPLICATION_ROLE,
                AUTHENTICATION_APPLICATION_ROLE,
            ):
                quoted_role = (
                    "PUBLIC"
                    if role_name == "PUBLIC"
                    else connection.dialect.identifier_preparer.quote(role_name)
                )
                await connection.exec_driver_sql(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    f"GRANT ALL PRIVILEGES ON TABLES TO {quoted_role}"
                )
    finally:
        await engine.dispose()


async def _insert_employee(
    connection: AsyncConnection,
    *,
    employee_id: UUID,
    tenant_id: UUID,
    employee_number: str,
    status: str = "active",
    employment_end_date: date | None = None,
    archived_at: datetime | None = None,
) -> None:
    await connection.execute(
        text(
            "insert into employees ("
            "id, tenant_id, employee_number, first_name, last_name, email, status, "
            "employment_start_date, employment_end_date, archived_at"
            ") values ("
            ":id, :tenant_id, :employee_number, 'Ada', 'Employee', null, :status, "
            "DATE '2026-07-01', :employment_end_date, :archived_at"
            ")"
        ),
        {
            "id": employee_id,
            "tenant_id": tenant_id,
            "employee_number": employee_number,
            "status": status,
            "employment_end_date": employment_end_date,
            "archived_at": archived_at,
        },
    )


async def _change_profile_state(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "update employee_profiles set preferred_name = 'Ada', version = 2 "
                    "where tenant_id = :tenant_id and employee_id = :employee_id"
                ),
                {"tenant_id": TENANT_A_ID, "employee_id": ACTIVE_EMPLOYEE_A_ID},
            )
            await connection.execute(
                text(
                    "update employee_employments "
                    "set contract_type = 'fixed_term', version = 2 "
                    "where tenant_id = :tenant_id and employee_id = :employee_id"
                ),
                {"tenant_id": TENANT_A_ID, "employee_id": ACTIVE_EMPLOYEE_A_ID},
            )
    finally:
        await engine.dispose()


async def _changed_profile_state(database_url: URL) -> dict[str, tuple[object, ...]]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            personal = (
                await connection.execute(
                    text(
                        "select preferred_name, version from employee_profiles "
                        "where tenant_id = :tenant_id and employee_id = :employee_id"
                    ),
                    {"tenant_id": TENANT_A_ID, "employee_id": ACTIVE_EMPLOYEE_A_ID},
                )
            ).one()
            employment = (
                await connection.execute(
                    text(
                        "select contract_type, version from employee_employments "
                        "where tenant_id = :tenant_id and employee_id = :employee_id"
                    ),
                    {"tenant_id": TENANT_A_ID, "employee_id": ACTIVE_EMPLOYEE_A_ID},
                )
            ).one()
            return {
                "personal": tuple(personal),
                "employment": tuple(employment),
            }
    finally:
        await engine.dispose()


async def _table_privileges(
    connection: AsyncConnection,
    *,
    table_name: str,
    role_name: str,
) -> set[str]:
    privileges: set[str] = set()
    for privilege in (
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "TRUNCATE",
        "REFERENCES",
        "TRIGGER",
    ):
        if role_name == "PUBLIC":
            has_privilege = await connection.scalar(
                text(
                    "select exists (select 1 from information_schema.table_privileges "
                    "where table_schema = 'public' and table_name = :table_name "
                    "and grantee = 'PUBLIC' and privilege_type = :privilege)"
                ),
                {"table_name": table_name, "privilege": privilege},
            )
        else:
            has_privilege = await connection.scalar(
                text("select has_table_privilege(:role_name, :table_name, :privilege)"),
                {
                    "role_name": role_name,
                    "table_name": f"public.{table_name}",
                    "privilege": privilege,
                },
            )
        if has_privilege:
            privileges.add(privilege)
    return privileges


async def _column_update_privileges(
    connection: AsyncConnection,
    *,
    table_name: str,
    role_name: str,
) -> set[str]:
    return set(
        await connection.scalars(
            text(
                "select column_name from information_schema.column_privileges "
                "where table_schema = 'public' and table_name = :table_name "
                "and grantee = :role_name and privilege_type = 'UPDATE'"
            ),
            {"table_name": table_name, "role_name": role_name},
        )
    )


async def _set_local_tenant_role(
    connection: AsyncConnection,
    tenant_id: UUID,
) -> None:
    quoted_role = connection.dialect.identifier_preparer.quote(TENANT_APPLICATION_ROLE)
    await connection.exec_driver_sql(f"SET LOCAL ROLE {quoted_role}")
    await connection.execute(
        text("select set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def _current_revision(database_url: URL) -> str | None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("select version_num from alembic_version"))
    finally:
        await engine.dispose()


async def _profile_table_presence(database_url: URL) -> dict[str, bool]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return {
                table_name: bool(
                    await connection.scalar(
                        text("select to_regclass(:table_name) is not null"),
                        {"table_name": f"public.{table_name}"},
                    )
                )
                for table_name in PROFILE_TABLES
            }
    finally:
        await engine.dispose()


async def _employee_count(database_url: URL) -> int:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return int(await connection.scalar(text("select count(*) from employees")))
    finally:
        await engine.dispose()


async def _profile_counts(database_url: URL) -> dict[str, int]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return {
                table_name: int(await connection.scalar(text(f"select count(*) from {table_name}")))
                for table_name in PROFILE_TABLES
            }
    finally:
        await engine.dispose()


async def _row_security_flags(
    database_url: URL,
) -> dict[str, tuple[bool, bool]]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "select relname, relrowsecurity, relforcerowsecurity "
                        "from pg_catalog.pg_class "
                        "where relname in "
                        "('employee_profiles', 'employee_employments')"
                    )
                )
            ).all()
            return {row[0]: (row[1], row[2]) for row in rows}
    finally:
        await engine.dispose()


async def _single_table_row_security_flags(
    database_url: URL,
    table_name: str,
) -> tuple[bool, bool]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "select relrowsecurity, relforcerowsecurity "
                        "from pg_catalog.pg_class where oid = cast(:table_name as regclass)"
                    ),
                    {"table_name": f"public.{table_name}"},
                )
            ).one()
            return bool(row[0]), bool(row[1])
    finally:
        await engine.dispose()


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config
