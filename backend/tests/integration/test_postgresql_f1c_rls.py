from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.api.dependencies import get_phase0_tenant_request_context
from app.core.config import Settings
from app.db.session import get_session
from app.main import create_app
from app.platform.db import (
    MissingDatabaseAccessContextError,
    SqlAlchemyUnitOfWork,
    configure_tenant_database_access,
    sqlstate_from_error,
)
from app.platform.db.tenant_access import (
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from app.platform.request_context import RequestContext
from app.services.employee_service import EmployeeNotFoundError, EmployeeService
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"

TENANT_A_ID = UUID("10000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("10000000-0000-4000-8000-000000000002")
TENANT_C_ID = UUID("10000000-0000-4000-8000-000000000003")
EMPLOYEE_A_ID = UUID("20000000-0000-4000-8000-000000000001")
EMPLOYEE_B_ID = UUID("20000000-0000-4000-8000-000000000002")

TENANT_OWNED_TABLES = frozenset(
    {
        "users",
        "employees",
        "leave_requests",
        "leave_balance_summaries",
        "command_idempotency",
        "tenant_settings",
        "tenant_feature_flags",
        "user_activation_tokens",
        "refresh_session_families",
        "refresh_session_tokens",
    }
)
ROW_SECURITY_TABLES = TENANT_OWNED_TABLES | {"tenants"}
PLATFORM_TABLES = frozenset(
    {"tenants", "tenant_settings", "tenant_feature_flags"}
)
HR_TABLES = ROW_SECURITY_TABLES - PLATFORM_TABLES

TABLE_PRIVILEGES = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})
EXPECTED_APPLICATION_PRIVILEGES = {
    "tenants": frozenset({"SELECT"}),
    "users": frozenset({"SELECT"}),
    "employees": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "leave_requests": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "leave_balance_summaries": frozenset({"SELECT"}),
    "command_idempotency": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "tenant_settings": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "tenant_feature_flags": frozenset({"SELECT"}),
    "user_activation_tokens": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "refresh_session_families": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "refresh_session_tokens": frozenset({"SELECT", "INSERT", "UPDATE"}),
}
EXPECTED_PLATFORM_PRIVILEGES = {
    table_name: (
        frozenset({"SELECT", "INSERT", "UPDATE"})
        if table_name in {"tenants", "tenant_feature_flags"}
        else frozenset({"INSERT"})
        if table_name == "tenant_settings"
        else frozenset()
    )
    for table_name in ROW_SECURITY_TABLES
}


@pytest.fixture
def f1c_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


