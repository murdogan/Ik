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
PRE_P3F_REVISION = "0026_p3e_identity_checkpoint"

TENANT_A_ID = UUID("e1000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("e1000000-0000-4000-8000-000000000002")
ROOT_A_ID = UUID("e2000000-0000-4000-8000-000000000001")
CHILD_A_ID = UUID("e2000000-0000-4000-8000-000000000002")
LEAF_A_ID = UUID("e2000000-0000-4000-8000-000000000003")
ROOT_B_ID = UUID("e2000000-0000-4000-8000-000000000004")
RACE_A_ID = UUID("e2000000-0000-4000-8000-000000000005")
RACE_B_ID = UUID("e2000000-0000-4000-8000-000000000006")
REPEATABLE_RACE_A_ID = UUID("e2000000-0000-4000-8000-000000000007")
REPEATABLE_RACE_B_ID = UUID("e2000000-0000-4000-8000-000000000008")

DEPARTMENT_UPDATE_COLUMNS = frozenset({"name", "parent_id", "status", "archived_at", "updated_at"})
ALL_DEPARTMENT_COLUMNS = frozenset(
    {
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
    }
)


@pytest.fixture
def p3g_postgres_database(postgres_database_url: URL) -> URL:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_P3F_REVISION)
    asyncio.run(_seed_pre_p3f_tenants(postgres_database_url))
    alembic_command.upgrade(config, "head")
    return postgres_database_url


def test_p3g_rls_acl_archive_guards_and_concurrent_cycle_proof(
    p3g_postgres_database: URL,
) -> None:
    asyncio.run(_assert_p3g_postgresql_contract(p3g_postgres_database))

    with pytest.raises(
        RuntimeError,
        match="P3G downgrade preflight failed; export and remove retained department history",
    ):
        alembic_command.downgrade(
            _alembic_config(p3g_postgres_database),
            "0027_p3f_legal_entities_branches",
        )


