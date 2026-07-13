from __future__ import annotations

import asyncio
from datetime import date
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
PRE_ORGANIZATION_REVISION = "0026_p3e_identity_checkpoint"

TENANT_A_ID = UUID("fa000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("fa000000-0000-4000-8000-000000000002")
BRANCH_A_ID = UUID("fa100000-0000-4000-8000-000000000001")
BRANCH_B_ID = UUID("fa100000-0000-4000-8000-000000000002")
ARCHIVED_BRANCH_A_ID = UUID("fa100000-0000-4000-8000-000000000003")
DEPARTMENT_A_ID = UUID("fa200000-0000-4000-8000-000000000001")
DEPARTMENT_B_ID = UUID("fa200000-0000-4000-8000-000000000002")
ARCHIVED_DEPARTMENT_A_ID = UUID("fa200000-0000-4000-8000-000000000003")
POSITION_A_ID = UUID("fa300000-0000-4000-8000-000000000001")
POSITION_B_ID = UUID("fa300000-0000-4000-8000-000000000002")
ARCHIVED_POSITION_A_ID = UUID("fa300000-0000-4000-8000-000000000003")
EMPLOYEE_A_ID = UUID("fa400000-0000-4000-8000-000000000001")
EMPLOYEE_B_ID = UUID("fa400000-0000-4000-8000-000000000002")
UNASSIGNED_EMPLOYEE_A_ID = UUID("fa400000-0000-4000-8000-000000000003")
TERMINATED_EMPLOYEE_A_ID = UUID("fa400000-0000-4000-8000-000000000004")
ASSIGNMENT_A_ID = UUID("fa500000-0000-4000-8000-000000000001")
ASSIGNMENT_B_ID = UUID("fa500000-0000-4000-8000-000000000002")
TERMINATED_ASSIGNMENT_A_ID = UUID("fa500000-0000-4000-8000-000000000003")

ASSIGNMENT_UPDATE_COLUMNS = frozenset({"effective_to", "updated_at"})
ALL_ASSIGNMENT_COLUMNS = frozenset(
    {
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
    }
)


@pytest.fixture
def p3i_postgres_database(postgres_database_url: URL) -> URL:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_ORGANIZATION_REVISION)
    asyncio.run(_seed_pre_organization_tenants(postgres_database_url))
    alembic_command.upgrade(config, "head")
    return postgres_database_url


def test_p3i_assignment_rls_acl_history_and_archived_reference_guards(
    p3i_postgres_database: URL,
) -> None:
    asyncio.run(_assert_p3i_postgresql_contract(p3i_postgres_database))


