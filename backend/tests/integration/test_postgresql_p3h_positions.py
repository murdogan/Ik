from __future__ import annotations

import asyncio
from datetime import UTC, datetime
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
PRE_P3H_REVISION = "0028_p3g_department_hierarchy"
P3H_REVISION = "0029_p3h_position_catalog"

TENANT_A_ID = UUID("f1000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("f1000000-0000-4000-8000-000000000002")
POSITION_A_ID = UUID("f2000000-0000-4000-8000-000000000001")
POSITION_B_ID = UUID("f2000000-0000-4000-8000-000000000002")

POSITION_UPDATE_COLUMNS = frozenset({"title", "status", "archived_at", "updated_at"})
ALL_POSITION_COLUMNS = frozenset(
    {
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
    }
)


@pytest.fixture
def p3h_postgres_database(postgres_database_url: URL) -> URL:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_P3H_REVISION)
    asyncio.run(_seed_tenants(postgres_database_url))
    alembic_command.upgrade(config, P3H_REVISION)
    return postgres_database_url


def test_p3h_position_catalog_rls_acl_indexes_and_archive_guards(
    p3h_postgres_database: URL,
) -> None:
    asyncio.run(_assert_p3h_postgresql_contract(p3h_postgres_database))

    with pytest.raises(
        RuntimeError,
        match=(
            "P3H downgrade preflight failed; export and remove retained position catalog "
            "history before retrying: positions=2"
        ),
    ):
        alembic_command.downgrade(
            _alembic_config(p3h_postgres_database),
            PRE_P3H_REVISION,
        )

    assert asyncio.run(_current_revision(p3h_postgres_database)) == P3H_REVISION
    assert asyncio.run(_position_row_security(p3h_postgres_database)) == (True, True)


async def _assert_p3h_postgresql_contract(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        await _assert_security_catalog(engine)
        await _insert_position(
            engine,
            tenant_id=TENANT_A_ID,
            position_id=POSITION_A_ID,
            code=" Eng ",
            title=" Senior Engineer ",
        )
        await _insert_position(
            engine,
            tenant_id=TENANT_B_ID,
            position_id=POSITION_B_ID,
            code="ENG",
            title="Tenant B Engineer",
        )
        await _assert_generated_normalization_and_tenant_unique_code(engine)
        await _assert_tenant_isolation_and_acl(engine)
        await _assert_immutable_identity_trigger(engine)
        await _assert_archive_lifecycle_trigger(engine)
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
                    "where namespace.nspname = 'public' and class.relname = 'positions'"
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
                        "where schemaname = 'public' and tablename = 'positions'"
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
                    "and class.relname = 'positions' and not trigger.tgisinternal"
                )
            )
        ).one()
        assert trigger == (
            "trg_positions_catalog_integrity",
            "O",
            "enforce_position_catalog_integrity",
            False,
            "v",
        )

        index_rows = (
            (
                await connection.execute(
                    text(
                        "select indexname, indexdef from pg_catalog.pg_indexes "
                        "where schemaname = 'public' and tablename = 'positions' "
                        "and indexname like 'ix_positions_%'"
                    )
                )
            )
            .mappings()
            .all()
        )
        indexes = {row["indexname"]: row["indexdef"] for row in index_rows}
        assert set(indexes) == {
            "ix_positions_tenant_code_cursor",
            "ix_positions_tenant_status_code_cursor",
            "ix_positions_code_normalized_trgm",
            "ix_positions_title_normalized_trgm",
        }
        assert (
            "USING btree (tenant_id, code_normalized, id)"
            in indexes["ix_positions_tenant_code_cursor"]
        )
        assert (
            "USING btree (tenant_id, status, code_normalized, id)"
            in indexes["ix_positions_tenant_status_code_cursor"]
        )
        assert (
            "USING gin (code_normalized gin_trgm_ops)"
            in indexes["ix_positions_code_normalized_trgm"]
        )
        assert (
            "USING gin (title_normalized gin_trgm_ops)"
            in indexes["ix_positions_title_normalized_trgm"]
        )
        assert (
            await connection.scalar(
                text("select count(*) from pg_catalog.pg_extension where extname = 'pg_trgm'")
            )
            == 1
        )

        assert await _table_privileges(
            connection,
            table_name="positions",
            role_name=TENANT_APPLICATION_ROLE,
        ) == {"SELECT", "INSERT"}
        for role_name in (
            PLATFORM_APPLICATION_ROLE,
            AUTHENTICATION_APPLICATION_ROLE,
        ):
            assert (
                await _table_privileges(
                    connection,
                    table_name="positions",
                    role_name=role_name,
                )
                == set()
            )

        for column_name in ALL_POSITION_COLUMNS:
            has_update = bool(
                await connection.scalar(
                    text(
                        "select has_column_privilege("
                        ":role_name, 'public.positions', :column_name, 'UPDATE')"
                    ),
                    {
                        "role_name": TENANT_APPLICATION_ROLE,
                        "column_name": column_name,
                    },
                )
            )
            assert has_update is (column_name in POSITION_UPDATE_COLUMNS)

        assert bool(
            await connection.scalar(
                text(
                    "select has_function_privilege("
                    ":role_name, 'public.enforce_position_catalog_integrity()', "
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
                        ":role_name, 'public.enforce_position_catalog_integrity()', "
                        "'EXECUTE')"
                    ),
                    {"role_name": role_name},
                )
            )