async def _assert_p3g_postgresql_contract(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        await _assert_security_catalog(engine)
        await _seed_departments(engine)
        await _assert_tenant_isolation_and_acl(engine)
        await _assert_hierarchy_and_archive_guards(engine)
        await _assert_multirow_opposing_moves_cannot_cycle(engine)
        await _assert_concurrent_opposing_moves_cannot_cycle(engine)
        await _assert_snapshot_isolation_opposing_moves_cannot_cycle(
            engine,
            isolation_level="REPEATABLE READ",
        )
        await _assert_snapshot_isolation_opposing_moves_cannot_cycle(
            engine,
            isolation_level="SERIALIZABLE",
        )
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
                    "where namespace.nspname = 'public' and class.relname = 'departments'"
                )
            )
        ).one()
        assert row_security == (True, True)

        fence_row_security = (
            await connection.execute(
                text(
                    "select class.relrowsecurity, class.relforcerowsecurity "
                    "from pg_catalog.pg_class as class "
                    "join pg_catalog.pg_namespace as namespace "
                    "on namespace.oid = class.relnamespace "
                    "where namespace.nspname = 'public' "
                    "and class.relname = 'department_hierarchy_write_fences'"
                )
            )
        ).one()
        assert fence_row_security == (True, True)

        policy = (
            (
                await connection.execute(
                    text(
                        "select policyname, roles, cmd, qual, with_check "
                        "from pg_catalog.pg_policies "
                        "where schemaname = 'public' and tablename = 'departments'"
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

        fence_policy = (
            (
                await connection.execute(
                    text(
                        "select policyname, roles, cmd, qual, with_check "
                        "from pg_catalog.pg_policies "
                        "where schemaname = 'public' "
                        "and tablename = 'department_hierarchy_write_fences'"
                    )
                )
            )
            .mappings()
            .one()
        )
        assert fence_policy["policyname"] == "tenant_isolation_app"
        assert tuple(fence_policy["roles"]) == (TENANT_APPLICATION_ROLE,)
        assert fence_policy["cmd"] == "ALL"
        assert "app.tenant_id" in fence_policy["qual"]
        assert fence_policy["with_check"] == fence_policy["qual"]

        triggers = set(
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
                    "and class.relname = 'departments' "
                    "and not trigger.tgisinternal"
                )
            )
        )
        assert triggers == {
            (
                "trg_departments_hierarchy_integrity",
                "O",
                "enforce_department_hierarchy_integrity",
                False,
                "v",
            ),
            (
                "trg_departments_acyclic_after_insert",
                "O",
                "validate_department_hierarchy_acyclic",
                False,
                "v",
            ),
            (
                "trg_departments_acyclic_after_update",
                "O",
                "validate_department_hierarchy_acyclic",
                False,
                "v",
            ),
        }

        assert await _table_privileges(
            connection,
            table_name="departments",
            role_name=TENANT_APPLICATION_ROLE,
        ) == {
            "SELECT",
            "INSERT",
        }
        assert await _table_privileges(
            connection,
            table_name="department_hierarchy_write_fences",
            role_name=TENANT_APPLICATION_ROLE,
        ) == {
            "SELECT",
            "INSERT",
        }
        assert bool(
            await connection.scalar(
                text(
                    "select has_column_privilege("
                    ":role_name, 'public.department_hierarchy_write_fences', "
                    "'version', 'UPDATE')"
                ),
                {"role_name": TENANT_APPLICATION_ROLE},
            )
        )
        assert not bool(
            await connection.scalar(
                text(
                    "select has_column_privilege("
                    ":role_name, 'public.department_hierarchy_write_fences', "
                    "'tenant_id', 'UPDATE')"
                ),
                {"role_name": TENANT_APPLICATION_ROLE},
            )
        )
        for role_name in (
            PLATFORM_APPLICATION_ROLE,
            AUTHENTICATION_APPLICATION_ROLE,
        ):
            assert await _table_privileges(
                connection,
                table_name="departments",
                role_name=role_name,
            ) == set()
            assert await _table_privileges(
                connection,
                table_name="department_hierarchy_write_fences",
                role_name=role_name,
            ) == set()

        for column_name in ALL_DEPARTMENT_COLUMNS:
            has_update = bool(
                await connection.scalar(
                    text(
                        "select has_column_privilege("
                        ":role_name, 'public.departments', :column_name, 'UPDATE')"
                    ),
                    {
                        "role_name": TENANT_APPLICATION_ROLE,
                        "column_name": column_name,
                    },
                )
            )
            assert has_update is (column_name in DEPARTMENT_UPDATE_COLUMNS)

        for function_name in (
            "enforce_department_hierarchy_integrity",
            "validate_department_hierarchy_acyclic",
        ):
            assert bool(
                await connection.scalar(
                    text(
                        "select has_function_privilege(:role_name, :function_signature, 'EXECUTE')"
                    ),
                    {
                        "role_name": TENANT_APPLICATION_ROLE,
                        "function_signature": f"public.{function_name}()",
                    },
                )
            )
        for role_name in (
            PLATFORM_APPLICATION_ROLE,
            AUTHENTICATION_APPLICATION_ROLE,
        ):
            for function_name in (
                "enforce_department_hierarchy_integrity",
                "validate_department_hierarchy_acyclic",
            ):
                assert not bool(
                    await connection.scalar(
                        text(
                            "select has_function_privilege("
                            ":role_name, :function_signature, 'EXECUTE')"
                        ),
                        {
                            "role_name": role_name,
                            "function_signature": f"public.{function_name}()",
                        },
                    )
                )


async def _seed_departments(engine: AsyncEngine) -> None:
    for tenant_id, department_id, parent_id, code, name in (
        (TENANT_A_ID, ROOT_A_ID, None, "A-ROOT", "Tenant A Root"),
        (TENANT_A_ID, CHILD_A_ID, ROOT_A_ID, "A-CHILD", "Tenant A Child"),
        (TENANT_A_ID, LEAF_A_ID, CHILD_A_ID, "A-LEAF", "Tenant A Leaf"),
        (TENANT_A_ID, RACE_A_ID, None, "A-RACE-1", "Tenant A Race One"),
        (TENANT_A_ID, RACE_B_ID, None, "A-RACE-2", "Tenant A Race Two"),
        (
            TENANT_A_ID,
            REPEATABLE_RACE_A_ID,
            None,
            "A-RR-RACE-1",
            "Tenant A Repeatable Race One",
        ),
        (
            TENANT_A_ID,
            REPEATABLE_RACE_B_ID,
            None,
            "A-RR-RACE-2",
            "Tenant A Repeatable Race Two",
        ),
        (TENANT_B_ID, ROOT_B_ID, None, "B-ROOT", "Tenant B Root"),
    ):
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, tenant_id)
            await _insert_department(
                connection,
                tenant_id=tenant_id,
                department_id=department_id,
                parent_id=parent_id,
                code=code,
                name=name,
            )


async def _assert_tenant_isolation_and_acl(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        visible_ids = set(await connection.scalars(text("select id from departments")))
        assert visible_ids == {
            ROOT_A_ID,
            CHILD_A_ID,
            LEAF_A_ID,
            RACE_A_ID,
            RACE_B_ID,
            REPEATABLE_RACE_A_ID,
            REPEATABLE_RACE_B_ID,
        }
        hidden_update = await connection.execute(
            text("update departments set name = 'must-not-change' where id = :id"),
            {"id": ROOT_B_ID},
        )
        assert hidden_update.rowcount == 0

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_B_ID)
        assert tuple(await connection.scalars(text("select id from departments"))) == (ROOT_B_ID,)
        assert (
            await connection.scalar(
                text("select name from departments where id = :id"),
                {"id": ROOT_B_ID},
            )
            == "Tenant B Root"
        )

    with pytest.raises(DBAPIError) as cross_tenant_parent:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await _insert_department(
                connection,
                tenant_id=TENANT_A_ID,
                department_id=uuid4(),
                parent_id=ROOT_B_ID,
                code="CROSS-TENANT",
                name="Cross tenant parent attack",
            )
    _assert_database_error(
        cross_tenant_parent.value,
        sqlstate="23503",
        constraint_name="fk_departments_tenant_parent_id_departments",
    )

    for statement in (
        "update departments set code = 'RENAMED' where id = :id",
        "delete from departments where id = :id",
    ):
        with pytest.raises(DBAPIError) as privilege_error:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await connection.execute(text(statement), {"id": ROOT_A_ID})
        assert sqlstate_from_error(privilege_error.value) == "42501"

    for role_name in (
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
    ):
        with pytest.raises(DBAPIError) as denied_read:
            async with engine.begin() as connection:
                await _set_local_role(connection, role_name)
                await connection.scalar(text("select count(*) from departments"))
        assert sqlstate_from_error(denied_read.value) == "42501"


async def _assert_hierarchy_and_archive_guards(engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError) as descendant_cycle:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(
                text("update departments set parent_id = :parent_id where id = :id"),
                {"id": ROOT_A_ID, "parent_id": LEAF_A_ID},
            )
    _assert_database_error(
        descendant_cycle.value,
        sqlstate="23514",
        constraint_name="ck_departments_acyclic",
    )

    with pytest.raises(DBAPIError) as active_children:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(
                text(
                    "update departments set status = 'archived', "
                    "archived_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                    "where id = :id"
                ),
                {"id": ROOT_A_ID},
            )
    _assert_database_error(
        active_children.value,
        sqlstate="23514",
        constraint_name="ck_departments_no_active_children",
    )

    with pytest.raises(DBAPIError) as archive_and_move:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(
                text(
                    "update departments set parent_id = :parent_id, status = 'archived', "
                    "archived_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                    "where id = :id"
                ),
                {"id": RACE_A_ID, "parent_id": RACE_B_ID},
            )
    _assert_database_error(
        archive_and_move.value,
        sqlstate="23514",
        constraint_name="ck_departments_archived_terminal",
    )

    archived_at = datetime.now(UTC)
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        await connection.execute(
            text(
                "update departments set status = 'archived', archived_at = :archived_at, "
                "updated_at = :archived_at where id = :id"
            ),
            {"id": LEAF_A_ID, "archived_at": archived_at},
        )

    with pytest.raises(DBAPIError) as archived_parent:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await _insert_department(
                connection,
                tenant_id=TENANT_A_ID,
                department_id=uuid4(),
                parent_id=LEAF_A_ID,
                code="UNDER-ARCHIVED",
                name="Must not use archived parent",
            )
    _assert_database_error(
        archived_parent.value,
        sqlstate="23514",
        constraint_name="ck_departments_active_parent",
    )

    for update_clause in (
        "name = 'Mutated history'",
        "parent_id = null",
        "status = 'active', archived_at = null",
        "updated_at = CURRENT_TIMESTAMP + interval '1 second'",
    ):
        with pytest.raises(DBAPIError) as terminal_history:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await connection.execute(
                    text(f"update departments set {update_clause} where id = :id"),
                    {"id": LEAF_A_ID},
                )
        _assert_database_error(
            terminal_history.value,
            sqlstate="23514",
            constraint_name="ck_departments_archived_terminal",
        )

    with pytest.raises(DBAPIError) as direct_archived_insert:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(
                text(
                    "insert into departments ("
                    "id, tenant_id, parent_id, code, name, status, archived_at"
                    ") values ("
                    ":id, :tenant_id, null, 'PRE-ARCHIVED', 'Pre-archived', "
                    "'archived', CURRENT_TIMESTAMP)"
                ),
                {"id": uuid4(), "tenant_id": TENANT_A_ID},
            )
    _assert_database_error(
        direct_archived_insert.value,
        sqlstate="23514",
        constraint_name="ck_departments_archived_terminal",
    )


async def _assert_concurrent_opposing_moves_cannot_cycle(engine: AsyncEngine) -> None:
    first_connection = await engine.connect()
    second_connection = await engine.connect()
    first_transaction = await first_connection.begin()
    second_transaction = await second_connection.begin()
    second_move: asyncio.Task[object] | None = None
    try:
        await _set_local_tenant_role(first_connection, TENANT_A_ID)
        await _set_local_tenant_role(second_connection, TENANT_A_ID)

        await first_connection.execute(
            text("update departments set parent_id = :parent_id where id = :id"),
            {"id": RACE_A_ID, "parent_id": RACE_B_ID},
        )
        second_move = asyncio.create_task(
            second_connection.execute(
                text("update departments set parent_id = :parent_id where id = :id"),
                {"id": RACE_B_ID, "parent_id": RACE_A_ID},
            )
        )
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(second_move), timeout=0.25)

        await first_transaction.commit()
        with pytest.raises(DBAPIError) as cycle_error:
            await second_move
        _assert_database_error(
            cycle_error.value,
            sqlstate="23514",
            constraint_name="ck_departments_acyclic",
        )
        await second_transaction.rollback()
    finally:
        if first_transaction.is_active:
            await first_transaction.rollback()
        if second_transaction.is_active:
            await second_transaction.rollback()
        if second_move is not None and not second_move.done():
            second_move.cancel()
            await asyncio.gather(second_move, return_exceptions=True)
        await first_connection.close()
        await second_connection.close()

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        parent_rows = (
            (
                await connection.execute(
                    text(
                        "select id, parent_id from departments where id in (:first_id, :second_id)"
                    ),
                    {"first_id": RACE_A_ID, "second_id": RACE_B_ID},
                )
            )
            .tuples()
            .all()
        )
        parents = {department_id: parent_id for department_id, parent_id in parent_rows}
    assert parents == {RACE_A_ID: RACE_B_ID, RACE_B_ID: None}


