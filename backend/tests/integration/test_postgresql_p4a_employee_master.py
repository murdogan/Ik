from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.platform.db import constraint_name_from_error, sqlstate_from_error
from app.platform.db.tenant_access import TENANT_APPLICATION_ROLE
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"
PRE_P4A_REVISION = "0031_p3k_legacy_tenant_auth_boundary"
P4A_REVISION = "0032_p4a_employee_directory"

TENANT_A_ID = UUID("f4a00000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("f4a00000-0000-4000-8000-000000000002")


def test_p4a_normalization_collision_refuses_atomically_and_restores_rls(
    postgres_database_url: URL,
) -> None:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_P4A_REVISION)
    asyncio.run(_seed_collision_fixture(postgres_database_url))

    with pytest.raises(
        RuntimeError,
        match=(
            "P4A employee preflight failed: normalized_number_collisions=1, "
            "blank_employee_numbers=0, normalized_email_collisions=1, "
            "blank_work_emails=0"
        ),
    ):
        alembic_command.upgrade(config, P4A_REVISION)

    assert asyncio.run(_current_revision(postgres_database_url)) == PRE_P4A_REVISION
    assert asyncio.run(_employee_row_security(postgres_database_url)) == (True, True)


def test_p4a_postgresql_generated_keys_indexes_acl_and_downgrade(
    postgres_database_url: URL,
) -> None:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_P4A_REVISION)
    asyncio.run(_seed_safe_fixture(postgres_database_url))
    alembic_command.upgrade(config, P4A_REVISION)

    asyncio.run(_assert_p4a_catalog_and_integrity(postgres_database_url))

    alembic_command.downgrade(config, PRE_P4A_REVISION)
    assert asyncio.run(_current_revision(postgres_database_url)) == PRE_P4A_REVISION
    assert asyncio.run(_employee_row_security(postgres_database_url)) == (True, True)