async def _insert_position(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    position_id: UUID,
    code: str,
    title: str,
) -> None:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, tenant_id)
        await connection.execute(
            text(
                "insert into positions (id, tenant_id, code, title, status) "
                "values (:id, :tenant_id, :code, :title, 'active')"
            ),
            {
                "id": position_id,
                "tenant_id": tenant_id,
                "code": code,
                "title": title,
            },
        )


async def _assert_generated_normalization_and_tenant_unique_code(
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        normalized = (
            await connection.execute(
                text(
                    "select code_normalized, title_normalized from positions "
                    "where id = :position_id"
                ),
                {"position_id": POSITION_A_ID},
            )
        ).one()
        assert normalized == ("eng", "senior engineer")

    with pytest.raises(DBAPIError) as duplicate_code:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(
                text(
                    "insert into positions (id, tenant_id, code, title, status) "
                    "values (:id, :tenant_id, 'ENG', 'Duplicate', 'active')"
                ),
                {"id": uuid4(), "tenant_id": TENANT_A_ID},
            )
    _assert_database_error(
        duplicate_code.value,
        sqlstate="23505",
        constraint_name="uq_positions_tenant_code_normalized",
    )


async def _assert_tenant_isolation_and_acl(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        assert tuple(await connection.scalars(text("select id from positions"))) == (POSITION_A_ID,)
        cross_tenant_update = await connection.execute(
            text("update positions set title = 'must-not-change' where id = :id"),
            {"id": POSITION_B_ID},
        )
        assert cross_tenant_update.rowcount == 0
        await connection.execute(
            text(
                "update positions set title = 'Principal Engineer', "
                "updated_at = :updated_at where id = :id"
            ),
            {"updated_at": datetime.now(UTC), "id": POSITION_A_ID},
        )
        assert (
            await connection.scalar(
                text("select title_normalized from positions where id = :id"),
                {"id": POSITION_A_ID},
            )
            == "principal engineer"
        )

    for role_name in (
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
    ):
        with pytest.raises(DBAPIError) as denied_read:
            async with engine.begin() as connection:
                await _set_local_role(connection, role_name)
                await connection.scalar(text("select count(*) from positions"))
        assert sqlstate_from_error(denied_read.value) == "42501"

    for statement in (
        "delete from positions where id = :id",
        "update positions set code = 'RENAMED' where id = :id",
        "update positions set tenant_id = :other_tenant where id = :id",
    ):
        with pytest.raises(DBAPIError) as denied_mutation:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await connection.execute(
                    text(statement),
                    {
                        "id": POSITION_A_ID,
                        "other_tenant": TENANT_B_ID,
                    },
                )
        assert sqlstate_from_error(denied_mutation.value) == "42501"


async def _assert_immutable_identity_trigger(engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError) as immutable_code:
        async with engine.begin() as connection:
            await connection.execute(
                text("update positions set code = 'OWNER-RENAMED' where id = :id"),
                {"id": POSITION_B_ID},
            )
    _assert_database_error(
        immutable_code.value,
        sqlstate="23514",
        constraint_name="ck_positions_immutable_identity_code",
    )


async def _assert_archive_lifecycle_trigger(engine: AsyncEngine) -> None:
    now = datetime.now(UTC)
    with pytest.raises(DBAPIError) as archived_insert:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(
                text(
                    "insert into positions ("
                    "id, tenant_id, code, title, status, archived_at"
                    ") values ("
                    ":id, :tenant_id, 'HISTORICAL', 'Historical', 'archived', :now"
                    ")"
                ),
                {"id": uuid4(), "tenant_id": TENANT_A_ID, "now": now},
            )
    _assert_database_error(
        archived_insert.value,
        sqlstate="23514",
        constraint_name="ck_positions_archived_terminal",
    )

    with pytest.raises(DBAPIError) as archive_rewrite:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(
                text(
                    "update positions set title = 'Rewritten On Archive', "
                    "status = 'archived', archived_at = :now, updated_at = :now "
                    "where id = :id"
                ),
                {"now": now, "id": POSITION_A_ID},
            )
    _assert_database_error(
        archive_rewrite.value,
        sqlstate="23514",
        constraint_name="ck_positions_archived_terminal",
    )

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        await connection.execute(
            text(
                "update positions set status = 'archived', archived_at = :now, "
                "updated_at = :now where id = :id"
            ),
            {"now": now, "id": POSITION_A_ID},
        )
        historical = (
            await connection.execute(
                text("select title, status, archived_at from positions where id = :id"),
                {"id": POSITION_A_ID},
            )
        ).one()
        assert historical[0:2] == ("Principal Engineer", "archived")
        assert historical.archived_at is not None

    for statement in (
        "update positions set title = 'Reopened' where id = :id",
        "update positions set status = 'active', archived_at = null where id = :id",
    ):
        with pytest.raises(DBAPIError) as terminal_archive:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await connection.execute(text(statement), {"id": POSITION_A_ID})
        _assert_database_error(
            terminal_archive.value,
            sqlstate="23514",
            constraint_name="ck_positions_archived_terminal",
        )


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
        if await connection.scalar(
            text("select has_table_privilege(:role_name, :qualified_table_name, :privilege)"),
            {
                "role_name": role_name,
                "qualified_table_name": f"public.{table_name}",
                "privilege": privilege,
            },
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


async def _seed_tenants(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone"
                    ") values "
                    "(:tenant_a, 'p3h-tenant-a', 'P3H Tenant A', 'active', "
                    "'core', 'tr-1', 'en-US', 'Europe/Istanbul'), "
                    "(:tenant_b, 'p3h-tenant-b', 'P3H Tenant B', 'active', "
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


async def _current_revision(database_url: URL) -> str | None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("select version_num from alembic_version"))
    finally:
        await engine.dispose()


async def _position_row_security(database_url: URL) -> tuple[bool, bool]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "select class.relrowsecurity, class.relforcerowsecurity "
                        "from pg_catalog.pg_class as class "
                        "join pg_catalog.pg_namespace as namespace "
                        "on namespace.oid = class.relnamespace "
                        "where namespace.nspname = 'public' "
                        "and class.relname = 'positions'"
                    )
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