async def test_f1c_catalog_covers_every_tenant_table_policy_role_and_grant(
    f1c_postgres_database: URL,
) -> None:
    engine = create_async_engine(f1c_postgres_database, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            discovered_tenant_tables = frozenset(
                await connection.scalars(
                    text(
                        "select table_name from information_schema.columns "
                        "where table_schema = 'public' and column_name = 'tenant_id' "
                        "and is_nullable = 'NO'"
                    )
                )
            )
            assert discovered_tenant_tables == TENANT_OWNED_TABLES

            row_security_rows = (
                await connection.execute(
                    text(
                        "select c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                        "pg_get_userbyid(c.relowner) as owner_name "
                        "from pg_catalog.pg_class c "
                        "join pg_catalog.pg_namespace n on n.oid = c.relnamespace "
                        "where n.nspname = 'public' and c.relkind = 'r' "
                        "and c.relname = any(:table_names)"
                    ),
                    {"table_names": sorted(ROW_SECURITY_TABLES)},
                )
            ).mappings()
            row_security = {row["relname"]: row for row in row_security_rows}
            assert set(row_security) == ROW_SECURITY_TABLES
            assert all(row["relrowsecurity"] for row in row_security.values())
            assert all(row["relforcerowsecurity"] for row in row_security.values())
            assert all(
                row["owner_name"] not in {TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE}
                for row in row_security.values()
            )

            policy_rows = (
                await connection.execute(
                    text(
                        "select tablename, policyname, permissive, roles, cmd, qual, with_check "
                        "from pg_catalog.pg_policies where schemaname = 'public' "
                        "and tablename = any(:table_names)"
                    ),
                    {"table_names": sorted(ROW_SECURITY_TABLES)},
                )
            ).mappings()
            policies = {(row["tablename"], row["policyname"]): row for row in policy_rows}
            expected_policy_keys = {
                (table_name, "tenant_isolation_app") for table_name in ROW_SECURITY_TABLES
            } | {
                ("tenants", "platform_operations"),
                ("tenant_settings", "platform_provision_settings"),
                ("tenant_feature_flags", "platform_feature_operations"),
            }
            assert set(policies) == expected_policy_keys

            for table_name in ROW_SECURITY_TABLES:
                policy = policies[(table_name, "tenant_isolation_app")]
                tenant_column = "id" if table_name == "tenants" else "tenant_id"
                assert policy["permissive"] == "PERMISSIVE"
                assert tuple(policy["roles"]) == (TENANT_APPLICATION_ROLE,)
                assert policy["cmd"] == "ALL"
                assert re.search(
                    rf"\b{tenant_column}\s*=",
                    policy["qual"].replace('"', ""),
                )
                assert "app.tenant_id" in policy["qual"]
                assert policy["with_check"] == policy["qual"]

            platform_policy = policies[("tenants", "platform_operations")]
            assert platform_policy["permissive"] == "PERMISSIVE"
            assert tuple(platform_policy["roles"]) == (PLATFORM_APPLICATION_ROLE,)
            assert platform_policy["cmd"] == "ALL"
            assert platform_policy["qual"] == "true"
            assert platform_policy["with_check"] == "true"

            settings_policy = policies[
                ("tenant_settings", "platform_provision_settings")
            ]
            assert settings_policy["permissive"] == "PERMISSIVE"
            assert tuple(settings_policy["roles"]) == (PLATFORM_APPLICATION_ROLE,)
            assert settings_policy["cmd"] == "INSERT"
            assert settings_policy["qual"] is None
            assert settings_policy["with_check"] == "true"

            feature_policy = policies[
                ("tenant_feature_flags", "platform_feature_operations")
            ]
            assert feature_policy["permissive"] == "PERMISSIVE"
            assert tuple(feature_policy["roles"]) == (PLATFORM_APPLICATION_ROLE,)
            assert feature_policy["cmd"] == "ALL"
            assert feature_policy["qual"] == "true"
            assert feature_policy["with_check"] == "true"

            role_rows = (
                await connection.execute(
                    text(
                        "select rolname, rolsuper, rolbypassrls, rolcanlogin, rolinherit, "
                        "rolcreatedb, rolcreaterole, rolreplication "
                        "from pg_catalog.pg_roles where rolname = any(:role_names)"
                    ),
                    {
                        "role_names": [
                            TENANT_APPLICATION_ROLE,
                            PLATFORM_APPLICATION_ROLE,
                        ]
                    },
                )
            ).mappings()
            roles = {row["rolname"]: row for row in role_rows}
            assert set(roles) == {TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE}
            for role in roles.values():
                assert role["rolsuper"] is False
                assert role["rolbypassrls"] is False
                assert role["rolcanlogin"] is False
                assert role["rolinherit"] is False
                assert role["rolcreatedb"] is False
                assert role["rolcreaterole"] is False
                assert role["rolreplication"] is False

            assert not await connection.scalar(
                text("select pg_has_role(:app_role, :platform_role, 'MEMBER')"),
                {
                    "app_role": TENANT_APPLICATION_ROLE,
                    "platform_role": PLATFORM_APPLICATION_ROLE,
                },
            )
            capability_parent_memberships = await connection.scalar(
                text(
                    "select count(*) from pg_catalog.pg_auth_members membership "
                    "join pg_catalog.pg_roles member_role "
                    "on member_role.oid = membership.member "
                    "where member_role.rolname = any(:role_names)"
                ),
                {
                    "role_names": [
                        TENANT_APPLICATION_ROLE,
                        PLATFORM_APPLICATION_ROLE,
                    ]
                },
            )
            assert capability_parent_memberships == 0

            assert await connection.scalar(
                text("select has_schema_privilege(:role_name, 'public', 'USAGE')"),
                {"role_name": TENANT_APPLICATION_ROLE},
            )
            assert await connection.scalar(
                text("select has_schema_privilege(:role_name, 'public', 'USAGE')"),
                {"role_name": PLATFORM_APPLICATION_ROLE},
            )
            assert (
                await _table_privilege_snapshot(
                    connection,
                    TENANT_APPLICATION_ROLE,
                )
                == EXPECTED_APPLICATION_PRIVILEGES
            )
            assert (
                await _table_privilege_snapshot(
                    connection,
                    PLATFORM_APPLICATION_ROLE,
                )
                == EXPECTED_PLATFORM_PRIVILEGES
            )
            app_tenant_update_columns = {
                column_name
                for column_name in (
                    "id",
                    "slug",
                    "name",
                    "status",
                    "plan_code",
                    "data_region",
                    "locale",
                    "timezone",
                    "active_employee_limit",
                    "created_at",
                    "updated_at",
                )
                if await connection.scalar(
                    text(
                        "select has_column_privilege("
                        ":role_name, 'public.tenants', :column_name, 'UPDATE')"
                    ),
                    {
                        "role_name": TENANT_APPLICATION_ROLE,
                        "column_name": column_name,
                    },
                )
            }
            assert app_tenant_update_columns == {
                "locale",
                "timezone",
                "updated_at",
            }
            direct_column_grants = {
                (
                    row["table_name"],
                    row["column_name"],
                    row["privilege_type"],
                    row["grantee"],
                )
                for row in (
                    await connection.execute(
                        text(
                            "select table_class.relname as table_name, "
                            "attribute.attname as column_name, "
                            "privilege.privilege_type, grantee.rolname as grantee "
                            "from pg_catalog.pg_attribute attribute "
                            "join pg_catalog.pg_class table_class "
                            "on table_class.oid = attribute.attrelid "
                            "join pg_catalog.pg_namespace namespace "
                            "on namespace.oid = table_class.relnamespace "
                            "cross join lateral pg_catalog.aclexplode(attribute.attacl) privilege "
                            "join pg_catalog.pg_roles grantee "
                            "on grantee.oid = privilege.grantee "
                            "where namespace.nspname = 'public' "
                            "and table_class.relname = any(:table_names) "
                            "and grantee.rolname = any(:role_names)"
                        ),
                        {
                            "table_names": sorted(ROW_SECURITY_TABLES),
                            "role_names": [
                                TENANT_APPLICATION_ROLE,
                                PLATFORM_APPLICATION_ROLE,
                            ],
                        },
                    )
                ).mappings()
            }
            assert direct_column_grants == {
                ("tenants", "locale", "UPDATE", TENANT_APPLICATION_ROLE),
                ("tenants", "timezone", "UPDATE", TENANT_APPLICATION_ROLE),
                ("tenants", "updated_at", "UPDATE", TENANT_APPLICATION_ROLE),
                ("users", "email", "INSERT", TENANT_APPLICATION_ROLE),
                ("users", "email", "UPDATE", TENANT_APPLICATION_ROLE),
                ("users", "full_name", "INSERT", TENANT_APPLICATION_ROLE),
                ("users", "full_name", "UPDATE", TENANT_APPLICATION_ROLE),
                ("users", "id", "INSERT", TENANT_APPLICATION_ROLE),
                ("users", "password_hash", "INSERT", TENANT_APPLICATION_ROLE),
                ("users", "password_hash", "UPDATE", TENANT_APPLICATION_ROLE),
                ("users", "status", "INSERT", TENANT_APPLICATION_ROLE),
                ("users", "status", "UPDATE", TENANT_APPLICATION_ROLE),
                ("users", "tenant_id", "INSERT", TENANT_APPLICATION_ROLE),
                ("users", "updated_at", "UPDATE", TENANT_APPLICATION_ROLE),
            }
    finally:
        await engine.dispose()


async def test_normal_role_raw_sql_is_tenant_scoped_and_missing_or_invalid_context_fails_closed(
    f1c_postgres_database: URL,
) -> None:
    engine = create_async_engine(f1c_postgres_database, poolclass=NullPool)
    try:
        await _seed_tenants_and_employees(engine)

        async with engine.begin() as connection:
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            await _set_local_tenant(connection, TENANT_A_ID)
            visible_ids = tuple(
                await connection.scalars(text("select id from employees order by id"))
            )
            assert visible_ids == (EMPLOYEE_A_ID,)
            assert (
                await connection.scalar(
                    text("select id from employees where tenant_id = :tenant_id"),
                    {"tenant_id": TENANT_B_ID},
                )
                is None
            )

            update_result = await connection.execute(
                text("update employees set first_name = 'must-not-change' where id = :employee_id"),
                {"employee_id": EMPLOYEE_B_ID},
            )
            assert update_result.rowcount == 0

        with pytest.raises(DBAPIError) as insert_error:
            async with engine.begin() as connection:
                await _set_local_role(connection, TENANT_APPLICATION_ROLE)
                await _set_local_tenant(connection, TENANT_A_ID)
                await connection.execute(
                    text(
                        "insert into employees ("
                        "id, tenant_id, employee_number, first_name, last_name, status, "
                        "employment_start_date"
                        ") values ("
                        ":id, :tenant_id, 'B-INJECTED', 'Blocked', 'Insert', 'active', "
                        "DATE '2026-07-11'"
                        ")"
                    ),
                    {"id": uuid4(), "tenant_id": TENANT_B_ID},
                )
        assert sqlstate_from_error(insert_error.value) == "42501"

        with pytest.raises(DBAPIError) as update_error:
            async with engine.begin() as connection:
                await _set_local_role(connection, TENANT_APPLICATION_ROLE)
                await _set_local_tenant(connection, TENANT_A_ID)
                await connection.execute(
                    text(
                        "update employees set tenant_id = :other_tenant_id where id = :employee_id"
                    ),
                    {
                        "employee_id": EMPLOYEE_A_ID,
                        "other_tenant_id": TENANT_B_ID,
                    },
                )
        assert sqlstate_from_error(update_error.value) == "42501"

        with pytest.raises(DBAPIError) as platform_field_update_error:
            async with engine.begin() as connection:
                await _set_local_role(connection, TENANT_APPLICATION_ROLE)
                await _set_local_tenant(connection, TENANT_A_ID)
                await connection.execute(
                    text(
                        "update tenants set status = 'suspended' "
                        "where id = :tenant_id"
                    ),
                    {"tenant_id": TENANT_A_ID},
                )
        assert sqlstate_from_error(platform_field_update_error.value) == "42501"

        async with engine.begin() as connection:
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            await _set_local_tenant(connection, TENANT_A_ID)
            locale_update = await connection.execute(
                text(
                    "update tenants set locale = 'en-US', updated_at = CURRENT_TIMESTAMP "
                    "where id = :tenant_id"
                ),
                {"tenant_id": TENANT_A_ID},
            )
            assert locale_update.rowcount == 1

        async with engine.begin() as connection:
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            assert tuple(await connection.scalars(text("select id from employees"))) == ()

        with pytest.raises(DBAPIError) as invalid_context_error:
            async with engine.begin() as connection:
                await _set_local_role(connection, TENANT_APPLICATION_ROLE)
                await connection.exec_driver_sql("SET LOCAL app.tenant_id = 'not-a-uuid'")
                await connection.execute(text("select id from employees"))
        assert sqlstate_from_error(invalid_context_error.value) == "22P02"

        async with engine.connect() as connection:
            persisted_rows = {
                row.id: (row.tenant_id, row.first_name)
                for row in (
                    await connection.execute(
                        text("select id, tenant_id, first_name from employees order by id")
                    )
                )
            }
        assert persisted_rows == {
            EMPLOYEE_A_ID: (TENANT_A_ID, "Tenant A"),
            EMPLOYEE_B_ID: (TENANT_B_ID, "Tenant B"),
        }
    finally:
        await engine.dispose()


async def test_platform_role_can_operate_metadata_but_cannot_select_any_hr_table(
    f1c_postgres_database: URL,
) -> None:
    engine = create_async_engine(f1c_postgres_database, poolclass=NullPool)
    try:
        await _seed_tenants_and_employees(engine)

        async with engine.begin() as connection:
            await _set_local_role(connection, PLATFORM_APPLICATION_ROLE)
            assert set(await connection.scalars(text("select id from tenants"))) == {
                TENANT_A_ID,
                TENANT_B_ID,
            }
            await connection.execute(
                text("update tenants set name = 'Platform Updated' where id = :tenant_id"),
                {"tenant_id": TENANT_B_ID},
            )
            await connection.execute(
                text(
                    "update tenants set active_employee_limit = 250 "
                    "where id = :tenant_id"
                ),
                {"tenant_id": TENANT_A_ID},
            )
            await connection.execute(
                text(
                    "update tenant_feature_flags set enabled = true "
                    "where tenant_id = :tenant_id and key = 'documents'"
                ),
                {"tenant_id": TENANT_A_ID},
            )
            await connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone"
                    ") values ("
                    ":id, 'f1c-tenant-c', 'Tenant C', 'provisioning', 'core', "
                    "'tr-1', 'tr-TR', 'Europe/Istanbul'"
                    ")"
                ),
                {"id": TENANT_C_ID},
            )
            await connection.execute(
                text(
                    "insert into tenant_settings ("
                    "tenant_id, week_start_day, date_format, time_format"
                    ") values (:tenant_id, 'monday', 'DD.MM.YYYY', '24h')"
                ),
                {"tenant_id": TENANT_C_ID},
            )
            await connection.execute(
                text(
                    "insert into tenant_feature_flags (tenant_id, key, enabled) "
                    "values (:tenant_id, 'organization', true)"
                ),
                {"tenant_id": TENANT_C_ID},
            )
            assert await connection.scalar(
                text(
                    "select enabled from tenant_feature_flags "
                    "where tenant_id = :tenant_id and key = 'documents'"
                ),
                {"tenant_id": TENANT_A_ID},
            ) is True

        with pytest.raises(DBAPIError) as settings_read_error:
            async with engine.begin() as connection:
                await _set_local_role(connection, PLATFORM_APPLICATION_ROLE)
                await connection.execute(text("select * from tenant_settings"))
        assert sqlstate_from_error(settings_read_error.value) == "42501"

        for table_name in sorted(HR_TABLES):
            with pytest.raises(DBAPIError) as access_error:
                async with engine.begin() as connection:
                    await _set_local_role(connection, PLATFORM_APPLICATION_ROLE)
                    await connection.exec_driver_sql(f'SELECT 1 FROM "{table_name}" LIMIT 1')
            assert sqlstate_from_error(access_error.value) == "42501"

        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("select name from tenants where id = :tenant_id"),
                    {"tenant_id": TENANT_B_ID},
                )
                == "Platform Updated"
            )
            assert (
                await connection.scalar(
                    text("select week_start_day from tenant_settings where tenant_id = :tenant_id"),
                    {"tenant_id": TENANT_C_ID},
                )
                == "monday"
            )
            assert (
                await connection.scalar(
                    text(
                        "select active_employee_limit from tenants "
                        "where id = :tenant_id"
                    ),
                    {"tenant_id": TENANT_A_ID},
                )
                == 250
            )
            assert await connection.scalar(
                text(
                    "select enabled from tenant_feature_flags "
                    "where tenant_id = :tenant_id and key = 'organization'"
                ),
                {"tenant_id": TENANT_C_ID},
            ) is True
            assert not await connection.scalar(
                text(
                    "select has_table_privilege("
                    ":role_name, 'public.tenant_settings', 'SELECT')"
                ),
                {"role_name": PLATFORM_APPLICATION_ROLE},
            )
            for table_name in HR_TABLES:
                assert not await connection.scalar(
                    text("select has_table_privilege(:role_name, :relation_name, 'SELECT')"),
                    {
                        "role_name": PLATFORM_APPLICATION_ROLE,
                        "relation_name": f"public.{table_name}",
                    },
                )
    finally:
        await engine.dispose()


