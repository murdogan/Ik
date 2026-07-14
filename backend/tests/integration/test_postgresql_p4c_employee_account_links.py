from __future__ import annotations

import asyncio
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
PRE_P4C_REVISION = "0033_p4b_employee_profiles"
P4C_REVISION = "0034_p4c_employee_account_links"

LINKS_TABLE = "employee_account_links"
ELIGIBILITY_FUNCTION = "public.is_current_tenant_membership_link_eligible(uuid)"
ELIGIBILITY_OWNER_ROLE = "wealthy_falcon_identity_recovery"
IDENTITY_PROJECTION_ROLE = "wealthy_falcon_identity_projection"

TENANT_A_ID = UUID("c4000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("c4000000-0000-4000-8000-000000000002")

EMPLOYEE_A1_ID = UUID("c4100000-0000-4000-8000-000000000001")
EMPLOYEE_A2_ID = UUID("c4100000-0000-4000-8000-000000000002")
EMPLOYEE_A3_ID = UUID("c4100000-0000-4000-8000-000000000003")
EMPLOYEE_B1_ID = UUID("c4100000-0000-4000-8000-000000000004")

USER_A1_ID = UUID("c4200000-0000-4000-8000-000000000001")
USER_A2_ID = UUID("c4200000-0000-4000-8000-000000000002")
USER_A3_ID = UUID("c4200000-0000-4000-8000-000000000003")
USER_A_INVITED_ID = UUID("c4200000-0000-4000-8000-000000000004")
USER_B1_ID = UUID("c4200000-0000-4000-8000-000000000005")

MEMBERSHIP_A1_ID = UUID("c4300000-0000-4000-8000-000000000001")
MEMBERSHIP_A2_ID = UUID("c4300000-0000-4000-8000-000000000002")
MEMBERSHIP_A3_ID = UUID("c4300000-0000-4000-8000-000000000003")
MEMBERSHIP_A_INVITED_ID = UUID("c4300000-0000-4000-8000-000000000004")
MEMBERSHIP_B1_ID = UUID("c4300000-0000-4000-8000-000000000005")

SHARED_IDENTITY_ID = UUID("c4400000-0000-4000-8000-000000000001")
IDENTITY_A2_ID = UUID("c4400000-0000-4000-8000-000000000002")
IDENTITY_A3_ID = UUID("c4400000-0000-4000-8000-000000000003")
INVITED_IDENTITY_ID = UUID("c4400000-0000-4000-8000-000000000004")

EXPECTED_COLUMNS = {
    "id",
    "tenant_id",
    "employee_id",
    "membership_id",
    "version",
    "created_at",
    "updated_at",
}


def test_p4c_postgresql_catalog_security_direct_attacks_and_safe_round_trip(
    postgres_database_url: URL,
) -> None:
    config = _prepare_p4c_database(postgres_database_url)

    asyncio.run(_assert_p4c_contract(postgres_database_url))
    asyncio.run(_delete_all_links(postgres_database_url))

    alembic_command.downgrade(config, PRE_P4C_REVISION)
    assert asyncio.run(_current_revision(postgres_database_url)) == PRE_P4C_REVISION
    assert not asyncio.run(_table_exists(postgres_database_url, LINKS_TABLE))
    assert not asyncio.run(_function_exists(postgres_database_url))
    assert asyncio.run(_source_row_counts(postgres_database_url)) == (4, 5)

    alembic_command.upgrade(config, P4C_REVISION)
    assert asyncio.run(_link_count(postgres_database_url)) == 0


def test_p4c_postgresql_downgrade_refuses_current_links_and_restores_force_rls(
    postgres_database_url: URL,
) -> None:
    config = _prepare_p4c_database(postgres_database_url)
    asyncio.run(
        _insert_link_as_tenant(
            postgres_database_url,
            tenant_id=TENANT_A_ID,
            employee_id=EMPLOYEE_A1_ID,
            membership_id=MEMBERSHIP_A1_ID,
        )
    )

    with pytest.raises(
        RuntimeError,
        match="P4C employee account link downgrade refused: current_links=1",
    ):
        alembic_command.downgrade(config, PRE_P4C_REVISION)

    assert asyncio.run(_current_revision(postgres_database_url)) == P4C_REVISION
    assert asyncio.run(_row_security_flags(postgres_database_url)) == (True, True)
    assert asyncio.run(_link_count(postgres_database_url)) == 1
    assert asyncio.run(_function_exists(postgres_database_url))


def test_p4c_postgresql_concurrent_employee_and_membership_uniqueness(
    postgres_database_url: URL,
) -> None:
    _prepare_p4c_database(postgres_database_url)

    employee_race = asyncio.run(
        _race_link_inserts(
            postgres_database_url,
            first=(EMPLOYEE_A1_ID, MEMBERSHIP_A1_ID),
            second=(EMPLOYEE_A1_ID, MEMBERSHIP_A2_ID),
        )
    )
    _assert_one_race_winner(
        employee_race,
        constraint_name="uq_employee_account_links_tenant_employee_id",
    )

    asyncio.run(_delete_all_links(postgres_database_url))
    membership_race = asyncio.run(
        _race_link_inserts(
            postgres_database_url,
            first=(EMPLOYEE_A1_ID, MEMBERSHIP_A1_ID),
            second=(EMPLOYEE_A2_ID, MEMBERSHIP_A1_ID),
        )
    )
    _assert_one_race_winner(
        membership_race,
        constraint_name="uq_employee_account_links_tenant_membership_id",
    )


def test_p4c_postgresql_concurrent_relink_and_unlink_have_one_version_winner(
    postgres_database_url: URL,
) -> None:
    _prepare_p4c_database(postgres_database_url)
    link_id = uuid4()
    asyncio.run(
        _insert_link_as_tenant(
            postgres_database_url,
            tenant_id=TENANT_A_ID,
            employee_id=EMPLOYEE_A1_ID,
            membership_id=MEMBERSHIP_A1_ID,
            link_id=link_id,
        )
    )

    rowcounts, final_link = asyncio.run(
        _race_optimistic_relink_and_unlink(
            postgres_database_url,
            link_id=link_id,
        )
    )

    assert sorted(rowcounts.values()) == [0, 1]
    if rowcounts["relink"] == 1:
        assert final_link == (MEMBERSHIP_A2_ID, 2)
    else:
        assert rowcounts["unlink"] == 1
        assert final_link is None


def _prepare_p4c_database(database_url: URL) -> Config:
    config = _alembic_config(database_url)
    alembic_command.upgrade(config, PRE_P4C_REVISION)
    asyncio.run(_seed_pre_p4c_fixture(database_url))
    asyncio.run(_grant_hostile_default_privileges(database_url))
    alembic_command.upgrade(config, P4C_REVISION)
    return config


async def _assert_p4c_contract(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        assert await _link_count_from_engine(engine) == 0
        await _assert_catalog_and_acl(engine)
        await _assert_eligibility_function(engine)
        await _assert_direct_integrity_and_rls(engine)
    finally:
        await engine.dispose()


async def _assert_catalog_and_acl(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        columns = {
            row.column_name: row
            for row in (
                await connection.execute(
                    text(
                        "select column_name, data_type, is_nullable, column_default "
                        "from information_schema.columns "
                        "where table_schema = 'public' "
                        "and table_name = 'employee_account_links'"
                    )
                )
            )
        }
        assert set(columns) == EXPECTED_COLUMNS
        for column_name in ("id", "tenant_id", "employee_id", "membership_id"):
            assert columns[column_name].data_type == "uuid"
            assert columns[column_name].is_nullable == "NO"
        assert columns["version"].data_type == "integer"
        assert columns["version"].is_nullable == "NO"
        assert columns["version"].column_default == "1"
        for column_name in ("created_at", "updated_at"):
            assert columns[column_name].data_type == "timestamp with time zone"
            assert columns[column_name].is_nullable == "NO"
            assert columns[column_name].column_default is not None

        constraints = {
            row.constraint_name: row.constraint_type
            for row in (
                await connection.execute(
                    text(
                        "select constraint_name, constraint_type "
                        "from information_schema.table_constraints "
                        "where table_schema = 'public' "
                        "and table_name = 'employee_account_links'"
                    )
                )
            )
        }
        assert constraints == {
            "pk_employee_account_links": "PRIMARY KEY",
            "ck_employee_account_links_version_positive": "CHECK",
            "fk_employee_account_links_tenant_id_tenants": "FOREIGN KEY",
            "fk_employee_account_links_tenant_employee_id_employees": "FOREIGN KEY",
            "fk_employee_account_links_tenant_membership_id_memberships": "FOREIGN KEY",
            "uq_employee_account_links_tenant_id_id": "UNIQUE",
            "uq_employee_account_links_tenant_employee_id": "UNIQUE",
            "uq_employee_account_links_tenant_membership_id": "UNIQUE",
        }

        foreign_keys = {
            row.constraint_name: row.definition
            for row in (
                await connection.execute(
                    text(
                        "select constraint_record.conname as constraint_name, "
                        "pg_get_constraintdef(constraint_record.oid) as definition "
                        "from pg_catalog.pg_constraint as constraint_record "
                        "where constraint_record.conrelid = "
                        "'public.employee_account_links'::regclass "
                        "and constraint_record.contype = 'f'"
                    )
                )
            )
        }
        assert foreign_keys == {
            "fk_employee_account_links_tenant_id_tenants": (
                "FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE"
            ),
            "fk_employee_account_links_tenant_employee_id_employees": (
                "FOREIGN KEY (tenant_id, employee_id) "
                "REFERENCES employees(tenant_id, id) ON DELETE RESTRICT"
            ),
            "fk_employee_account_links_tenant_membership_id_memberships": (
                "FOREIGN KEY (tenant_id, membership_id) "
                "REFERENCES tenant_memberships(tenant_id, id) ON DELETE RESTRICT"
            ),
        }

        index_names = set(
            await connection.scalars(
                text(
                    "select indexname from pg_catalog.pg_indexes "
                    "where schemaname = 'public' "
                    "and tablename = 'employee_account_links'"
                )
            )
        )
        assert index_names == {
            "pk_employee_account_links",
            "uq_employee_account_links_tenant_id_id",
            "uq_employee_account_links_tenant_employee_id",
            "uq_employee_account_links_tenant_membership_id",
        }

        assert await _row_security_flags_from_connection(connection) == (True, True)
        policy = (
            (
                await connection.execute(
                    text(
                        "select policyname, roles, cmd, qual, with_check "
                        "from pg_catalog.pg_policies where schemaname = 'public' "
                        "and tablename = 'employee_account_links'"
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

        assert await _direct_table_privileges(
            connection,
            role_name=TENANT_APPLICATION_ROLE,
        ) == {"SELECT", "INSERT", "DELETE"}
        assert await _direct_update_columns(
            connection,
            role_name=TENANT_APPLICATION_ROLE,
        ) == {"membership_id", "version", "updated_at"}
        for role_name in (
            "PUBLIC",
            PLATFORM_APPLICATION_ROLE,
            AUTHENTICATION_APPLICATION_ROLE,
            IDENTITY_PROJECTION_ROLE,
            ELIGIBILITY_OWNER_ROLE,
        ):
            assert await _direct_table_privileges(connection, role_name=role_name) == set()
            assert await _direct_update_columns(connection, role_name=role_name) == set()

        function = (
            await connection.execute(
                text(
                    "select procedure.prosecdef, procedure.provolatile, procedure.proconfig, "
                    "owner.rolname as owner_name, pg_get_functiondef(procedure.oid) as definition "
                    "from pg_catalog.pg_proc as procedure "
                    "join pg_catalog.pg_roles as owner on owner.oid = procedure.proowner "
                    "where procedure.oid = "
                    "'public.is_current_tenant_membership_link_eligible(uuid)'::regprocedure"
                )
            )
        ).mappings().one()
        assert function["prosecdef"] is True
        assert function["provolatile"] == "s"
        assert function["owner_name"] == ELIGIBILITY_OWNER_ROLE
        assert function["proconfig"] == ["search_path=pg_catalog, public"]
        definition = str(function["definition"]).lower()
        for required_fragment in (
            "from public.tenant_memberships",
            "join public.users",
            "join public.identities",
            "current_setting('app.tenant_id', true)",
            "membership.status = 'active'",
            "legacy_user.status = 'active'",
            "canonical_identity.status = 'active'",
            "membership.permission_version = legacy_user.permission_version",
        ):
            assert required_fragment in definition
        assert "email" not in definition
        assert "password" not in definition

        assert await _has_function_execute(
            connection,
            role_name=TENANT_APPLICATION_ROLE,
        )
        for role_name in (
            PLATFORM_APPLICATION_ROLE,
            AUTHENTICATION_APPLICATION_ROLE,
            IDENTITY_PROJECTION_ROLE,
        ):
            assert not await _has_function_execute(connection, role_name=role_name)
        public_execute = await connection.scalar(
            text(
                "select exists (select 1 from information_schema.routine_privileges "
                "where specific_schema = 'public' "
                "and routine_name = 'is_current_tenant_membership_link_eligible' "
                "and grantee = 'PUBLIC' and privilege_type = 'EXECUTE')"
            )
        )
        assert public_execute is False


async def _assert_eligibility_function(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        assert await _membership_is_eligible(connection, MEMBERSHIP_A1_ID)
        assert not await _membership_is_eligible(connection, MEMBERSHIP_B1_ID)
        assert not await _membership_is_eligible(connection, MEMBERSHIP_A_INVITED_ID)

    async with engine.begin() as connection:
        await _set_local_role(connection, TENANT_APPLICATION_ROLE)
        assert not await _membership_is_eligible(connection, MEMBERSHIP_A1_ID)

    for role_name in (PLATFORM_APPLICATION_ROLE, AUTHENTICATION_APPLICATION_ROLE):
        with pytest.raises(DBAPIError) as denied:
            async with engine.begin() as connection:
                await _set_local_role(connection, role_name)
                await _membership_is_eligible(connection, MEMBERSHIP_A1_ID)
        assert sqlstate_from_error(denied.value) == "42501"

    with pytest.raises(DBAPIError) as denied_identity_read:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(text("select id, status from identities"))
    assert sqlstate_from_error(denied_identity_read.value) == "42501"

    for table_name, column_name, changed_value in (
        ("tenant_memberships", "status", "locked"),
        ("users", "status", "disabled"),
        ("identities", "status", "disabled"),
        ("tenant_memberships", "permission_version", 2),
    ):
        await _set_eligibility_state(
            engine,
            table_name=table_name,
            column_name=column_name,
            value=changed_value,
        )
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            assert not await _membership_is_eligible(connection, MEMBERSHIP_A1_ID)
        await _restore_eligibility_state(
            engine,
            table_name=table_name,
            column_name=column_name,
        )


async def _assert_direct_integrity_and_rls(engine: AsyncEngine) -> None:
    link_a1_id = uuid4()
    await _insert_link_with_engine(
        engine,
        link_id=link_a1_id,
        tenant_id=TENANT_A_ID,
        employee_id=EMPLOYEE_A1_ID,
        membership_id=MEMBERSHIP_A1_ID,
    )

    await _assert_rejected_mutation(
        engine,
        text(
            "update employee_account_links set version = 0 "
            "where tenant_id = :tenant_id and id = :link_id"
        ),
        {"tenant_id": TENANT_A_ID, "link_id": link_a1_id},
        tenant_id=TENANT_A_ID,
        sqlstate="23514",
        constraint_name="ck_employee_account_links_version_positive",
    )
    await _assert_rejected_mutation(
        engine,
        _insert_link_statement(),
        _link_parameters(
            tenant_id=TENANT_A_ID,
            employee_id=EMPLOYEE_A1_ID,
            membership_id=MEMBERSHIP_A2_ID,
        ),
        tenant_id=TENANT_A_ID,
        sqlstate="23505",
        constraint_name="uq_employee_account_links_tenant_employee_id",
    )
    await _assert_rejected_mutation(
        engine,
        _insert_link_statement(),
        _link_parameters(
            tenant_id=TENANT_A_ID,
            employee_id=EMPLOYEE_A2_ID,
            membership_id=MEMBERSHIP_A1_ID,
        ),
        tenant_id=TENANT_A_ID,
        sqlstate="23505",
        constraint_name="uq_employee_account_links_tenant_membership_id",
    )
    await _assert_rejected_mutation(
        engine,
        _insert_link_statement(),
        _link_parameters(
            tenant_id=TENANT_A_ID,
            employee_id=EMPLOYEE_B1_ID,
            membership_id=MEMBERSHIP_A2_ID,
        ),
        tenant_id=TENANT_A_ID,
        sqlstate="23503",
        constraint_name="fk_employee_account_links_tenant_employee_id_employees",
    )
    await _assert_rejected_mutation(
        engine,
        _insert_link_statement(),
        _link_parameters(
            tenant_id=TENANT_A_ID,
            employee_id=EMPLOYEE_A2_ID,
            membership_id=MEMBERSHIP_B1_ID,
        ),
        tenant_id=TENANT_A_ID,
        sqlstate="23503",
        constraint_name="fk_employee_account_links_tenant_membership_id_memberships",
    )
    await _assert_rejected_mutation(
        engine,
        _insert_link_statement(),
        _link_parameters(
            tenant_id=TENANT_B_ID,
            employee_id=EMPLOYEE_B1_ID,
            membership_id=MEMBERSHIP_B1_ID,
        ),
        tenant_id=TENANT_A_ID,
        sqlstate="42501",
        constraint_name=None,
    )

    await _insert_link_with_engine(
        engine,
        tenant_id=TENANT_A_ID,
        employee_id=EMPLOYEE_A2_ID,
        membership_id=MEMBERSHIP_A2_ID,
    )
    await _insert_link_with_engine(
        engine,
        tenant_id=TENANT_B_ID,
        employee_id=EMPLOYEE_B1_ID,
        membership_id=MEMBERSHIP_B1_ID,
    )

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        visible_a = tuple(
            await connection.scalars(
                text("select membership_id from employee_account_links order by membership_id")
            )
        )
        assert visible_a == (MEMBERSHIP_A1_ID, MEMBERSHIP_A2_ID)
        assert not await _membership_is_eligible(connection, MEMBERSHIP_B1_ID)

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_B_ID)
        visible_b = tuple(
            await connection.scalars(
                text("select membership_id from employee_account_links order by membership_id")
            )
        )
        assert visible_b == (MEMBERSHIP_B1_ID,)
        assert not await _membership_is_eligible(connection, MEMBERSHIP_A1_ID)

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        deleted = await connection.execute(
            text("delete from employee_account_links where id = :link_id"),
            {"link_id": link_a1_id},
        )
        assert deleted.rowcount == 1
        assert await connection.scalar(text("select count(*) from employee_account_links")) == 1


async def _seed_pre_p4c_fixture(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone"
                    ") values "
                    "(:tenant_a, 'p4c-a', 'P4C Tenant A', 'active', 'core', "
                    "'tr-1', 'en-US', 'UTC'), "
                    "(:tenant_b, 'p4c-b', 'P4C Tenant B', 'active', 'core', "
                    "'tr-1', 'en-US', 'UTC')"
                ),
                {"tenant_a": TENANT_A_ID, "tenant_b": TENANT_B_ID},
            )
            await connection.execute(
                text(
                    "insert into identities (id, email, status, password_hash) values "
                    "(:shared, 'shared@p4c.test', 'active', 'p4c-hash'), "
                    "(:identity_a2, 'a2@p4c.test', 'active', 'p4c-hash'), "
                    "(:identity_a3, 'a3@p4c.test', 'active', 'p4c-hash'), "
                    "(:invited, 'invited@p4c.test', 'pending', null)"
                ),
                {
                    "shared": SHARED_IDENTITY_ID,
                    "identity_a2": IDENTITY_A2_ID,
                    "identity_a3": IDENTITY_A3_ID,
                    "invited": INVITED_IDENTITY_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into users ("
                    "id, tenant_id, email, full_name, status, password_hash, permission_version"
                    ") values "
                    "(:user_a1, :tenant_a, 'shared@p4c.test', 'Shared A', "
                    "'active', 'p4c-hash', 1), "
                    "(:user_a2, :tenant_a, 'a2@p4c.test', 'Account A2', "
                    "'active', 'p4c-hash', 1), "
                    "(:user_a3, :tenant_a, 'a3@p4c.test', 'Account A3', "
                    "'active', 'p4c-hash', 1), "
                    "(:user_invited, :tenant_a, 'invited@p4c.test', 'Invited A', "
                    "'invited', null, 1), "
                    "(:user_b1, :tenant_b, 'shared@p4c.test', 'Shared B', "
                    "'active', 'p4c-hash', 1)"
                ),
                {
                    "tenant_a": TENANT_A_ID,
                    "tenant_b": TENANT_B_ID,
                    "user_a1": USER_A1_ID,
                    "user_a2": USER_A2_ID,
                    "user_a3": USER_A3_ID,
                    "user_invited": USER_A_INVITED_ID,
                    "user_b1": USER_B1_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into tenant_memberships ("
                    "id, tenant_id, identity_id, legacy_user_id, full_name, status, "
                    "permission_version"
                    ") values "
                    "(:membership_a1, :tenant_a, :shared, :user_a1, 'Shared A', 'active', 1), "
                    "(:membership_a2, :tenant_a, :identity_a2, :user_a2, "
                    "'Account A2', 'active', 1), "
                    "(:membership_a3, :tenant_a, :identity_a3, :user_a3, "
                    "'Account A3', 'active', 1), "
                    "(:membership_invited, :tenant_a, :invited, :user_invited, "
                    "'Invited A', 'invited', 1), "
                    "(:membership_b1, :tenant_b, :shared, :user_b1, 'Shared B', 'active', 1)"
                ),
                {
                    "tenant_a": TENANT_A_ID,
                    "tenant_b": TENANT_B_ID,
                    "shared": SHARED_IDENTITY_ID,
                    "identity_a2": IDENTITY_A2_ID,
                    "identity_a3": IDENTITY_A3_ID,
                    "invited": INVITED_IDENTITY_ID,
                    "membership_a1": MEMBERSHIP_A1_ID,
                    "membership_a2": MEMBERSHIP_A2_ID,
                    "membership_a3": MEMBERSHIP_A3_ID,
                    "membership_invited": MEMBERSHIP_A_INVITED_ID,
                    "membership_b1": MEMBERSHIP_B1_ID,
                    "user_a1": USER_A1_ID,
                    "user_a2": USER_A2_ID,
                    "user_a3": USER_A3_ID,
                    "user_invited": USER_A_INVITED_ID,
                    "user_b1": USER_B1_ID,
                },
            )
            for employee_id, tenant_id, number, email in (
                (EMPLOYEE_A1_ID, TENANT_A_ID, "P4C-A1", "shared@p4c.test"),
                (EMPLOYEE_A2_ID, TENANT_A_ID, "P4C-A2", "a2@p4c.test"),
                (EMPLOYEE_A3_ID, TENANT_A_ID, "P4C-A3", "a3@p4c.test"),
                (EMPLOYEE_B1_ID, TENANT_B_ID, "P4C-B1", "shared@p4c.test"),
            ):
                await connection.execute(
                    text(
                        "insert into employees ("
                        "id, tenant_id, employee_number, first_name, last_name, email, "
                        "status, employment_start_date"
                        ") values ("
                        ":id, :tenant_id, :number, 'P4C', 'Employee', :email, "
                        "'active', DATE '2026-07-01')"
                    ),
                    {
                        "id": employee_id,
                        "tenant_id": tenant_id,
                        "number": number,
                        "email": email,
                    },
                )
    finally:
        await engine.dispose()


async def _grant_hostile_default_privileges(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            for role_name in (
                "PUBLIC",
                TENANT_APPLICATION_ROLE,
                PLATFORM_APPLICATION_ROLE,
                AUTHENTICATION_APPLICATION_ROLE,
                IDENTITY_PROJECTION_ROLE,
                ELIGIBILITY_OWNER_ROLE,
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
                await connection.exec_driver_sql(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    f"GRANT ALL PRIVILEGES ON FUNCTIONS TO {quoted_role}"
                )
    finally:
        await engine.dispose()


async def _set_eligibility_state(
    engine: AsyncEngine,
    *,
    table_name: str,
    column_name: str,
    value: object,
) -> None:
    identifiers = {
        "tenant_memberships": MEMBERSHIP_A1_ID,
        "users": USER_A1_ID,
        "identities": SHARED_IDENTITY_ID,
    }
    async with engine.begin() as connection:
        await connection.execute(
            text(f"update {table_name} set {column_name} = :value where id = :id"),
            {"value": value, "id": identifiers[table_name]},
        )


async def _restore_eligibility_state(
    engine: AsyncEngine,
    *,
    table_name: str,
    column_name: str,
) -> None:
    value: object = 1 if column_name == "permission_version" else "active"
    await _set_eligibility_state(
        engine,
        table_name=table_name,
        column_name=column_name,
        value=value,
    )


async def _membership_is_eligible(
    connection: AsyncConnection,
    membership_id: UUID,
) -> bool:
    return bool(
        await connection.scalar(
            text(
                "select public.is_current_tenant_membership_link_eligible(:membership_id)"
            ),
            {"membership_id": membership_id},
        )
    )


async def _insert_link_as_tenant(
    database_url: URL,
    *,
    tenant_id: UUID,
    employee_id: UUID,
    membership_id: UUID,
    link_id: UUID | None = None,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        await _insert_link_with_engine(
            engine,
            tenant_id=tenant_id,
            employee_id=employee_id,
            membership_id=membership_id,
            link_id=link_id,
        )
    finally:
        await engine.dispose()


async def _insert_link_with_engine(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    employee_id: UUID,
    membership_id: UUID,
    link_id: UUID | None = None,
) -> None:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, tenant_id)
        await connection.execute(
            _insert_link_statement(),
            _link_parameters(
                link_id=link_id,
                tenant_id=tenant_id,
                employee_id=employee_id,
                membership_id=membership_id,
            ),
        )


def _insert_link_statement():
    return text(
        "insert into employee_account_links ("
        "id, tenant_id, employee_id, membership_id, version"
        ") values (:id, :tenant_id, :employee_id, :membership_id, 1)"
    )


def _link_parameters(
    *,
    tenant_id: UUID,
    employee_id: UUID,
    membership_id: UUID,
    link_id: UUID | None = None,
) -> dict[str, object]:
    return {
        "id": link_id or uuid4(),
        "tenant_id": tenant_id,
        "employee_id": employee_id,
        "membership_id": membership_id,
    }


async def _assert_rejected_mutation(
    engine: AsyncEngine,
    statement,
    parameters: dict[str, object],
    *,
    tenant_id: UUID,
    sqlstate: str,
    constraint_name: str | None,
) -> None:
    with pytest.raises(DBAPIError) as error:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, tenant_id)
            await connection.execute(statement, parameters)
    assert sqlstate_from_error(error.value) == sqlstate
    if constraint_name is not None:
        assert constraint_name_from_error(error.value) == constraint_name


async def _race_link_inserts(
    database_url: URL,
    *,
    first: tuple[UUID, UUID],
    second: tuple[UUID, UUID],
) -> tuple[tuple[str, str | None, str | None], ...]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    ready: asyncio.Queue[None] = asyncio.Queue()
    release = asyncio.Event()

    async def contender(
        employee_id: UUID,
        membership_id: UUID,
    ) -> tuple[str, str | None, str | None]:
        try:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await ready.put(None)
                await release.wait()
                await connection.execute(
                    _insert_link_statement(),
                    _link_parameters(
                        tenant_id=TENANT_A_ID,
                        employee_id=employee_id,
                        membership_id=membership_id,
                    ),
                )
            return ("success", None, None)
        except DBAPIError as error:
            return (
                "error",
                sqlstate_from_error(error),
                constraint_name_from_error(error),
            )

    tasks: tuple[asyncio.Task[tuple[str, str | None, str | None]], ...] = ()
    try:
        tasks = (
            asyncio.create_task(contender(*first)),
            asyncio.create_task(contender(*second)),
        )
        await asyncio.wait_for(ready.get(), timeout=5)
        await asyncio.wait_for(ready.get(), timeout=5)
        release.set()
        return tuple(await asyncio.wait_for(asyncio.gather(*tasks), timeout=10))
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()


async def _race_optimistic_relink_and_unlink(
    database_url: URL,
    *,
    link_id: UUID,
) -> tuple[dict[str, int], tuple[UUID, int] | None]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    ready: asyncio.Queue[None] = asyncio.Queue()
    release = asyncio.Event()

    statements = {
        "relink": text(
            "update employee_account_links "
            "set membership_id = :membership_id, version = :next_version, "
            "updated_at = CURRENT_TIMESTAMP "
            "where tenant_id = :tenant_id and id = :link_id "
            "and version = :expected_version"
        ),
        "unlink": text(
            "delete from employee_account_links "
            "where tenant_id = :tenant_id and id = :link_id "
            "and version = :expected_version"
        ),
    }
    parameters = {
        "tenant_id": TENANT_A_ID,
        "link_id": link_id,
        "membership_id": MEMBERSHIP_A2_ID,
        "expected_version": 1,
        "next_version": 2,
    }

    async def contender(operation: str) -> tuple[str, int]:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await ready.put(None)
            await release.wait()
            result = await connection.execute(statements[operation], parameters)
            return operation, int(result.rowcount)

    tasks: tuple[asyncio.Task[tuple[str, int]], ...] = ()
    try:
        tasks = (
            asyncio.create_task(contender("relink")),
            asyncio.create_task(contender("unlink")),
        )
        await asyncio.wait_for(ready.get(), timeout=5)
        await asyncio.wait_for(ready.get(), timeout=5)
        release.set()
        outcomes = dict(await asyncio.wait_for(asyncio.gather(*tasks), timeout=10))

        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            final_link_row = (
                await connection.execute(
                    text(
                        "select membership_id, version from employee_account_links "
                        "where tenant_id = :tenant_id and id = :link_id"
                    ),
                    {"tenant_id": TENANT_A_ID, "link_id": link_id},
                )
            ).one_or_none()
        final_link = (
            None
            if final_link_row is None
            else (final_link_row.membership_id, int(final_link_row.version))
        )
        return outcomes, final_link
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()


def _assert_one_race_winner(
    results: tuple[tuple[str, str | None, str | None], ...],
    *,
    constraint_name: str,
) -> None:
    assert [result[0] for result in results].count("success") == 1
    assert [result for result in results if result[0] == "error"] == [
        ("error", "23505", constraint_name)
    ]


async def _direct_table_privileges(
    connection: AsyncConnection,
    *,
    role_name: str,
) -> set[str]:
    return set(
        await connection.scalars(
            text(
                "select privilege_type from information_schema.table_privileges "
                "where table_schema = 'public' and table_name = 'employee_account_links' "
                "and grantee = :role_name"
            ),
            {"role_name": role_name},
        )
    )


async def _direct_update_columns(
    connection: AsyncConnection,
    *,
    role_name: str,
) -> set[str]:
    return set(
        await connection.scalars(
            text(
                "select column_name from information_schema.column_privileges "
                "where table_schema = 'public' and table_name = 'employee_account_links' "
                "and grantee = :role_name and privilege_type = 'UPDATE'"
            ),
            {"role_name": role_name},
        )
    )


async def _has_function_execute(
    connection: AsyncConnection,
    *,
    role_name: str,
) -> bool:
    return bool(
        await connection.scalar(
            text(
                "select has_function_privilege("
                ":role_name, :function_signature, 'EXECUTE')"
            ),
            {
                "role_name": role_name,
                "function_signature": ELIGIBILITY_FUNCTION,
            },
        )
    )


async def _delete_all_links(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("delete from employee_account_links"))
    finally:
        await engine.dispose()


async def _link_count(database_url: URL) -> int:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        return await _link_count_from_engine(engine)
    finally:
        await engine.dispose()


async def _link_count_from_engine(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return int(await connection.scalar(text("select count(*) from employee_account_links")))


async def _current_revision(database_url: URL) -> str | None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("select version_num from alembic_version"))
    finally:
        await engine.dispose()


async def _table_exists(database_url: URL, table_name: str) -> bool:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text("select to_regclass(:table_name) is not null"),
                    {"table_name": f"public.{table_name}"},
                )
            )
    finally:
        await engine.dispose()


async def _function_exists(database_url: URL) -> bool:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text("select to_regprocedure(:signature) is not null"),
                    {"signature": ELIGIBILITY_FUNCTION},
                )
            )
    finally:
        await engine.dispose()


async def _source_row_counts(database_url: URL) -> tuple[int, int]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "select (select count(*) from employees), "
                        "(select count(*) from tenant_memberships)"
                    )
                )
            ).one()
            return int(row[0]), int(row[1])
    finally:
        await engine.dispose()


async def _row_security_flags(database_url: URL) -> tuple[bool, bool]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await _row_security_flags_from_connection(connection)
    finally:
        await engine.dispose()


async def _row_security_flags_from_connection(
    connection: AsyncConnection,
) -> tuple[bool, bool]:
    row = (
        await connection.execute(
            text(
                "select relrowsecurity, relforcerowsecurity from pg_catalog.pg_class "
                "where oid = 'public.employee_account_links'::regclass"
            )
        )
    ).one()
    return bool(row[0]), bool(row[1])


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