async def _assert_p3i_postgresql_contract(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        await _assert_security_catalog(engine)
        await _seed_runtime_records(engine)
        await _insert_assignment(
            engine,
            tenant_id=TENANT_A_ID,
            assignment_id=ASSIGNMENT_A_ID,
            employee_id=EMPLOYEE_A_ID,
            branch_id=BRANCH_A_ID,
            department_id=DEPARTMENT_A_ID,
            position_id=POSITION_A_ID,
        )
        await _insert_assignment(
            engine,
            tenant_id=TENANT_B_ID,
            assignment_id=ASSIGNMENT_B_ID,
            employee_id=EMPLOYEE_B_ID,
            branch_id=BRANCH_B_ID,
            department_id=DEPARTMENT_B_ID,
            position_id=POSITION_B_ID,
        )
        await _assert_tenant_isolation(engine)
        await _assert_archived_references_rejected(engine)
        await _assert_terminated_history_bootstrap_is_owner_only(engine)
        await _assert_history_is_immutable(engine)
    finally:
        await engine.dispose()


async def _assert_security_catalog(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        row_security = (
            await connection.execute(
                text(
                    "select class.relrowsecurity, class.relforcerowsecurity "
                    "from pg_catalog.pg_class as class "
                    "join pg_catalog.pg_namespace as namespace "
                    "on namespace.oid = class.relnamespace "
                    "where namespace.nspname = 'public' "
                    "and class.relname = 'employee_assignments'"
                )
            )
        ).one()
        assert row_security == (True, True)

        policy = (
            (
                await connection.execute(
                    text(
                        "select policyname, roles, cmd, qual, with_check "
                        "from pg_catalog.pg_policies "
                        "where schemaname = 'public' "
                        "and tablename = 'employee_assignments'"
                    )
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

        trigger = (
            await connection.execute(
                text(
                    "select trigger.tgname, trigger.tgenabled::text, procedure.proname, "
                    "procedure.prosecdef, procedure.provolatile::text "
                    "from pg_catalog.pg_trigger as trigger "
                    "join pg_catalog.pg_class as class on class.oid = trigger.tgrelid "
                    "join pg_catalog.pg_namespace as namespace "
                    "on namespace.oid = class.relnamespace "
                    "join pg_catalog.pg_proc as procedure "
                    "on procedure.oid = trigger.tgfoid "
                    "where namespace.nspname = 'public' "
                    "and class.relname = 'employee_assignments' "
                    "and not trigger.tgisinternal"
                )
            )
        ).one()
        assert trigger == (
            "trg_employee_assignments_integrity",
            "O",
            "enforce_employee_assignment_integrity",
            False,
            "v",
        )

        assert await _table_privileges(
            connection,
            role_name=TENANT_APPLICATION_ROLE,
        ) == {"SELECT", "INSERT"}
        for role_name in (
            PLATFORM_APPLICATION_ROLE,
            AUTHENTICATION_APPLICATION_ROLE,
        ):
            assert await _table_privileges(connection, role_name=role_name) == set()

        for column_name in ALL_ASSIGNMENT_COLUMNS:
            has_update = bool(
                await connection.scalar(
                    text(
                        "select has_column_privilege("
                        ":role_name, 'public.employee_assignments', "
                        ":column_name, 'UPDATE')"
                    ),
                    {
                        "role_name": TENANT_APPLICATION_ROLE,
                        "column_name": column_name,
                    },
                )
            )
            assert has_update is (column_name in ASSIGNMENT_UPDATE_COLUMNS)

        assert bool(
            await connection.scalar(
                text(
                    "select has_function_privilege("
                    ":role_name, 'public.enforce_employee_assignment_integrity()', "
                    "'EXECUTE')"
                ),
                {"role_name": TENANT_APPLICATION_ROLE},
            )
        )
        for role_name in (
            PLATFORM_APPLICATION_ROLE,
            AUTHENTICATION_APPLICATION_ROLE,
        ):
            assert not bool(
                await connection.scalar(
                    text(
                        "select has_function_privilege("
                        ":role_name, 'public.enforce_employee_assignment_integrity()', "
                        "'EXECUTE')"
                    ),
                    {"role_name": role_name},
                )
            )


async def _seed_runtime_records(engine: AsyncEngine) -> None:
    for tenant_id, branch_id, department_id, position_id, employee_id in (
        (TENANT_A_ID, BRANCH_A_ID, DEPARTMENT_A_ID, POSITION_A_ID, EMPLOYEE_A_ID),
        (TENANT_B_ID, BRANCH_B_ID, DEPARTMENT_B_ID, POSITION_B_ID, EMPLOYEE_B_ID),
    ):
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, tenant_id)
            await connection.execute(
                text(
                    "insert into branches ("
                    "id, tenant_id, legal_entity_id, code, name, timezone, status"
                    ") values ("
                    ":id, :tenant_id, :tenant_id, :code, :name, 'UTC', 'active'"
                    ")"
                ),
                {
                    "id": branch_id,
                    "tenant_id": tenant_id,
                    "code": f"{str(tenant_id)[1:3]}-HQ",
                    "name": f"{tenant_id} Headquarters",
                },
            )
            await connection.execute(
                text(
                    "insert into departments ("
                    "id, tenant_id, code, name, status"
                    ") values ("
                    ":id, :tenant_id, :code, :name, 'active'"
                    ")"
                ),
                {
                    "id": department_id,
                    "tenant_id": tenant_id,
                    "code": f"{str(tenant_id)[1:3]}-DEPT",
                    "name": f"{tenant_id} Department",
                },
            )
            await connection.execute(
                text(
                    "insert into positions ("
                    "id, tenant_id, code, title, status"
                    ") values ("
                    ":id, :tenant_id, :code, :title, 'active'"
                    ")"
                ),
                {
                    "id": position_id,
                    "tenant_id": tenant_id,
                    "code": f"{str(tenant_id)[1:3]}-POS",
                    "title": f"{tenant_id} Position",
                },
            )
            await connection.execute(
                text(
                    "insert into employees ("
                    "id, tenant_id, employee_number, first_name, last_name, "
                    "department, position, status, employment_start_date"
                    ") values ("
                    ":id, :tenant_id, :employee_number, 'P3I', 'Employee', "
                    "'Legacy Department', 'Legacy Position', 'active', :start_date"
                    ")"
                ),
                {
                    "id": employee_id,
                    "tenant_id": tenant_id,
                    "employee_number": f"P3I-{str(tenant_id)[-4:]}",
                    "start_date": date(2026, 7, 1),
                },
            )

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        await connection.execute(
            text(
                "insert into branches ("
                "id, tenant_id, legal_entity_id, code, name, timezone, status"
                ") values ("
                ":id, :tenant_id, :tenant_id, 'A-OLD', "
                "'Archived Branch', 'UTC', 'active'"
                ")"
            ),
            {"id": ARCHIVED_BRANCH_A_ID, "tenant_id": TENANT_A_ID},
        )
        await connection.execute(
            text(
                "insert into departments (id, tenant_id, code, name, status) "
                "values (:id, :tenant_id, 'A-OLD-DEPT', 'Archived Department', 'active')"
            ),
            {"id": ARCHIVED_DEPARTMENT_A_ID, "tenant_id": TENANT_A_ID},
        )
        await connection.execute(
            text(
                "insert into positions (id, tenant_id, code, title, status) "
                "values (:id, :tenant_id, 'A-OLD-POS', 'Archived Position', 'active')"
            ),
            {"id": ARCHIVED_POSITION_A_ID, "tenant_id": TENANT_A_ID},
        )
        await connection.execute(
            text(
                "insert into employees ("
                "id, tenant_id, employee_number, first_name, last_name, status, "
                "employment_start_date"
                ") values ("
                ":id, :tenant_id, 'P3I-A-UNASSIGNED', 'Unassigned', 'Employee', "
                "'active', :start_date"
                ")"
            ),
            {
                "id": UNASSIGNED_EMPLOYEE_A_ID,
                "tenant_id": TENANT_A_ID,
                "start_date": date(2026, 7, 1),
            },
        )
        await connection.execute(
            text(
                "insert into employees ("
                "id, tenant_id, employee_number, first_name, last_name, status, "
                "employment_start_date, employment_end_date"
                ") values ("
                ":id, :tenant_id, 'P3I-A-TERMINATED', 'Terminated', 'Employee', "
                "'terminated', :start_date, :end_date"
                ")"
            ),
            {
                "id": TERMINATED_EMPLOYEE_A_ID,
                "tenant_id": TENANT_A_ID,
                "start_date": date(2025, 1, 10),
                "end_date": date(2026, 6, 30),
            },
        )
        for table_name, record_id in (
            ("branches", ARCHIVED_BRANCH_A_ID),
            ("departments", ARCHIVED_DEPARTMENT_A_ID),
            ("positions", ARCHIVED_POSITION_A_ID),
        ):
            await connection.execute(
                text(
                    f"update {table_name} set status = 'archived', "
                    "archived_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                    "where id = :id"
                ),
                {"id": record_id},
            )


async def _insert_assignment(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    assignment_id: UUID,
    employee_id: UUID,
    branch_id: UUID,
    department_id: UUID,
    position_id: UUID,
) -> None:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, tenant_id)
        await connection.execute(
            text(
                "insert into employee_assignments ("
                "id, tenant_id, employee_id, legal_entity_id, branch_id, "
                "department_id, position_id, effective_from, change_reason"
                ") values ("
                ":id, :tenant_id, :employee_id, :tenant_id, :branch_id, "
                ":department_id, :position_id, :effective_from, 'PostgreSQL P3I proof'"
                ")"
            ),
            {
                "id": assignment_id,
                "tenant_id": tenant_id,
                "employee_id": employee_id,
                "branch_id": branch_id,
                "department_id": department_id,
                "position_id": position_id,
                "effective_from": date(2026, 7, 1),
            },
        )


async def _assert_tenant_isolation(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        assert tuple(
            await connection.scalars(
                text("select id from employee_assignments order by id")
            )
        ) == (ASSIGNMENT_A_ID,)
        cross_tenant_update = await connection.execute(
            text(
                "update employee_assignments set effective_to = DATE '2026-08-01' "
                "where id = :id"
            ),
            {"id": ASSIGNMENT_B_ID},
        )
        assert cross_tenant_update.rowcount == 0

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_B_ID)
        assert tuple(
            await connection.scalars(
                text("select id from employee_assignments order by id")
            )
        ) == (ASSIGNMENT_B_ID,)


async def _assert_archived_references_rejected(engine: AsyncEngine) -> None:
    for field_name, archived_id, constraint_name in (
        (
            "branch_id",
            ARCHIVED_BRANCH_A_ID,
            "ck_employee_assignments_branch_assignable",
        ),
        (
            "department_id",
            ARCHIVED_DEPARTMENT_A_ID,
            "ck_employee_assignments_department_assignable",
        ),
        (
            "position_id",
            ARCHIVED_POSITION_A_ID,
            "ck_employee_assignments_position_assignable",
        ),
    ):
        parameters = {
            "id": uuid4(),
            "tenant_id": TENANT_A_ID,
            "employee_id": UNASSIGNED_EMPLOYEE_A_ID,
            "branch_id": BRANCH_A_ID,
            "department_id": DEPARTMENT_A_ID,
            "position_id": POSITION_A_ID,
            "effective_from": date(2026, 7, 1),
        }
        parameters[field_name] = archived_id
        with pytest.raises(DBAPIError) as archived_reference:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await connection.execute(
                    text(
                        "insert into employee_assignments ("
                        "id, tenant_id, employee_id, legal_entity_id, branch_id, "
                        "department_id, position_id, effective_from"
                        ") values ("
                        ":id, :tenant_id, :employee_id, :tenant_id, :branch_id, "
                        ":department_id, :position_id, :effective_from"
                        ")"
                    ),
                    parameters,
                )
        _assert_database_error(
            archived_reference.value,
            sqlstate="23514",
            constraint_name=constraint_name,
        )


async def _assert_terminated_history_bootstrap_is_owner_only(
    engine: AsyncEngine,
) -> None:
    exact_parameters = {
        "id": TERMINATED_ASSIGNMENT_A_ID,
        "tenant_id": TENANT_A_ID,
        "employee_id": TERMINATED_EMPLOYEE_A_ID,
        "branch_id": BRANCH_A_ID,
        "department_id": DEPARTMENT_A_ID,
        "position_id": POSITION_A_ID,
        "effective_from": date(2025, 1, 10),
        "effective_to": date(2026, 7, 1),
    }
    insert_history = text(
        "insert into employee_assignments ("
        "id, tenant_id, employee_id, legal_entity_id, branch_id, "
        "department_id, position_id, effective_from, effective_to"
        ") values ("
        ":id, :tenant_id, :employee_id, :tenant_id, :branch_id, "
        ":department_id, :position_id, :effective_from, :effective_to"
        ")"
    )

    with pytest.raises(DBAPIError) as tenant_history_insert:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(insert_history, exact_parameters)
    _assert_database_error(
        tenant_history_insert.value,
        sqlstate="23514",
        constraint_name="ck_employee_assignments_runtime_insert_open",
    )

    for field_name, inexact_boundary in (
        ("effective_from", date(2025, 1, 11)),
        ("effective_to", date(2026, 7, 2)),
    ):
        inexact_parameters = {
            **exact_parameters,
            "id": uuid4(),
            field_name: inexact_boundary,
        }
        with pytest.raises(DBAPIError) as inexact_owner_history:
            async with engine.begin() as connection:
                await connection.execute(insert_history, inexact_parameters)
        _assert_database_error(
            inexact_owner_history.value,
            sqlstate="23514",
            constraint_name="ck_employee_assignments_runtime_insert_open",
        )

    async with engine.begin() as connection:
        await connection.execute(insert_history, exact_parameters)
        stored_interval = (
            await connection.execute(
                text(
                    "select effective_from, effective_to "
                    "from employee_assignments where id = :id"
                ),
                {"id": TERMINATED_ASSIGNMENT_A_ID},
            )
        ).one()
        assert stored_interval == (date(2025, 1, 10), date(2026, 7, 1))


async def _assert_history_is_immutable(engine: AsyncEngine) -> None:
    for statement in (
        "delete from employee_assignments where id = :id",
        "update employee_assignments set position_id = :position_id where id = :id",
    ):
        with pytest.raises(DBAPIError) as denied_mutation:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await connection.execute(
                    text(statement),
                    {
                        "id": ASSIGNMENT_A_ID,
                        "position_id": ARCHIVED_POSITION_A_ID,
                    },
                )
        assert sqlstate_from_error(denied_mutation.value) == "42501"

    with pytest.raises(DBAPIError) as owner_structural_mutation:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "update employee_assignments set position_id = :position_id "
                    "where id = :id"
                ),
                {
                    "id": ASSIGNMENT_A_ID,
                    "position_id": ARCHIVED_POSITION_A_ID,
                },
            )
    _assert_database_error(
        owner_structural_mutation.value,
        sqlstate="23514",
        constraint_name="ck_employee_assignments_immutable_history",
    )

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        closed = await connection.execute(
            text(
                "update employee_assignments set effective_to = DATE '2026-08-01' "
                "where id = :id"
            ),
            {"id": ASSIGNMENT_A_ID},
        )
        assert closed.rowcount == 1

    with pytest.raises(DBAPIError) as interval_rewrite:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(
                text(
                    "update employee_assignments set effective_to = DATE '2026-09-01' "
                    "where id = :id"
                ),
                {"id": ASSIGNMENT_A_ID},
            )
    _assert_database_error(
        interval_rewrite.value,
        sqlstate="23514",
        constraint_name="ck_employee_assignments_close_open_interval",
    )


async def _table_privileges(
    connection: AsyncConnection,
    *,
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
        if await connection.scalar(
            text(
                "select has_table_privilege("
                ":role_name, 'public.employee_assignments', :privilege)"
            ),
            {"role_name": role_name, "privilege": privilege},
        ):
            privileges.add(privilege)
    return privileges


def _assert_database_error(
    error: BaseException,
    *,
    sqlstate: str,
    constraint_name: str,
) -> None:
    assert sqlstate_from_error(error) == sqlstate
    assert constraint_name_from_error(error) == constraint_name


async def _seed_pre_organization_tenants(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone"
                    ") values "
                    "(:tenant_a, 'p3i-tenant-a', 'P3I Tenant A', 'active', "
                    "'core', 'tr-1', 'en-US', 'Europe/Istanbul'), "
                    "(:tenant_b, 'p3i-tenant-b', 'P3I Tenant B', 'active', "
                    "'core', 'eu-1', 'en-US', 'Europe/London')"
                ),
                {"tenant_a": TENANT_A_ID, "tenant_b": TENANT_B_ID},
            )
    finally:
        await engine.dispose()


async def _set_local_tenant_role(
    connection: AsyncConnection,
    tenant_id: UUID,
) -> None:
    await _set_local_role(connection, TENANT_APPLICATION_ROLE)
    await connection.execute(
        text("select set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def _set_local_role(connection: AsyncConnection, role_name: str) -> None:
    quoted_role = connection.dialect.identifier_preparer.quote(role_name)
    await connection.exec_driver_sql(f"SET LOCAL ROLE {quoted_role}")


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config