async def test_tenant_feature_flags_are_read_only_and_cross_tenant_hidden(
    f1c_postgres_database: URL,
) -> None:
    engine = create_async_engine(f1c_postgres_database, poolclass=NullPool)
    try:
        await _seed_tenants_and_employees(engine)

        async with engine.begin() as connection:
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            await _set_local_tenant(connection, TENANT_A_ID)
            assert set(
                await connection.scalars(
                    text("select tenant_id from tenant_feature_flags")
                )
            ) == {TENANT_A_ID}
            assert (
                await connection.scalar(
                    text(
                        "select enabled from tenant_feature_flags "
                        "where tenant_id = :tenant_id and key = 'documents'"
                    ),
                    {"tenant_id": TENANT_B_ID},
                )
                is None
            )

        with pytest.raises(DBAPIError) as update_error:
            async with engine.begin() as connection:
                await _set_local_role(connection, TENANT_APPLICATION_ROLE)
                await _set_local_tenant(connection, TENANT_A_ID)
                await connection.execute(
                    text(
                        "update tenant_feature_flags set enabled = true "
                        "where tenant_id = :tenant_id and key = 'documents'"
                    ),
                    {"tenant_id": TENANT_A_ID},
                )
        assert sqlstate_from_error(update_error.value) == "42501"

        async with engine.begin() as connection:
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            await _set_local_tenant(connection, TENANT_B_ID)
            assert set(
                await connection.scalars(
                    text("select tenant_id from tenant_feature_flags")
                )
            ) == {TENANT_B_ID}
    finally:
        await engine.dispose()