async def _assert_multirow_opposing_moves_cannot_cycle(engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError) as cycle_error:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(
                text(
                    "update departments set parent_id = case "
                    "when id = :first_id then :second_id else :first_id end "
                    "where id in (:first_id, :second_id)"
                ),
                {"first_id": RACE_A_ID, "second_id": RACE_B_ID},
            )
    _assert_database_error(
        cycle_error.value,
        sqlstate="23514",
        constraint_name="ck_departments_acyclic",
    )

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        parent_rows = (
            (
                await connection.execute(
                    text(
                        "select id, parent_id from departments where id in (:first_id, :second_id)"
                    ),
                    {"first_id": RACE_A_ID, "second_id": RACE_B_ID},
                )
            )
            .tuples()
            .all()
        )
        parents = {department_id: parent_id for department_id, parent_id in parent_rows}
    assert parents == {RACE_A_ID: None, RACE_B_ID: None}


async def _assert_snapshot_isolation_opposing_moves_cannot_cycle(
    engine: AsyncEngine,
    *,
    isolation_level: str,
) -> None:
    async with engine.begin() as reset_connection:
        await _set_local_tenant_role(reset_connection, TENANT_A_ID)
        await reset_connection.execute(
            text(
                "update departments set parent_id = null "
                "where id in (:first_id, :second_id)"
            ),
            {
                "first_id": REPEATABLE_RACE_A_ID,
                "second_id": REPEATABLE_RACE_B_ID,
            },
        )

    first_connection = await engine.connect()
    second_connection = await engine.connect()
    await first_connection.execution_options(isolation_level=isolation_level)
    await second_connection.execution_options(isolation_level=isolation_level)
    first_transaction = await first_connection.begin()
    second_transaction = await second_connection.begin()
    second_move: asyncio.Task[object] | None = None
    try:
        await _set_local_tenant_role(first_connection, TENANT_A_ID)
        await _set_local_tenant_role(second_connection, TENANT_A_ID)

        # Establish both snapshots before either edge changes. Under REPEATABLE READ, a lock-only
        # sentinel would let the second transaction retain this stale graph after waiting.
        await first_connection.scalar(text("select count(*) from departments"))
        await second_connection.scalar(text("select count(*) from departments"))

        await first_connection.execute(
            text("update departments set parent_id = :parent_id where id = :id"),
            {"id": REPEATABLE_RACE_A_ID, "parent_id": REPEATABLE_RACE_B_ID},
        )
        second_move = asyncio.create_task(
            second_connection.execute(
                text("update departments set parent_id = :parent_id where id = :id"),
                {"id": REPEATABLE_RACE_B_ID, "parent_id": REPEATABLE_RACE_A_ID},
            )
        )
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(second_move), timeout=0.25)

        await first_transaction.commit()
        with pytest.raises(DBAPIError) as serialization_error:
            await second_move
        assert sqlstate_from_error(serialization_error.value) == "40001"
        await second_transaction.rollback()
    finally:
        if first_transaction.is_active:
            await first_transaction.rollback()
        if second_transaction.is_active:
            await second_transaction.rollback()
        if second_move is not None and not second_move.done():
            second_move.cancel()
            await asyncio.gather(second_move, return_exceptions=True)
        await first_connection.close()
        await second_connection.close()

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        parent_rows = (
            (
                await connection.execute(
                    text(
                        "select id, parent_id from departments "
                        "where id in (:first_id, :second_id)"
                    ),
                    {
                        "first_id": REPEATABLE_RACE_A_ID,
                        "second_id": REPEATABLE_RACE_B_ID,
                    },
                )
            )
            .tuples()
            .all()
        )
        parents = {department_id: parent_id for department_id, parent_id in parent_rows}
    assert parents == {
        REPEATABLE_RACE_A_ID: REPEATABLE_RACE_B_ID,
        REPEATABLE_RACE_B_ID: None,
    }


async def _insert_department(
    connection: AsyncConnection,
    *,
    tenant_id: UUID,
    department_id: UUID,
    parent_id: UUID | None,
    code: str,
    name: str,
) -> None:
    await connection.execute(
        text(
            "insert into departments (id, tenant_id, parent_id, code, name, status) "
            "values (:id, :tenant_id, :parent_id, :code, :name, 'active')"
        ),
        {
            "id": department_id,
            "tenant_id": tenant_id,
            "parent_id": parent_id,
            "code": code,
            "name": name,
        },
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
            text(
                "select has_table_privilege("
                ":role_name, :qualified_table_name, :privilege)"
            ),
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


async def _seed_pre_p3f_tenants(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone"
                    ") values "
                    "(:tenant_a, 'p3g-tenant-a', 'P3G Tenant A', 'active', "
                    "'core', 'tr-1', 'en-US', 'Europe/Istanbul'), "
                    "(:tenant_b, 'p3g-tenant-b', 'P3G Tenant B', 'active', "
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