async def _seed_collision_fixture(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await _insert_tenants(connection)
            await _insert_employee(
                connection,
                tenant_id=TENANT_A_ID,
                employee_number="WF-001",
                email="Ada@Example.test",
            )
            await _insert_employee(
                connection,
                tenant_id=TENANT_A_ID,
                employee_number=" wf-001 ",
                email=" ada@example.test ",
            )
    finally:
        await engine.dispose()


async def _seed_safe_fixture(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await _insert_tenants(connection)
            await _insert_employee(
                connection,
                tenant_id=TENANT_A_ID,
                employee_number=" WF-001 ",
                email=" Ada@Example.test ",
            )
            await _insert_employee(
                connection,
                tenant_id=TENANT_A_ID,
                employee_number="WF-002",
                email=None,
            )
            await _insert_employee(
                connection,
                tenant_id=TENANT_A_ID,
                employee_number="WF-003",
                email=None,
            )
            # Normalized identifiers are tenant-scoped, so another tenant may reuse both.
            await _insert_employee(
                connection,
                tenant_id=TENANT_B_ID,
                employee_number="wf-001",
                email="ada@example.test",
            )
    finally:
        await engine.dispose()


async def _assert_p4a_catalog_and_integrity(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        await _assert_catalog(engine)
        async with engine.connect() as connection:
            normalized = (
                await connection.execute(
                    text(
                        "select employee_number_normalized, email_normalized, "
                        "full_name_normalized, version from employees "
                        "where tenant_id = :tenant_id order by employee_number_normalized"
                    ),
                    {"tenant_id": TENANT_A_ID},
                )
            ).tuples().all()
        assert normalized == [
            ("wf-001", "ada@example.test", "ada employee", 1),
            ("wf-002", None, "ada employee", 1),
            ("wf-003", None, "ada employee", 1),
        ]

        await _assert_rejected_employee(
            engine,
            employee_number="wf-001",
            email=None,
            constraint_name="uq_employees_tenant_employee_number_normalized",
            sqlstate="23505",
        )
        await _assert_rejected_employee(
            engine,
            employee_number="WF-004",
            email="ADA@EXAMPLE.TEST",
            constraint_name="uq_employees_tenant_email_normalized",
            sqlstate="23505",
        )
        await _assert_rejected_employee(
            engine,
            employee_number="\t\n\u00a0",
            email=None,
            constraint_name="ck_employees_employee_number_not_blank",
            sqlstate="23514",
        )
        await _assert_rejected_employee(
            engine,
            employee_number="WF-005",
            email="\t\n\u00a0",
            constraint_name="ck_employees_email_not_blank",
            sqlstate="23514",
        )
    finally:
        await engine.dispose()


async def _assert_catalog(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        assert await _employee_row_security_from_connection(connection) == (True, True)
        generated = {
            row.column_name: (row.is_generated, row.generation_expression)
            for row in (
                await connection.execute(
                    text(
                        "select column_name, is_generated, generation_expression "
                        "from information_schema.columns where table_schema = 'public' "
                        "and table_name = 'employees' and column_name in "
                        "('employee_number_normalized', 'email_normalized', "
                        "'full_name_normalized')"
                    )
                )
            ).all()
        }
        assert set(generated) == {
            "employee_number_normalized",
            "email_normalized",
            "full_name_normalized",
        }
        assert {value[0] for value in generated.values()} == {"ALWAYS"}
        assert all(value[1] for value in generated.values())

        constraints = set(
            await connection.scalars(
                text(
                    "select con.conname from pg_catalog.pg_constraint as con "
                    "join pg_catalog.pg_class as cls on cls.oid = con.conrelid "
                    "where cls.relname = 'employees'"
                )
            )
        )
        assert {
            "ck_employees_employee_number_not_blank",
            "ck_employees_email_not_blank",
            "ck_employees_version_positive",
        } <= constraints

        index_rows = (
            (
                await connection.execute(
                    text(
                        "select tablename, indexname, indexdef from pg_catalog.pg_indexes "
                        "where schemaname = 'public' and indexname in "
                        "('uq_employees_tenant_employee_number_normalized', "
                        "'uq_employees_tenant_email_normalized', "
                        "'ix_employees_tenant_directory_cursor', "
                        "'ix_employees_tenant_status_directory_cursor', "
                        "'ix_employees_full_name_normalized_trgm', "
                        "'ix_employee_assignments_tenant_legal_entity_effective', "
                        "'ix_employee_assignments_tenant_position_effective')"
                    )
                )
            )
            .mappings()
            .all()
        )
        indexes = {row["indexname"]: row["indexdef"] for row in index_rows}
        assert set(indexes) == {
            "uq_employees_tenant_employee_number_normalized",
            "uq_employees_tenant_email_normalized",
            "ix_employees_tenant_directory_cursor",
            "ix_employees_tenant_status_directory_cursor",
            "ix_employees_full_name_normalized_trgm",
            "ix_employee_assignments_tenant_legal_entity_effective",
            "ix_employee_assignments_tenant_position_effective",
        }
        assert "UNIQUE INDEX" in indexes[
            "uq_employees_tenant_employee_number_normalized"
        ]
        assert indexes["ix_employees_tenant_directory_cursor"] == (
            "CREATE INDEX ix_employees_tenant_directory_cursor ON public.employees "
            "USING btree (tenant_id, id) WHERE (archived_at IS NULL)"
        )
        assert indexes["ix_employees_tenant_status_directory_cursor"] == (
            "CREATE INDEX ix_employees_tenant_status_directory_cursor ON "
            "public.employees USING btree (tenant_id, status, id) "
            "WHERE (archived_at IS NULL)"
        )
        assert "USING gin (full_name_normalized gin_trgm_ops)" in indexes[
            "ix_employees_full_name_normalized_trgm"
        ]
        for privilege in ("SELECT", "INSERT", "UPDATE"):
            assert await connection.scalar(
                text(
                    "select has_table_privilege("
                    ":role, 'public.employees', :privilege)"
                ),
                {"role": TENANT_APPLICATION_ROLE, "privilege": privilege},
            ) is True
        assert await connection.scalar(
            text("select has_table_privilege(:role, 'public.employees', 'DELETE')"),
            {"role": TENANT_APPLICATION_ROLE},
        ) is False


async def _assert_rejected_employee(
    engine: AsyncEngine,
    *,
    employee_number: str,
    email: str | None,
    constraint_name: str,
    sqlstate: str,
) -> None:
    with pytest.raises(DBAPIError) as error:
        async with engine.begin() as connection:
            await _insert_employee(
                connection,
                tenant_id=TENANT_A_ID,
                employee_number=employee_number,
                email=email,
            )
    assert sqlstate_from_error(error.value) == sqlstate
    assert constraint_name_from_error(error.value) == constraint_name


async def _insert_tenants(connection) -> None:
    await connection.execute(
        text(
            "insert into tenants ("
            "id, slug, name, status, plan_code, data_region, locale, timezone"
            ") values "
            "(:tenant_a, 'p4a-tenant-a', 'P4A Tenant A', 'active', 'core', "
            "'tr-1', 'en-US', 'UTC'), "
            "(:tenant_b, 'p4a-tenant-b', 'P4A Tenant B', 'active', 'core', "
            "'tr-1', 'en-US', 'UTC')"
        ),
        {"tenant_a": TENANT_A_ID, "tenant_b": TENANT_B_ID},
    )


async def _insert_employee(
    connection,
    *,
    tenant_id: UUID,
    employee_number: str,
    email: str | None,
) -> None:
    await connection.execute(
        text(
            "insert into employees ("
            "id, tenant_id, employee_number, first_name, last_name, email, status, "
            "employment_start_date"
            ") values ("
            ":id, :tenant_id, :employee_number, 'Ada', 'Employee', :email, 'active', "
            "DATE '2026-07-01'"
            ")"
        ),
        {
            "id": uuid4(),
            "tenant_id": tenant_id,
            "employee_number": employee_number,
            "email": email,
        },
    )


async def _current_revision(database_url: URL) -> str | None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("select version_num from alembic_version"))
    finally:
        await engine.dispose()


async def _employee_row_security(database_url: URL) -> tuple[bool, bool]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await _employee_row_security_from_connection(connection)
    finally:
        await engine.dispose()


async def _employee_row_security_from_connection(connection) -> tuple[bool, bool]:
    row = (
        await connection.execute(
            text(
                "select class.relrowsecurity, class.relforcerowsecurity "
                "from pg_catalog.pg_class as class "
                "join pg_catalog.pg_namespace as namespace "
                "on namespace.oid = class.relnamespace "
                "where namespace.nspname = 'public' and class.relname = 'employees'"
            )
        )
    ).one()
    return row[0], row[1]


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config