async def test_uow_set_local_role_and_tenant_rebind_and_reset_on_one_pool_connection(
    f1c_postgres_database: URL,
) -> None:
    engine = create_async_engine(
        f1c_postgres_database,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _seed_tenants_and_employees(engine)
        initial = await _unbound_connection_state(engine)

        async with session_factory() as missing_context_session:
            with pytest.raises(MissingDatabaseAccessContextError):
                await SqlAlchemyUnitOfWork(missing_context_session).execute(
                    _operation_must_not_run
                )
            assert missing_context_session.in_transaction() is False

        async with session_factory() as session:
            configure_tenant_database_access(session, TENANT_A_ID)
            unit_of_work = SqlAlchemyUnitOfWork(session)
            first_a = await unit_of_work.execute(lambda: _transaction_state(session))
            second_a = await unit_of_work.execute(lambda: _transaction_state(session))

        after_commit = await _unbound_connection_state(engine)

        rollback_state: _TransactionState | None = None
        async with session_factory() as session:
            configure_tenant_database_access(session, TENANT_B_ID)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def fail_after_binding() -> None:
                nonlocal rollback_state
                rollback_state = await _transaction_state(session)
                raise _ExpectedRollback

            with pytest.raises(_ExpectedRollback):
                await unit_of_work.execute(fail_after_binding)
            assert session.in_transaction() is False

            after_rollback = await _unbound_connection_state(engine)
            rebound_b = await unit_of_work.execute(lambda: _transaction_state(session))

        final_reset = await _unbound_connection_state(engine)

        assert rollback_state is not None
        bound_states = (first_a, second_a, rollback_state, rebound_b)
        assert {state.backend_pid for state in bound_states} == {initial.backend_pid}
        assert all(state.current_user == TENANT_APPLICATION_ROLE for state in bound_states)
        assert first_a.tenant_setting == second_a.tenant_setting == str(TENANT_A_ID)
        assert first_a.employee_ids == second_a.employee_ids == (EMPLOYEE_A_ID,)
        assert rollback_state.tenant_setting == rebound_b.tenant_setting == str(TENANT_B_ID)
        assert rollback_state.employee_ids == rebound_b.employee_ids == (EMPLOYEE_B_ID,)

        for reset_state in (after_commit, after_rollback, final_reset):
            assert reset_state.backend_pid == initial.backend_pid
            assert reset_state.current_user == initial.current_user
            assert reset_state.current_user not in {
                TENANT_APPLICATION_ROLE,
                PLATFORM_APPLICATION_ROLE,
            }
            assert reset_state.tenant_setting in {None, ""}
    finally:
        await engine.dispose()


async def test_employee_repository_cannot_retrieve_tenant_b_under_tenant_a_session(
    f1c_postgres_database: URL,
) -> None:
    engine = create_async_engine(f1c_postgres_database, poolclass=NullPool)
    try:
        await _seed_tenants_and_employees(engine)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            configure_tenant_database_access(session, TENANT_A_ID)
            service = EmployeeService(session)

            with pytest.raises(EmployeeNotFoundError):
                await service.get_employee(TENANT_B_ID, EMPLOYEE_B_ID)

            employee = await service.get_employee(TENANT_A_ID, EMPLOYEE_A_ID)
            assert employee.id == EMPLOYEE_A_ID
            assert employee.tenant_id == TENANT_A_ID
    finally:
        await engine.dispose()


async def test_http_request_context_binds_effective_role_and_unfiltered_rls_scope(
    f1c_postgres_database: URL,
) -> None:
    seed_engine = create_async_engine(f1c_postgres_database, poolclass=NullPool)
    await _seed_tenants_and_employees(seed_engine)
    await seed_engine.dispose()

    application = create_app(
        settings=Settings(
            _env_file=None,
            environment="test",
            database_url=f1c_postgres_database.render_as_string(hide_password=False),
        )
    )

    @application.get("/_test/f1c-database-scope")
    async def database_scope_probe(
        request_context: Annotated[
            RequestContext,
            Depends(get_phase0_tenant_request_context),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> dict[str, object]:
        transaction_identity = (
            await session.execute(
                text(
                    "select current_user, current_setting('app.tenant_id', true)"
                )
            )
        ).one()
        employee_ids = tuple(
            await session.scalars(text("select id from employees order by id"))
        )
        return {
            "request_tenant_id": str(
                request_context.require_tenant().tenant_id
            ),
            "current_user": transaction_identity[0],
            "database_tenant_id": transaction_identity[1],
            "employee_ids": [str(employee_id) for employee_id in employee_ids],
        }

    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://f1c-test.local",
        ) as client:
            tenant_a_response = await client.get(
                "/_test/f1c-database-scope",
                headers={"X-Tenant-Id": str(TENANT_A_ID)},
            )
            tenant_b_response = await client.get(
                "/_test/f1c-database-scope",
                headers={"X-Tenant-Id": str(TENANT_B_ID)},
            )

    assert tenant_a_response.status_code == 200
    assert tenant_a_response.json() == {
        "request_tenant_id": str(TENANT_A_ID),
        "current_user": TENANT_APPLICATION_ROLE,
        "database_tenant_id": str(TENANT_A_ID),
        "employee_ids": [str(EMPLOYEE_A_ID)],
    }
    assert tenant_b_response.status_code == 200
    assert tenant_b_response.json() == {
        "request_tenant_id": str(TENANT_B_ID),
        "current_user": TENANT_APPLICATION_ROLE,
        "database_tenant_id": str(TENANT_B_ID),
        "employee_ids": [str(EMPLOYEE_B_ID)],
    }


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


async def _table_privilege_snapshot(
    connection: AsyncConnection,
    role_name: str,
) -> dict[str, frozenset[str]]:
    snapshot: dict[str, frozenset[str]] = {}
    for table_name in ROW_SECURITY_TABLES:
        granted = {
            privilege
            for privilege in TABLE_PRIVILEGES
            if await connection.scalar(
                text("select has_table_privilege(:role_name, :relation_name, :privilege)"),
                {
                    "role_name": role_name,
                    "relation_name": f"public.{table_name}",
                    "privilege": privilege,
                },
            )
        }
        snapshot[table_name] = frozenset(granted)
    return snapshot


async def _seed_tenants_and_employees(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into tenants ("
                "id, slug, name, status, plan_code, data_region, locale, timezone"
                ") values ("
                ":id, :slug, :name, 'active', 'core', 'tr-1', 'tr-TR', 'Europe/Istanbul'"
                ")"
            ),
            [
                {"id": TENANT_A_ID, "slug": "f1c-tenant-a", "name": "Tenant A"},
                {"id": TENANT_B_ID, "slug": "f1c-tenant-b", "name": "Tenant B"},
            ],
        )
        await connection.execute(
            text(
                "insert into tenant_settings (tenant_id, week_start_day, date_format, time_format) "
                "values (:tenant_id, 'monday', 'DD.MM.YYYY', '24h')"
            ),
            [{"tenant_id": TENANT_A_ID}, {"tenant_id": TENANT_B_ID}],
        )
        await connection.execute(
            text(
                "insert into tenant_feature_flags (tenant_id, key, enabled) "
                "values (:tenant_id, 'documents', false)"
            ),
            [{"tenant_id": TENANT_A_ID}, {"tenant_id": TENANT_B_ID}],
        )
        await connection.execute(
            text(
                "insert into employees ("
                "id, tenant_id, employee_number, first_name, last_name, status, "
                "employment_start_date"
                ") values ("
                ":id, :tenant_id, :employee_number, :first_name, 'Employee', 'active', "
                "DATE '2026-07-11'"
                ")"
            ),
            [
                {
                    "id": EMPLOYEE_A_ID,
                    "tenant_id": TENANT_A_ID,
                    "employee_number": "A-001",
                    "first_name": "Tenant A",
                },
                {
                    "id": EMPLOYEE_B_ID,
                    "tenant_id": TENANT_B_ID,
                    "employee_number": "B-001",
                    "first_name": "Tenant B",
                },
            ],
        )


async def _set_local_role(connection: AsyncConnection, role_name: str) -> None:
    await connection.exec_driver_sql(f'SET LOCAL ROLE "{role_name}"')
    assert await connection.scalar(text("select current_user")) == role_name


async def _set_local_tenant(connection: AsyncConnection, tenant_id: UUID) -> None:
    await connection.exec_driver_sql(f"SET LOCAL app.tenant_id = '{tenant_id}'")


@dataclass(frozen=True, slots=True)
class _ConnectionState:
    backend_pid: int
    current_user: str
    tenant_setting: str | None


@dataclass(frozen=True, slots=True)
class _TransactionState(_ConnectionState):
    employee_ids: tuple[UUID, ...]


async def _unbound_connection_state(engine: AsyncEngine) -> _ConnectionState:
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "select pg_backend_pid(), current_user, current_setting('app.tenant_id', true)"
                )
            )
        ).one()
        return _ConnectionState(
            backend_pid=int(row[0]),
            current_user=str(row[1]),
            tenant_setting=row[2],
        )


async def _transaction_state(session: AsyncSession) -> _TransactionState:
    row = (
        await session.execute(
            text("select pg_backend_pid(), current_user, current_setting('app.tenant_id', true)")
        )
    ).one()
    employee_ids = tuple(await session.scalars(text("select id from employees order by id")))
    return _TransactionState(
        backend_pid=int(row[0]),
        current_user=str(row[1]),
        tenant_setting=row[2],
        employee_ids=employee_ids,
    )


class _ExpectedRollback(Exception):
    pass


async def _operation_must_not_run() -> None:
    raise AssertionError("A PostgreSQL UoW must fail before an unscoped operation runs")
