from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.platform.db import sqlstate_from_error
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
PRE_P4E_REVISION = "0034_p4c_employee_account_links"
P4E_REVISION = "0035_p4e_employee_change_requests"

REQUESTS_TABLE = "employee_profile_change_requests"
COMMAND_SCHEMA = "p4e_command"
COMMAND_BINDINGS_TABLE = "database_command_bindings"
EXECUTOR_ROLE = "wealthy_falcon_identity_recovery"
IDENTITY_PROJECTION_ROLE = "wealthy_falcon_identity_projection"

TENANT_A_ID = UUID("e4000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("e4000000-0000-4000-8000-000000000002")

EMPLOYEE_A_ID = UUID("e4100000-0000-4000-8000-000000000001")
EMPLOYEE_B_ID = UUID("e4100000-0000-4000-8000-000000000002")
PROFILE_A_ID = UUID("e4110000-0000-4000-8000-000000000001")
PROFILE_B_ID = UUID("e4110000-0000-4000-8000-000000000002")
EMPLOYMENT_A_ID = UUID("e4120000-0000-4000-8000-000000000001")
EMPLOYMENT_B_ID = UUID("e4120000-0000-4000-8000-000000000002")
LINK_A_ID = UUID("e4130000-0000-4000-8000-000000000001")
LINK_B_ID = UUID("e4130000-0000-4000-8000-000000000002")

EMPLOYEE_A_USER_ID = UUID("e4200000-0000-4000-8000-000000000001")
HR_A_USER_ID = UUID("e4200000-0000-4000-8000-000000000002")
MANAGER_A_USER_ID = UUID("e4200000-0000-4000-8000-000000000003")
EMPLOYEE_B_USER_ID = UUID("e4200000-0000-4000-8000-000000000004")

EMPLOYEE_A_MEMBERSHIP_ID = UUID("e4300000-0000-4000-8000-000000000001")
HR_A_MEMBERSHIP_ID = UUID("e4300000-0000-4000-8000-000000000002")
MANAGER_A_MEMBERSHIP_ID = UUID("e4300000-0000-4000-8000-000000000003")
EMPLOYEE_B_MEMBERSHIP_ID = UUID("e4300000-0000-4000-8000-000000000004")

EMPLOYEE_A_IDENTITY_ID = UUID("e4400000-0000-4000-8000-000000000001")
HR_A_IDENTITY_ID = UUID("e4400000-0000-4000-8000-000000000002")
MANAGER_A_IDENTITY_ID = UUID("e4400000-0000-4000-8000-000000000003")
EMPLOYEE_B_IDENTITY_ID = UUID("e4400000-0000-4000-8000-000000000004")

HR_DIRECTOR_ROLE_ID = UUID("d2000000-0000-4000-8000-000000000003")
MANAGER_ROLE_ID = UUID("d2000000-0000-4000-8000-000000000007")
EMPLOYEE_ROLE_ID = UUID("d2000000-0000-4000-8000-000000000008")

EXPECTED_COLUMNS = {
    "id",
    "tenant_id",
    "employee_id",
    "requester_membership_id",
    "requester_user_id",
    "status",
    "version",
    "base_profile_version",
    "preferred_name_changed",
    "previous_preferred_name",
    "proposed_preferred_name",
    "phone_changed",
    "previous_phone",
    "proposed_phone",
    "birth_date_changed",
    "previous_birth_date",
    "proposed_birth_date",
    "submitted_at",
    "decided_at",
    "cancelled_at",
    "decided_by_membership_id",
    "decided_by_user_id",
    "rejection_reason",
    "created_at",
    "updated_at",
}

EXPECTED_CONSTRAINTS = {
    "pk_employee_profile_change_requests": "PRIMARY KEY",
    "ck_employee_profile_change_requests_status": "CHECK",
    "ck_employee_profile_change_requests_version_positive": "CHECK",
    "ck_employee_profile_change_requests_base_version_positive": "CHECK",
    "ck_employee_profile_change_requests_has_change": "CHECK",
    "ck_employee_profile_change_requests_preferred_snapshot": "CHECK",
    "ck_employee_profile_change_requests_phone_snapshot": "CHECK",
    "ck_employee_profile_change_requests_birth_snapshot": "CHECK",
    "ck_employee_profile_change_requests_timestamp_order": "CHECK",
    "ck_employee_profile_change_requests_state": "CHECK",
    "fk_employee_profile_change_requests_tenant_id_tenants": "FOREIGN KEY",
    "fk_epcr_tenant_employee_employees": "FOREIGN KEY",
    "fk_epcr_requester_membership_memberships": "FOREIGN KEY",
    "fk_epcr_requester_user_users": "FOREIGN KEY",
    "fk_epcr_decider_membership_memberships": "FOREIGN KEY",
    "fk_epcr_decider_user_users": "FOREIGN KEY",
    "uq_employee_profile_change_requests_tenant_id_id": "UNIQUE",
}
EXPECTED_CHECK_DEFINITIONS = {
    "ck_employee_profile_change_requests_base_version_positive": (
        "CHECK ((base_profile_version > 0))"
    ),
    "ck_employee_profile_change_requests_birth_snapshot": (
        "CHECK (((birth_date_changed AND (previous_birth_date IS DISTINCT FROM "
        "proposed_birth_date)) OR ((NOT birth_date_changed) AND "
        "(previous_birth_date IS NULL) AND (proposed_birth_date IS NULL))))"
    ),
    "ck_employee_profile_change_requests_has_change": (
        "CHECK ((preferred_name_changed OR phone_changed OR birth_date_changed))"
    ),
    "ck_employee_profile_change_requests_phone_snapshot": (
        "CHECK (((phone_changed AND ((previous_phone)::text IS DISTINCT FROM "
        "(proposed_phone)::text)) OR ((NOT phone_changed) AND (previous_phone IS NULL) "
        "AND (proposed_phone IS NULL))))"
    ),
    "ck_employee_profile_change_requests_preferred_snapshot": (
        "CHECK (((preferred_name_changed AND ((previous_preferred_name)::text IS DISTINCT "
        "FROM (proposed_preferred_name)::text)) OR ((NOT preferred_name_changed) AND "
        "(previous_preferred_name IS NULL) AND (proposed_preferred_name IS NULL))))"
    ),
    "ck_employee_profile_change_requests_state": (
        "CHECK (((((status)::text = 'submitted'::text) AND (decided_at IS NULL) AND "
        "(cancelled_at IS NULL) AND (decided_by_membership_id IS NULL) AND "
        "(decided_by_user_id IS NULL) AND (rejection_reason IS NULL)) OR "
        "(((status)::text = 'approved'::text) AND (decided_at IS NOT NULL) AND "
        "(cancelled_at IS NULL) AND (decided_by_membership_id IS NOT NULL) AND "
        "(decided_by_user_id IS NOT NULL) AND (rejection_reason IS NULL)) OR "
        "(((status)::text = 'rejected'::text) AND (decided_at IS NOT NULL) AND "
        "(cancelled_at IS NULL) AND (decided_by_membership_id IS NOT NULL) AND "
        "(decided_by_user_id IS NOT NULL) AND (rejection_reason IS NOT NULL) AND "
        "(length(TRIM(BOTH FROM rejection_reason)) > 0)) OR (((status)::text = "
        "'cancelled'::text) AND (decided_at IS NULL) AND (cancelled_at IS NOT NULL) AND "
        "(decided_by_membership_id IS NULL) AND (decided_by_user_id IS NULL) AND "
        "(rejection_reason IS NULL))))"
    ),
    "ck_employee_profile_change_requests_status": (
        "CHECK (((status)::text = ANY ((ARRAY['submitted'::character varying, "
        "'approved'::character varying, 'rejected'::character varying, "
        "'cancelled'::character varying])::text[])))"
    ),
    "ck_employee_profile_change_requests_timestamp_order": (
        "CHECK ((((decided_at IS NULL) OR (decided_at >= submitted_at)) AND "
        "((cancelled_at IS NULL) OR (cancelled_at >= submitted_at))))"
    ),
    "ck_employee_profile_change_requests_version_positive": "CHECK ((version > 0))",
}

SUBMIT_SQL = text(
    "select public.submit_own_employee_profile_change_request("
    "cast(:request_id as uuid), cast(:preferred_changed as boolean), "
    "cast(:preferred_value as varchar), cast(:phone_changed as boolean), "
    "cast(:phone_value as varchar), cast(:birth_changed as boolean), "
    "cast(:birth_value as date))"
)
TRANSITION_SQL = text(
    "select public.transition_employee_profile_change_request("
    "cast(:request_id as uuid), cast(:expected_version as integer), "
    "cast(:action as varchar), cast(:reason as varchar))"
)
PERSONAL_UPDATE_SQL = text(
    "select public.update_employee_personal_profile_values("
    "cast(:employee_id as uuid), cast(:expected_version as integer), "
    "cast(:preferred_changed as boolean), cast(:preferred_value as varchar), "
    "cast(:phone_changed as boolean), cast(:phone_value as varchar), "
    "cast(:birth_changed as boolean), cast(:birth_value as date))"
)
BIND_COMMAND_SQL = text(
    "select p4e_command.bind_database_command("
    "cast(:tenant_id as uuid), cast(:actor_id as uuid), cast(:membership_id as uuid), "
    "cast(:intent as varchar), cast(:target_id as uuid), cast(:audit_event_id as uuid), "
    "cast(:request_id as varchar), cast(:trace_id as varchar), cast(:session_id as uuid))"
)


def test_p4e_postgresql_empty_upgrade_catalog_acl_and_safe_round_trip(
    postgres_database_url: URL,
) -> None:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, P4E_REVISION)

    asyncio.run(_assert_catalog_rls_acl(postgres_database_url))
    assert asyncio.run(_request_count(postgres_database_url)) == 0

    alembic_command.downgrade(config, PRE_P4E_REVISION)
    assert asyncio.run(_current_revision(postgres_database_url)) == PRE_P4E_REVISION
    assert not asyncio.run(_table_exists(postgres_database_url, REQUESTS_TABLE))
    assert not asyncio.run(_p4e_functions_exist(postgres_database_url))
    assert not asyncio.run(_schema_exists(postgres_database_url, COMMAND_SCHEMA))
    assert asyncio.run(_p4c_eligibility_contract(postgres_database_url))
    assert asyncio.run(_profile_update_columns(postgres_database_url)) == {
        "birth_date",
        "phone",
        "preferred_name",
        "updated_at",
        "version",
    }
    assert asyncio.run(_table_exists(postgres_database_url, "employee_profiles"))
    assert asyncio.run(_table_exists(postgres_database_url, "employee_account_links"))

    alembic_command.upgrade(config, P4E_REVISION)
    assert asyncio.run(_current_revision(postgres_database_url)) == P4E_REVISION


def test_p4e_postgresql_commands_reject_forgery_and_stale_apply(
    postgres_database_url: URL,
) -> None:
    _prepare_populated_database(postgres_database_url)
    asyncio.run(_assert_context_commands_and_direct_attacks(postgres_database_url))


def test_p4e_postgresql_submit_and_transition_races_have_one_winner(
    postgres_database_url: URL,
) -> None:
    _prepare_populated_database(postgres_database_url)
    asyncio.run(_assert_races(postgres_database_url))


def test_p4e_postgresql_downgrade_refuses_history_without_collateral_damage(
    postgres_database_url: URL,
) -> None:
    config = _prepare_populated_database(postgres_database_url)
    source_counts = asyncio.run(_source_counts(postgres_database_url))

    alembic_command.downgrade(config, PRE_P4E_REVISION)
    assert asyncio.run(_current_revision(postgres_database_url)) == PRE_P4E_REVISION
    assert asyncio.run(_source_counts(postgres_database_url)) == source_counts
    assert not asyncio.run(_table_exists(postgres_database_url, REQUESTS_TABLE))
    assert not asyncio.run(_schema_exists(postgres_database_url, COMMAND_SCHEMA))
    assert asyncio.run(_p4c_eligibility_contract(postgres_database_url))
    assert asyncio.run(_profile_update_columns(postgres_database_url)) == {
        "birth_date",
        "phone",
        "preferred_name",
        "updated_at",
        "version",
    }

    alembic_command.upgrade(config, P4E_REVISION)
    request_id = uuid4()
    outcome = asyncio.run(
        _call_submit(
            postgres_database_url,
            request_id=request_id,
            preferred_value="Ada P4E",
        )
    )
    assert outcome == "submitted"

    with pytest.raises(
        RuntimeError,
        match="P4E employee change request downgrade refused: requests=1",
    ):
        alembic_command.downgrade(config, PRE_P4E_REVISION)

    assert asyncio.run(_current_revision(postgres_database_url)) == P4E_REVISION
    assert asyncio.run(_request_count(postgres_database_url)) == 1
    assert asyncio.run(_request_row_security_flags(postgres_database_url)) == (
        True,
        True,
    )
    assert asyncio.run(_p4e_functions_exist(postgres_database_url))
    assert asyncio.run(_profile_update_columns(postgres_database_url)) == set()
    assert asyncio.run(_source_counts(postgres_database_url)) == source_counts


@pytest.fixture
def p4e_gateway_database(
    postgres_database_url: URL,
) -> Iterator[tuple[URL, URL, str]]:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_P4E_REVISION)
    asyncio.run(_seed_pre_p4e_fixture(postgres_database_url))
    gateway_role = f"p4e_gateway_{uuid4().hex}"
    asyncio.run(_create_gateway_role(postgres_database_url, gateway_role))
    try:
        alembic_command.upgrade(config, P4E_REVISION)
        yield (
            postgres_database_url,
            postgres_database_url.set(username=gateway_role, password=None),
            gateway_role,
        )
    finally:
        asyncio.run(_drop_gateway_role(postgres_database_url, gateway_role))


def test_p4e_postgresql_non_super_gateway_binding_and_allowed_flow(
    p4e_gateway_database: tuple[URL, URL, str],
) -> None:
    database_url, gateway_url, gateway_role = p4e_gateway_database
    asyncio.run(_assert_gateway_binding_grants(database_url, gateway_role))
    request_id = uuid4()
    assert (
        asyncio.run(
            _call_submit(
                gateway_url,
                request_id=request_id,
                preferred_value="Gateway Accepted",
            )
        )
        == "submitted"
    )
    assert asyncio.run(_audit_event_types(database_url, request_id)) == [
        "employee.profile_change_request.submitted"
    ]


def _prepare_populated_database(database_url: URL) -> Config:
    config = _alembic_config(database_url)
    alembic_command.upgrade(config, PRE_P4E_REVISION)
    asyncio.run(_seed_pre_p4e_fixture(database_url))
    asyncio.run(_grant_hostile_default_privileges(database_url))
    alembic_command.upgrade(config, P4E_REVISION)
    assert asyncio.run(_request_count(database_url)) == 0
    return config


async def _assert_catalog_rls_acl(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            columns = {
                row.column_name: row
                for row in (
                    await connection.execute(
                        text(
                            "select column_name, data_type, is_nullable, column_default, "
                            "character_maximum_length from information_schema.columns "
                            "where table_schema = 'public' and table_name = :table_name"
                        ),
                        {"table_name": REQUESTS_TABLE},
                    )
                )
            }
            assert set(columns) == EXPECTED_COLUMNS
            for column_name in (
                "id",
                "tenant_id",
                "employee_id",
                "requester_membership_id",
                "requester_user_id",
                "decided_by_membership_id",
                "decided_by_user_id",
            ):
                assert columns[column_name].data_type == "uuid"
            for column_name in (
                "id",
                "tenant_id",
                "employee_id",
                "requester_membership_id",
                "requester_user_id",
                "status",
                "version",
                "base_profile_version",
                "preferred_name_changed",
                "phone_changed",
                "birth_date_changed",
                "submitted_at",
                "created_at",
                "updated_at",
            ):
                assert columns[column_name].is_nullable == "NO"
            assert columns["status"].character_maximum_length == 32
            assert columns["rejection_reason"].character_maximum_length == 500
            assert columns["previous_preferred_name"].character_maximum_length == 200
            assert columns["proposed_phone"].character_maximum_length == 32
            assert columns["status"].column_default == "'submitted'::character varying"
            assert columns["version"].column_default == "1"

            constraints = {
                row.constraint_name: row.constraint_type
                for row in (
                    await connection.execute(
                        text(
                            "select constraint_row.conname as constraint_name, "
                            "case constraint_row.contype "
                            "when 'p' then 'PRIMARY KEY' when 'c' then 'CHECK' "
                            "when 'f' then 'FOREIGN KEY' when 'u' then 'UNIQUE' end "
                            "as constraint_type "
                            "from pg_catalog.pg_constraint as constraint_row "
                            "where constraint_row.conrelid = "
                            "'public.employee_profile_change_requests'::regclass "
                            "and constraint_row.contype in ('p','c','f','u')"
                        )
                    )
                )
            }
            assert constraints == EXPECTED_CONSTRAINTS
            check_definitions = {
                row.constraint_name: row.definition
                for row in (
                    await connection.execute(
                        text(
                            "select constraint_row.conname as constraint_name, "
                            "pg_get_constraintdef(constraint_row.oid) as definition "
                            "from pg_catalog.pg_constraint as constraint_row "
                            "where constraint_row.conrelid = "
                            "'public.employee_profile_change_requests'::regclass "
                            "and constraint_row.contype = 'c'"
                        )
                    )
                )
            }
            assert check_definitions == EXPECTED_CHECK_DEFINITIONS

            foreign_keys = {
                row.constraint_name: row.definition
                for row in (
                    await connection.execute(
                        text(
                            "select constraint_row.conname as constraint_name, "
                            "pg_get_constraintdef(constraint_row.oid) as definition "
                            "from pg_catalog.pg_constraint as constraint_row "
                            "where constraint_row.conrelid = "
                            "'public.employee_profile_change_requests'::regclass "
                            "and constraint_row.contype = 'f'"
                        )
                    )
                )
            }
            assert foreign_keys == {
                "fk_employee_profile_change_requests_tenant_id_tenants": (
                    "FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE"
                ),
                "fk_epcr_tenant_employee_employees": (
                    "FOREIGN KEY (tenant_id, employee_id) "
                    "REFERENCES employees(tenant_id, id) ON DELETE RESTRICT"
                ),
                "fk_epcr_requester_membership_memberships": (
                    "FOREIGN KEY (tenant_id, requester_membership_id) "
                    "REFERENCES tenant_memberships(tenant_id, id) ON DELETE RESTRICT"
                ),
                "fk_epcr_requester_user_users": (
                    "FOREIGN KEY (tenant_id, requester_user_id) "
                    "REFERENCES users(tenant_id, id) ON DELETE RESTRICT"
                ),
                "fk_epcr_decider_membership_memberships": (
                    "FOREIGN KEY (tenant_id, decided_by_membership_id) "
                    "REFERENCES tenant_memberships(tenant_id, id) ON DELETE RESTRICT"
                ),
                "fk_epcr_decider_user_users": (
                    "FOREIGN KEY (tenant_id, decided_by_user_id) "
                    "REFERENCES users(tenant_id, id) ON DELETE RESTRICT"
                ),
            }

            indexes = {
                row.indexname: row.indexdef
                for row in (
                    await connection.execute(
                        text(
                            "select indexname, indexdef from pg_catalog.pg_indexes "
                            "where schemaname = 'public' and tablename = :table_name"
                        ),
                        {"table_name": REQUESTS_TABLE},
                    )
                )
            }
            assert set(indexes) == {
                "pk_employee_profile_change_requests",
                "uq_employee_profile_change_requests_tenant_id_id",
                "uq_employee_profile_change_requests_active_employee",
                "ix_employee_profile_change_requests_tenant_queue_cursor",
                "ix_employee_profile_change_requests_own_cursor",
            }
            assert indexes == {
                "pk_employee_profile_change_requests": (
                    "CREATE UNIQUE INDEX pk_employee_profile_change_requests ON "
                    "public.employee_profile_change_requests USING btree (id)"
                ),
                "uq_employee_profile_change_requests_tenant_id_id": (
                    "CREATE UNIQUE INDEX uq_employee_profile_change_requests_tenant_id_id "
                    "ON public.employee_profile_change_requests USING btree (tenant_id, id)"
                ),
                "uq_employee_profile_change_requests_active_employee": (
                    "CREATE UNIQUE INDEX uq_employee_profile_change_requests_active_employee "
                    "ON public.employee_profile_change_requests USING btree (tenant_id, "
                    "employee_id) WHERE ((status)::text = 'submitted'::text)"
                ),
                "ix_employee_profile_change_requests_tenant_queue_cursor": (
                    "CREATE INDEX ix_employee_profile_change_requests_tenant_queue_cursor "
                    "ON public.employee_profile_change_requests USING btree (tenant_id, "
                    "status, submitted_at, id)"
                ),
                "ix_employee_profile_change_requests_own_cursor": (
                    "CREATE INDEX ix_employee_profile_change_requests_own_cursor ON "
                    "public.employee_profile_change_requests USING btree (tenant_id, "
                    "employee_id, requester_membership_id, submitted_at, id)"
                ),
            }

            assert await _request_row_security_flags_from_connection(connection) == (
                True,
                True,
            )
            policies = {
                row.policyname: row
                for row in (
                    await connection.execute(
                        text(
                            "select policyname, roles, cmd, qual, with_check "
                            "from pg_catalog.pg_policies where schemaname = 'public' "
                            "and tablename = :table_name"
                        ),
                        {"table_name": REQUESTS_TABLE},
                    )
                ).mappings()
            }
            assert set(policies) == {
                "tenant_isolation_app",
                "p4e_executor_request_access",
            }
            assert tuple(policies["tenant_isolation_app"]["roles"]) == (TENANT_APPLICATION_ROLE,)
            assert tuple(policies["p4e_executor_request_access"]["roles"]) == (EXECUTOR_ROLE,)
            for policy in policies.values():
                assert policy["cmd"] == "ALL"
                assert "app.tenant_id" in policy["qual"]
                assert policy["with_check"] == policy["qual"]

            assert (
                await _direct_table_privileges(
                    connection,
                    table_name=REQUESTS_TABLE,
                    role_name=TENANT_APPLICATION_ROLE,
                )
                == set()
            )
            assert (
                await _column_privileges(
                    connection,
                    table_name=REQUESTS_TABLE,
                    role_name=TENANT_APPLICATION_ROLE,
                    privilege="SELECT",
                )
                == EXPECTED_COLUMNS
            )
            for privilege in ("INSERT", "UPDATE", "REFERENCES"):
                assert (
                    await _column_privileges(
                        connection,
                        table_name=REQUESTS_TABLE,
                        role_name=TENANT_APPLICATION_ROLE,
                        privilege=privilege,
                    )
                    == set()
                )
            for role_name in (
                "PUBLIC",
                PLATFORM_APPLICATION_ROLE,
                AUTHENTICATION_APPLICATION_ROLE,
                IDENTITY_PROJECTION_ROLE,
            ):
                assert (
                    await _direct_table_privileges(
                        connection,
                        table_name=REQUESTS_TABLE,
                        role_name=role_name,
                    )
                    == set()
                )
                assert (
                    await _all_column_privileges(
                        connection,
                        table_name=REQUESTS_TABLE,
                        role_name=role_name,
                    )
                    == set()
                )
            assert (
                await _direct_table_privileges(
                    connection,
                    table_name=REQUESTS_TABLE,
                    role_name=EXECUTOR_ROLE,
                )
                == set()
            )
            assert (
                await _column_privileges(
                    connection,
                    table_name=REQUESTS_TABLE,
                    role_name=EXECUTOR_ROLE,
                    privilege="SELECT",
                )
                == EXPECTED_COLUMNS
            )
            assert await _column_privileges(
                connection,
                table_name=REQUESTS_TABLE,
                role_name=EXECUTOR_ROLE,
                privilege="INSERT",
            ) == EXPECTED_COLUMNS - {
                "decided_at",
                "cancelled_at",
                "decided_by_membership_id",
                "decided_by_user_id",
                "rejection_reason",
            }
            assert await _column_privileges(
                connection,
                table_name=REQUESTS_TABLE,
                role_name=EXECUTOR_ROLE,
                privilege="UPDATE",
            ) == {
                "status",
                "version",
                "decided_at",
                "cancelled_at",
                "decided_by_membership_id",
                "decided_by_user_id",
                "rejection_reason",
                "updated_at",
            }
            assert (
                await _column_privileges(
                    connection,
                    table_name=REQUESTS_TABLE,
                    role_name=EXECUTOR_ROLE,
                    privilege="REFERENCES",
                )
                == set()
            )
            assert await _profile_update_columns_from_connection(connection) == set()

            await _assert_function_acl(connection)
            await _assert_command_binding_catalog(connection)
            await _assert_p4e_audit_acl(connection)
    finally:
        await engine.dispose()


async def _assert_function_acl(connection: AsyncConnection) -> None:
    assert not bool(
        await connection.scalar(
            text("select has_schema_privilege(:role_name, 'public', 'CREATE')"),
            {"role_name": EXECUTOR_ROLE},
        )
    )
    expected_functions = {
        "submit_own_employee_profile_change_request": (
            "uuid, boolean, character varying, boolean, character varying, boolean, date"
        ),
        "transition_employee_profile_change_request": (
            "uuid, integer, character varying, character varying"
        ),
        "update_employee_personal_profile_values": (
            "uuid, integer, boolean, character varying, boolean, character varying, boolean, date"
        ),
    }
    rows = (
        await connection.execute(
            text(
                "select procedure.proname, "
                "oidvectortypes(procedure.proargtypes) as identity_arguments, "
                "owner.rolname as owner_name, procedure.prosecdef, procedure.proconfig, "
                "exists ("
                "select 1 from aclexplode(coalesce(procedure.proacl, "
                "acldefault('f', procedure.proowner))) as acl "
                "where acl.grantee = 0 and acl.privilege_type = 'EXECUTE'"
                ") as public_execute "
                "from pg_catalog.pg_proc as procedure "
                "join pg_catalog.pg_namespace as namespace "
                "on namespace.oid = procedure.pronamespace "
                "join pg_catalog.pg_roles as owner on owner.oid = procedure.proowner "
                "where namespace.nspname = 'public' and procedure.proname = any(:names)"
            ),
            {"names": list(expected_functions)},
        )
    ).mappings()
    by_name = {row["proname"]: row for row in rows}
    assert set(by_name) == set(expected_functions)
    for function_name, identity_arguments in expected_functions.items():
        row = by_name[function_name]
        assert row["identity_arguments"] == identity_arguments
        assert row["owner_name"] == EXECUTOR_ROLE
        assert row["prosecdef"] is True
        assert row["proconfig"] == ["search_path=pg_catalog, p4e_command, public"]
        assert row["public_execute"] is False
        signature = f"public.{function_name}({identity_arguments})"
        assert bool(
            await connection.scalar(
                text("select has_function_privilege(:role_name, :signature, 'EXECUTE')"),
                {"role_name": TENANT_APPLICATION_ROLE, "signature": signature},
            )
        )
        for role_name in (
            PLATFORM_APPLICATION_ROLE,
            AUTHENTICATION_APPLICATION_ROLE,
            IDENTITY_PROJECTION_ROLE,
        ):
            assert not bool(
                await connection.scalar(
                    text("select has_function_privilege(:role_name, :signature, 'EXECUTE')"),
                    {"role_name": role_name, "signature": signature},
                )
            )


async def _assert_command_binding_catalog(connection: AsyncConnection) -> None:
    expected_column_types = {
        "backend_pid": ("integer", "int4", "NO", None),
        "transaction_id": ("xid8", "xid8", "NO", None),
        "gateway_session_user": ("text", "text", "NO", None),
        "tenant_id": ("uuid", "uuid", "NO", None),
        "actor_user_id": ("uuid", "uuid", "NO", None),
        "membership_id": ("uuid", "uuid", "NO", None),
        "intent": ("character varying", "varchar", "NO", 32),
        "target_id": ("uuid", "uuid", "NO", None),
        "audit_event_id": ("uuid", "uuid", "NO", None),
        "correlation_request_id": ("character varying", "varchar", "NO", 128),
        "trace_id": ("character varying", "varchar", "NO", 32),
        "session_id": ("uuid", "uuid", "YES", None),
        "state": ("character varying", "varchar", "NO", 16),
        "bound_at": ("timestamp with time zone", "timestamptz", "NO", None),
        "executed_at": ("timestamp with time zone", "timestamptz", "YES", None),
        "audit_written_at": ("timestamp with time zone", "timestamptz", "YES", None),
    }
    columns = {
        row.column_name: (
            row.data_type,
            row.udt_name,
            row.is_nullable,
            row.character_maximum_length,
        )
        for row in (
            await connection.execute(
                text(
                    "select column_name, data_type, udt_name, is_nullable, "
                    "character_maximum_length from information_schema.columns "
                    "where table_schema = :schema_name and table_name = :table_name"
                ),
                {"schema_name": COMMAND_SCHEMA, "table_name": COMMAND_BINDINGS_TABLE},
            )
        )
    }
    assert columns == expected_column_types

    constraints = {
        row.conname: row.definition
        for row in (
            await connection.execute(
                text(
                    "select constraint_row.conname, "
                    "pg_get_constraintdef(constraint_row.oid) as definition "
                    "from pg_catalog.pg_constraint as constraint_row "
                    "where constraint_row.conrelid = "
                    "'p4e_command.database_command_bindings'::regclass"
                )
            )
        )
    }
    assert set(constraints) == {
        "pk_p4e_database_command_bindings",
        "ck_p4e_database_command_bindings_backend",
        "ck_p4e_database_command_bindings_context",
        "ck_p4e_database_command_bindings_intent",
        "ck_p4e_database_command_bindings_request_id",
        "ck_p4e_database_command_bindings_trace_id",
        "ck_p4e_database_command_bindings_state",
    }
    assert constraints["pk_p4e_database_command_bindings"] == (
        "PRIMARY KEY (backend_pid, transaction_id)"
    )
    assert all(
        intent in constraints["ck_p4e_database_command_bindings_intent"]
        for intent in (
            "p4e_submit",
            "p4e_cancel",
            "p4e_approve",
            "p4e_reject",
            "p4b_personal_update",
        )
    )
    assert "{0,126}" in constraints["ck_p4e_database_command_bindings_request_id"]
    assert (
        "audit_written_at >= executed_at" in constraints["ck_p4e_database_command_bindings_state"]
    )

    indexes = {
        row.indexname: row.indexdef
        for row in (
            await connection.execute(
                text(
                    "select indexname, indexdef from pg_catalog.pg_indexes "
                    "where schemaname = :schema_name and tablename = :table_name"
                ),
                {"schema_name": COMMAND_SCHEMA, "table_name": COMMAND_BINDINGS_TABLE},
            )
        )
    }
    assert indexes == {
        "pk_p4e_database_command_bindings": (
            "CREATE UNIQUE INDEX pk_p4e_database_command_bindings ON "
            "p4e_command.database_command_bindings USING btree (backend_pid, transaction_id)"
        ),
        "ix_p4e_database_command_bindings_bound_at": (
            "CREATE INDEX ix_p4e_database_command_bindings_bound_at ON "
            "p4e_command.database_command_bindings USING btree (bound_at)"
        ),
    }
    security = (
        await connection.execute(
            text(
                "select relrowsecurity, relforcerowsecurity from pg_catalog.pg_class "
                "where oid = 'p4e_command.database_command_bindings'::regclass"
            )
        )
    ).one()
    assert tuple(bool(value) for value in security) == (True, True)

    policies = {
        row.policyname: row
        for row in (
            await connection.execute(
                text(
                    "select policyname, permissive, roles, cmd, qual, with_check "
                    "from pg_catalog.pg_policies where schemaname = :schema_name "
                    "and tablename = :table_name"
                ),
                {"schema_name": COMMAND_SCHEMA, "table_name": COMMAND_BINDINGS_TABLE},
            )
        ).mappings()
    }
    assert set(policies) == {
        "p4e_command_executor_select",
        "p4e_command_executor_insert",
        "p4e_command_executor_update",
        "p4e_command_executor_delete_committed",
    }
    assert {row["cmd"] for row in policies.values()} == {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
    }
    for row in policies.values():
        assert row["permissive"] == "PERMISSIVE"
        assert tuple(row["roles"]) == (EXECUTOR_ROLE,)
    assert policies["p4e_command_executor_delete_committed"]["qual"] == (
        "(transaction_id <> pg_current_xact_id())"
    )
    for policy_name in (
        "p4e_command_executor_select",
        "p4e_command_executor_insert",
        "p4e_command_executor_update",
    ):
        policy_text = " ".join(
            str(value or "")
            for value in (
                policies[policy_name]["qual"],
                policies[policy_name]["with_check"],
            )
        )
        assert "pg_backend_pid()" in policy_text
        assert "pg_current_xact_id()" in policy_text
        assert "gateway_session_user = SESSION_USER" in policy_text

    assert await _direct_table_privileges(
        connection,
        schema_name=COMMAND_SCHEMA,
        table_name=COMMAND_BINDINGS_TABLE,
        role_name=EXECUTOR_ROLE,
    ) == {"DELETE"}
    expected_columns = set(expected_column_types)
    assert (
        await _column_privileges(
            connection,
            schema_name=COMMAND_SCHEMA,
            table_name=COMMAND_BINDINGS_TABLE,
            role_name=EXECUTOR_ROLE,
            privilege="SELECT",
        )
        == expected_columns
    )
    assert (
        await _column_privileges(
            connection,
            schema_name=COMMAND_SCHEMA,
            table_name=COMMAND_BINDINGS_TABLE,
            role_name=EXECUTOR_ROLE,
            privilege="INSERT",
        )
        == expected_columns
    )
    assert await _column_privileges(
        connection,
        schema_name=COMMAND_SCHEMA,
        table_name=COMMAND_BINDINGS_TABLE,
        role_name=EXECUTOR_ROLE,
        privilege="UPDATE",
    ) == {"state", "executed_at", "audit_written_at"}
    for role_name in (
        "PUBLIC",
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
        IDENTITY_PROJECTION_ROLE,
    ):
        if role_name == "PUBLIC":
            assert not bool(
                await connection.scalar(
                    text(
                        "select exists (select 1 from pg_catalog.pg_namespace as namespace, "
                        "lateral aclexplode(coalesce(namespace.nspacl, "
                        "acldefault('n', namespace.nspowner))) as acl "
                        "where namespace.nspname = :schema_name and acl.grantee = 0 "
                        "and acl.privilege_type = 'USAGE')"
                    ),
                    {"schema_name": COMMAND_SCHEMA},
                )
            )
        else:
            assert not bool(
                await connection.scalar(
                    text("select has_schema_privilege(:role_name, :schema_name, 'USAGE')"),
                    {"role_name": role_name, "schema_name": COMMAND_SCHEMA},
                )
            )
        assert (
            await _direct_table_privileges(
                connection,
                schema_name=COMMAND_SCHEMA,
                table_name=COMMAND_BINDINGS_TABLE,
                role_name=role_name,
            )
            == set()
        )
        assert (
            await _all_column_privileges(
                connection,
                schema_name=COMMAND_SCHEMA,
                table_name=COMMAND_BINDINGS_TABLE,
                role_name=role_name,
            )
            == set()
        )
    assert bool(
        await connection.scalar(
            text("select has_schema_privilege(:role_name, :schema_name, 'USAGE')"),
            {"role_name": EXECUTOR_ROLE, "schema_name": COMMAND_SCHEMA},
        )
    )
    assert not bool(
        await connection.scalar(
            text("select has_schema_privilege(:role_name, :schema_name, 'CREATE')"),
            {"role_name": EXECUTOR_ROLE, "schema_name": COMMAND_SCHEMA},
        )
    )

    function_rows = (
        await connection.execute(
            text(
                "select procedure.proname, "
                "oidvectortypes(procedure.proargtypes) as identity_arguments, "
                "owner.rolname as owner_name, procedure.prosecdef, procedure.proconfig, "
                "coalesce(array_agg(coalesce(grantee.rolname, 'PUBLIC')) "
                "filter (where acl.privilege_type = 'EXECUTE'), array[]::name[]) "
                "as execute_grantees "
                "from pg_catalog.pg_proc as procedure "
                "join pg_catalog.pg_namespace as namespace "
                "on namespace.oid = procedure.pronamespace "
                "join pg_catalog.pg_roles as owner on owner.oid = procedure.proowner "
                "left join lateral aclexplode(coalesce(procedure.proacl, "
                "acldefault('f', procedure.proowner))) as acl on true "
                "left join pg_catalog.pg_roles as grantee on grantee.oid = acl.grantee "
                "where namespace.nspname = :schema_name "
                "group by procedure.oid, owner.rolname"
            ),
            {"schema_name": COMMAND_SCHEMA},
        )
    ).mappings()
    by_name = {row["proname"]: row for row in function_rows}
    assert {name: row["identity_arguments"] for name, row in by_name.items()} == {
        "bind_database_command": (
            "uuid, uuid, uuid, character varying, uuid, uuid, character varying, "
            "character varying, uuid"
        ),
        "claim_database_command": "character varying, uuid",
        "write_employee_profile_change_request_audit": "",
    }
    for function_name, row in by_name.items():
        assert row["owner_name"] == EXECUTOR_ROLE
        assert row["prosecdef"] is True
        assert row["proconfig"] == ["search_path=pg_catalog, p4e_command, public"]
        grantees = set(row["execute_grantees"])
        if function_name != "bind_database_command":
            assert grantees == {EXECUTOR_ROLE}
            continue
        assert EXECUTOR_ROLE in grantees
        for grantee in grantees - {EXECUTOR_ROLE}:
            assert bool(
                await connection.scalar(
                    text(
                        "select login.rolcanlogin and not login.rolsuper "
                        "and not login.rolbypassrls and exists ("
                        "select 1 from pg_catalog.pg_auth_members as memberships "
                        "join pg_catalog.pg_roles as capability "
                        "on capability.oid = memberships.roleid "
                        "where memberships.member = login.oid "
                        "and capability.rolname = :capability_role) "
                        "from pg_catalog.pg_roles as login where login.rolname = :grantee"
                    ),
                    {"capability_role": TENANT_APPLICATION_ROLE, "grantee": grantee},
                )
            )


async def _assert_p4e_audit_acl(connection: AsyncConnection) -> None:
    policy = (
        (
            await connection.execute(
                text(
                    "select roles, cmd, qual, with_check from pg_catalog.pg_policies "
                    "where schemaname = 'public' and tablename = 'audit_events' "
                    "and policyname = 'p4e_executor_audit_insert'"
                )
            )
        )
        .mappings()
        .one()
    )
    assert tuple(policy["roles"]) == (EXECUTOR_ROLE,)
    assert policy["cmd"] == "INSERT"
    assert policy["qual"] is None
    assert "app.tenant_id" in policy["with_check"]
    assert "employee_profile_change_request" in policy["with_check"]
    for event_type in ("submitted", "approved", "rejected", "cancelled"):
        assert f"employee.profile_change_request.{event_type}" in policy["with_check"]
    assert (
        await _direct_table_privileges(
            connection,
            table_name="audit_events",
            role_name=EXECUTOR_ROLE,
        )
        == set()
    )
    assert await _column_privileges(
        connection,
        table_name="audit_events",
        role_name=EXECUTOR_ROLE,
        privilege="INSERT",
    ) == {
        "id",
        "occurred_at",
        "scope_type",
        "tenant_id",
        "actor_type",
        "actor_user_id",
        "impersonator_user_id",
        "event_type",
        "category",
        "severity",
        "resource_type",
        "resource_id",
        "action",
        "result",
        "request_id",
        "trace_id",
        "session_id",
        "ip_address",
        "user_agent",
        "reason",
        "support_ticket_id",
        "changed_fields",
        "before_data",
        "after_data",
        "metadata",
        "data_classification",
        "visibility_class",
        "integrity_hash",
    }
    for privilege in ("SELECT", "UPDATE", "REFERENCES"):
        assert (
            await _column_privileges(
                connection,
                table_name="audit_events",
                role_name=EXECUTOR_ROLE,
                privilege=privilege,
            )
            == set()
        )


async def _call_submit(
    database_url: URL,
    *,
    request_id: UUID,
    tenant_id: UUID = TENANT_A_ID,
    actor_id: UUID = EMPLOYEE_A_USER_ID,
    membership_id: UUID = EMPLOYEE_A_MEMBERSHIP_ID,
    preferred_changed: bool = True,
    preferred_value: str | None = "Ada Proposed",
    phone_changed: bool = False,
    phone_value: str | None = None,
    birth_changed: bool = False,
    birth_value: date | None = None,
    set_context: bool = True,
) -> str:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            if set_context:
                await _bind_database_command(
                    connection,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    membership_id=membership_id,
                    intent="p4e_submit",
                    target_id=request_id,
                )
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            result = await connection.scalar(
                SUBMIT_SQL,
                {
                    "request_id": request_id,
                    "preferred_changed": preferred_changed,
                    "preferred_value": preferred_value,
                    "phone_changed": phone_changed,
                    "phone_value": phone_value,
                    "birth_changed": birth_changed,
                    "birth_value": birth_value,
                },
            )
            return str(result)
    finally:
        await engine.dispose()


async def _call_transition(
    database_url: URL,
    *,
    request_id: UUID,
    action: str | None,
    expected_version: int = 1,
    reason: str | None = None,
    tenant_id: UUID = TENANT_A_ID,
    actor_id: UUID = HR_A_USER_ID,
    membership_id: UUID = HR_A_MEMBERSHIP_ID,
    set_context: bool = True,
) -> str:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            if set_context:
                await _bind_database_command(
                    connection,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    membership_id=membership_id,
                    intent={
                        "approve": "p4e_approve",
                        "reject": "p4e_reject",
                        "cancel": "p4e_cancel",
                    }.get(action, "p4e_approve"),
                    target_id=request_id,
                )
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            result = await connection.scalar(
                TRANSITION_SQL,
                {
                    "request_id": request_id,
                    "expected_version": expected_version,
                    "action": action,
                    "reason": reason,
                },
            )
            return str(result)
    finally:
        await engine.dispose()


async def _call_personal_update(
    database_url: URL,
    *,
    employee_id: UUID,
    expected_version: int,
    tenant_id: UUID = TENANT_A_ID,
    actor_id: UUID = HR_A_USER_ID,
    membership_id: UUID = HR_A_MEMBERSHIP_ID,
    preferred_changed: bool = True,
    preferred_value: str | None = "HR Updated",
    phone_changed: bool = False,
    phone_value: str | None = None,
    birth_changed: bool = False,
    birth_value: date | None = None,
) -> str:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await _bind_database_command(
                connection,
                tenant_id=tenant_id,
                actor_id=actor_id,
                membership_id=membership_id,
                intent="p4b_personal_update",
                target_id=employee_id,
            )
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            result = await connection.scalar(
                PERSONAL_UPDATE_SQL,
                {
                    "employee_id": employee_id,
                    "expected_version": expected_version,
                    "preferred_changed": preferred_changed,
                    "preferred_value": preferred_value,
                    "phone_changed": phone_changed,
                    "phone_value": phone_value,
                    "birth_changed": birth_changed,
                    "birth_value": birth_value,
                },
            )
            return str(result)
    finally:
        await engine.dispose()


async def _assert_context_commands_and_direct_attacks(database_url: URL) -> None:
    await _assert_binding_gate_attacks(database_url)
    assert (
        await _call_submit(
            database_url,
            request_id=uuid4(),
            set_context=False,
        )
        == "context_invalid"
    )
    assert (
        await _call_transition(
            database_url,
            request_id=uuid4(),
            action="approve",
            set_context=False,
        )
        == "context_invalid"
    )

    for masked_value in (
        "Ada*",
        "Ada•",
        "Ada●",
        "Ada·",
        "Ada▪",
        "Ada◦",
    ):
        assert (
            await _call_submit(
                database_url,
                request_id=uuid4(),
                preferred_value=masked_value,
            )
            == "invalid_request"
        )
    assert (
        await _call_submit(
            database_url,
            request_id=uuid4(),
            preferred_value=" Ada  Alias ",
        )
        == "invalid_request"
    )
    # Current storage deliberately contains legacy display formatting. The command compares
    # normalized values and rejects a submission that would not change the semantic value.
    assert (
        await _call_submit(
            database_url,
            request_id=uuid4(),
            preferred_value="Ada Alias",
        )
        == "invalid_request"
    )
    assert (
        await _call_submit(
            database_url,
            request_id=uuid4(),
            preferred_changed=False,
            preferred_value=None,
            phone_changed=True,
            phone_value="+905551234567",
        )
        == "invalid_request"
    )
    for invalid_phone in ("+90 ••• ••• ••", "+90 555 999 8877", "123"):
        assert (
            await _call_submit(
                database_url,
                request_id=uuid4(),
                preferred_changed=False,
                preferred_value=None,
                phone_changed=True,
                phone_value=invalid_phone,
            )
            == "invalid_request"
        )

    before_clear = await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID)
    clear_request_id = uuid4()
    assert (
        await _call_submit(
            database_url,
            request_id=clear_request_id,
            preferred_changed=False,
            preferred_value=None,
            phone_changed=True,
            phone_value=None,
        )
        == "submitted"
    )
    assert await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID) == before_clear
    clear_request = await _request_state(database_url, clear_request_id)
    assert clear_request == {
        "tenant_id": TENANT_A_ID,
        "employee_id": EMPLOYEE_A_ID,
        "requester_membership_id": EMPLOYEE_A_MEMBERSHIP_ID,
        "requester_user_id": EMPLOYEE_A_USER_ID,
        "status": "submitted",
        "version": 1,
        "base_profile_version": before_clear[3],
        "previous_preferred_name": None,
        "proposed_preferred_name": None,
        "previous_phone": before_clear[1],
        "proposed_phone": None,
    }
    assert (
        await _call_transition(
            database_url,
            request_id=clear_request_id,
            action=None,
        )
        == "context_invalid"
    )
    assert await _request_state(database_url, clear_request_id) == clear_request
    assert await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID) == before_clear

    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        await _assert_permission_denied(
            engine,
            text(
                "insert into employee_profile_change_requests ("
                "id, tenant_id, employee_id, requester_membership_id, requester_user_id, "
                "status, version, base_profile_version, preferred_name_changed, "
                "previous_preferred_name, proposed_preferred_name, phone_changed, "
                "birth_date_changed, submitted_at"
                ") values ("
                ":id, :tenant_id, :employee_id, :membership_id, :actor_id, "
                "'submitted', 1, 1, true, 'old', 'new', false, false, now())"
            ),
            {
                "id": uuid4(),
                "tenant_id": TENANT_A_ID,
                "employee_id": EMPLOYEE_A_ID,
                "membership_id": HR_A_MEMBERSHIP_ID,
                "actor_id": HR_A_USER_ID,
            },
        )
        await _assert_permission_denied(
            engine,
            text(
                "update employee_profile_change_requests "
                "set status = 'approved', decided_by_user_id = :actor_id "
                "where tenant_id = :tenant_id and id = :request_id"
            ),
            {
                "actor_id": HR_A_USER_ID,
                "tenant_id": TENANT_A_ID,
                "request_id": clear_request_id,
            },
        )
        await _assert_permission_denied(
            engine,
            text(
                "delete from employee_profile_change_requests "
                "where tenant_id = :tenant_id and id = :request_id"
            ),
            {"tenant_id": TENANT_A_ID, "request_id": clear_request_id},
        )
        await _assert_permission_denied(
            engine,
            text(
                "update employee_profiles set preferred_name = 'forged', version = version + 1 "
                "where tenant_id = :tenant_id and employee_id = :employee_id"
            ),
            {"tenant_id": TENANT_A_ID, "employee_id": EMPLOYEE_A_ID},
        )

        async with engine.begin() as connection:
            await _set_local_tenant_actor_role(
                connection,
                tenant_id=TENANT_B_ID,
                actor_id=EMPLOYEE_B_USER_ID,
                membership_id=EMPLOYEE_B_MEMBERSHIP_ID,
            )
            visible_count = await connection.scalar(
                text(
                    "select count(*) from employee_profile_change_requests where id = :request_id"
                ),
                {"request_id": clear_request_id},
            )
            assert int(visible_count or 0) == 0
    finally:
        await engine.dispose()

    assert (
        await _call_transition(
            database_url,
            request_id=clear_request_id,
            action="approve",
            actor_id=MANAGER_A_USER_ID,
            membership_id=MANAGER_A_MEMBERSHIP_ID,
        )
        == "access_denied"
    )
    assert (
        await _call_transition(
            database_url,
            request_id=clear_request_id,
            action="cancel",
        )
        == "not_found"
    )
    assert (
        await _call_transition(
            database_url,
            request_id=clear_request_id,
            action="approve",
            tenant_id=TENANT_B_ID,
            actor_id=EMPLOYEE_B_USER_ID,
            membership_id=EMPLOYEE_B_MEMBERSHIP_ID,
        )
        == "not_found"
    )
    assert (
        await _call_transition(
            database_url,
            request_id=clear_request_id,
            action="cancel",
            actor_id=EMPLOYEE_A_USER_ID,
            membership_id=EMPLOYEE_A_MEMBERSHIP_ID,
        )
        == "cancelled"
    )
    assert await _audit_event_types(database_url, clear_request_id) == [
        "employee.profile_change_request.submitted",
        "employee.profile_change_request.cancelled",
    ]
    assert await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID) == before_clear

    reject_request_id = uuid4()
    assert (
        await _call_submit(
            database_url,
            request_id=reject_request_id,
            preferred_value="Ada Rejected",
        )
        == "submitted"
    )
    assert (
        await _call_transition(
            database_url,
            request_id=reject_request_id,
            action="reject",
            reason=None,
        )
        == "invalid_request"
    )
    assert (
        await _call_transition(
            database_url,
            request_id=reject_request_id,
            action="approve",
            reason="must not be accepted",
        )
        == "invalid_request"
    )
    assert (
        await _call_transition(
            database_url,
            request_id=reject_request_id,
            action="reject",
            reason="Non  canonical",
        )
        == "invalid_request"
    )
    assert (
        await _call_transition(
            database_url,
            request_id=reject_request_id,
            action="reject",
            reason="Policy mismatch",
        )
        == "rejected"
    )
    assert await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID) == before_clear

    stale_request_id = uuid4()
    assert (
        await _call_submit(
            database_url,
            request_id=stale_request_id,
            preferred_value="Employee Proposed",
        )
        == "submitted"
    )
    assert (
        await _call_personal_update(
            database_url,
            employee_id=EMPLOYEE_A_ID,
            expected_version=before_clear[3],
            actor_id=MANAGER_A_USER_ID,
            membership_id=MANAGER_A_MEMBERSHIP_ID,
        )
        == "access_denied"
    )
    assert (
        await _call_personal_update(
            database_url,
            employee_id=EMPLOYEE_A_ID,
            expected_version=before_clear[3],
            tenant_id=TENANT_B_ID,
            actor_id=EMPLOYEE_B_USER_ID,
            membership_id=EMPLOYEE_B_MEMBERSHIP_ID,
        )
        == "not_found"
    )
    assert (
        await _call_personal_update(
            database_url,
            employee_id=EMPLOYEE_A_ID,
            expected_version=before_clear[3],
            preferred_value="HR Changed",
        )
        == "updated"
    )
    changed_profile = await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID)
    assert changed_profile[0] == "HR Changed"
    assert changed_profile[3] == before_clear[3] + 1
    assert (
        await _call_transition(
            database_url,
            request_id=stale_request_id,
            action="approve",
        )
        == "profile_conflict"
    )
    assert await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID) == changed_profile
    stale_request = await _request_state(database_url, stale_request_id)
    assert stale_request["status"] == "submitted"
    assert stale_request["version"] == 1
    assert await _audit_event_types(database_url, clear_request_id) == [
        "employee.profile_change_request.submitted",
        "employee.profile_change_request.cancelled",
    ]
    assert await _audit_event_types(database_url, reject_request_id) == [
        "employee.profile_change_request.submitted",
        "employee.profile_change_request.rejected",
    ]
    assert await _audit_event_types(database_url, stale_request_id) == [
        "employee.profile_change_request.submitted"
    ]
    await _assert_audit_value_redaction(database_url)
    await _assert_denied_actor_does_not_lock_request(
        database_url,
        active_request_id=stale_request_id,
    )
    await _assert_p4b_update_only_permission(database_url)


async def _assert_binding_gate_attacks(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    forged_request_id = uuid4()
    try:
        for statement in (
            text("select count(*) from p4e_command.database_command_bindings"),
            text(
                "insert into p4e_command.database_command_bindings ("
                "backend_pid, transaction_id, gateway_session_user, tenant_id, "
                "actor_user_id, membership_id, intent, target_id, audit_event_id, "
                "correlation_request_id, trace_id) values ("
                "pg_backend_pid(), pg_current_xact_id(), session_user, :tenant_id, "
                ":actor_id, :membership_id, 'p4e_submit', :target_id, :audit_event_id, "
                "'forged-command', '11111111111111111111111111111111')"
            ),
            text(
                "update p4e_command.database_command_bindings set state = 'executed', "
                "executed_at = clock_timestamp()"
            ),
            text("delete from p4e_command.database_command_bindings"),
        ):
            await _assert_permission_denied(
                engine,
                statement,
                {
                    "tenant_id": TENANT_A_ID,
                    "actor_id": HR_A_USER_ID,
                    "membership_id": HR_A_MEMBERSHIP_ID,
                    "target_id": forged_request_id,
                    "audit_event_id": uuid4(),
                },
            )

        with pytest.raises(DBAPIError) as binder_error:
            async with engine.begin() as connection:
                await _set_local_role(connection, TENANT_APPLICATION_ROLE)
                await _bind_database_command(
                    connection,
                    tenant_id=TENANT_A_ID,
                    actor_id=EMPLOYEE_A_USER_ID,
                    membership_id=EMPLOYEE_A_MEMBERSHIP_ID,
                    intent="p4e_submit",
                    target_id=forged_request_id,
                )
        assert sqlstate_from_error(binder_error.value) == "42501"

        request_count_before = await _request_count(database_url)
        async with engine.begin() as connection:
            await _set_local_tenant_actor_role(
                connection,
                tenant_id=TENANT_A_ID,
                actor_id=EMPLOYEE_A_USER_ID,
                membership_id=EMPLOYEE_A_MEMBERSHIP_ID,
            )
            assert (
                str(
                    await connection.scalar(
                        SUBMIT_SQL,
                        {
                            "request_id": forged_request_id,
                            "preferred_changed": True,
                            "preferred_value": "Forged GUC",
                            "phone_changed": False,
                            "phone_value": None,
                            "birth_changed": False,
                            "birth_value": None,
                        },
                    )
                )
                == "context_invalid"
            )
        assert await _request_count(database_url) == request_count_before

        with pytest.raises(DBAPIError) as cross_tenant_error:
            async with engine.begin() as connection:
                await _bind_database_command(
                    connection,
                    tenant_id=TENANT_A_ID,
                    actor_id=EMPLOYEE_B_USER_ID,
                    membership_id=EMPLOYEE_B_MEMBERSHIP_ID,
                    intent="p4e_submit",
                    target_id=uuid4(),
                )
        assert sqlstate_from_error(cross_tenant_error.value) == "42501"

        with pytest.raises(DBAPIError) as actor_membership_error:
            async with engine.begin() as connection:
                await _bind_database_command(
                    connection,
                    tenant_id=TENANT_A_ID,
                    actor_id=HR_A_USER_ID,
                    membership_id=EMPLOYEE_A_MEMBERSHIP_ID,
                    intent="p4e_submit",
                    target_id=uuid4(),
                )
        assert sqlstate_from_error(actor_membership_error.value) == "42501"

        bound_target = uuid4()
        async with engine.begin() as connection:
            await _bind_database_command(
                connection,
                tenant_id=TENANT_A_ID,
                actor_id=EMPLOYEE_A_USER_ID,
                membership_id=EMPLOYEE_A_MEMBERSHIP_ID,
                intent="p4e_submit",
                target_id=bound_target,
            )
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            parameters = {
                "request_id": uuid4(),
                "preferred_changed": True,
                "preferred_value": "Target Mismatch",
                "phone_changed": False,
                "phone_value": None,
                "birth_changed": False,
                "birth_value": None,
            }
            assert str(await connection.scalar(SUBMIT_SQL, parameters)) == ("context_invalid")
            parameters["request_id"] = bound_target
            parameters["preferred_value"] = "masked*"
            assert str(await connection.scalar(SUBMIT_SQL, parameters)) == ("invalid_request")

        intent_target = uuid4()
        async with engine.begin() as connection:
            await _bind_database_command(
                connection,
                tenant_id=TENANT_A_ID,
                actor_id=HR_A_USER_ID,
                membership_id=HR_A_MEMBERSHIP_ID,
                intent="p4e_approve",
                target_id=intent_target,
            )
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            assert (
                str(
                    await connection.scalar(
                        TRANSITION_SQL,
                        {
                            "request_id": intent_target,
                            "expected_version": 1,
                            "action": "cancel",
                            "reason": None,
                        },
                    )
                )
                == "context_invalid"
            )
            assert (
                str(
                    await connection.scalar(
                        TRANSITION_SQL,
                        {
                            "request_id": intent_target,
                            "expected_version": 1,
                            "action": "approve",
                            "reason": None,
                        },
                    )
                )
                == "not_found"
            )

        one_use_target = uuid4()
        async with engine.begin() as connection:
            await _bind_database_command(
                connection,
                tenant_id=TENANT_A_ID,
                actor_id=EMPLOYEE_A_USER_ID,
                membership_id=EMPLOYEE_A_MEMBERSHIP_ID,
                intent="p4e_submit",
                target_id=one_use_target,
                request_id="api.v1.profile..change",
            )
            with pytest.raises(DBAPIError) as rebind_error:
                async with connection.begin_nested():
                    await _bind_database_command(
                        connection,
                        tenant_id=TENANT_A_ID,
                        actor_id=EMPLOYEE_A_USER_ID,
                        membership_id=EMPLOYEE_A_MEMBERSHIP_ID,
                        intent="p4e_submit",
                        target_id=one_use_target,
                    )
            assert sqlstate_from_error(rebind_error.value) == "55000"
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            invalid_parameters = {
                "request_id": one_use_target,
                "preferred_changed": True,
                "preferred_value": "masked*",
                "phone_changed": False,
                "phone_value": None,
                "birth_changed": False,
                "birth_value": None,
            }
            assert str(await connection.scalar(SUBMIT_SQL, invalid_parameters)) == (
                "invalid_request"
            )
            assert str(await connection.scalar(SUBMIT_SQL, invalid_parameters)) == (
                "context_invalid"
            )

        first_tombstone = await _binding_tombstones(database_url)
        assert len(first_tombstone) == 1
        assert first_tombstone[0][0] == "executed"
        second_target = uuid4()
        async with engine.begin() as connection:
            await _bind_database_command(
                connection,
                tenant_id=TENANT_A_ID,
                actor_id=EMPLOYEE_A_USER_ID,
                membership_id=EMPLOYEE_A_MEMBERSHIP_ID,
                intent="p4e_submit",
                target_id=second_target,
            )
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            assert (
                str(
                    await connection.scalar(
                        SUBMIT_SQL,
                        {
                            "request_id": second_target,
                            "preferred_changed": True,
                            "preferred_value": "masked•",
                            "phone_changed": False,
                            "phone_value": None,
                            "birth_changed": False,
                            "birth_value": None,
                        },
                    )
                )
                == "invalid_request"
            )
        second_tombstone = await _binding_tombstones(database_url)
        assert len(second_tombstone) == 1
        assert second_tombstone[0][0] == "executed"
        assert second_tombstone[0][1] == second_target
    finally:
        await engine.dispose()


async def _assert_races(database_url: URL) -> None:
    first_submit_id = uuid4()
    second_submit_id = uuid4()
    submit_outcomes = await _race_submits(
        database_url,
        request_ids=(first_submit_id, second_submit_id),
    )
    assert sorted(submit_outcomes) == ["active_request_exists", "submitted"]
    active_request_id = first_submit_id if submit_outcomes[0] == "submitted" else second_submit_id
    assert await _request_count(database_url) == 1
    assert (
        await _call_transition(
            database_url,
            request_id=active_request_id,
            action="cancel",
            actor_id=EMPLOYEE_A_USER_ID,
            membership_id=EMPLOYEE_A_MEMBERSHIP_ID,
        )
        == "cancelled"
    )
    assert await _audit_event_types(database_url, active_request_id) == [
        "employee.profile_change_request.submitted",
        "employee.profile_change_request.cancelled",
    ]

    approve_request_id = uuid4()
    assert (
        await _call_submit(
            database_url,
            request_id=approve_request_id,
            preferred_value="Approve Winner",
        )
        == "submitted"
    )
    profile_before = await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID)
    approve_outcomes = await _race_transitions(
        database_url,
        request_id=approve_request_id,
        contenders=(
            ("approve", HR_A_USER_ID, HR_A_MEMBERSHIP_ID, None),
            ("approve", HR_A_USER_ID, HR_A_MEMBERSHIP_ID, None),
        ),
    )
    assert sorted(approve_outcomes) == ["approved", "version_conflict"]
    approve_request = await _request_state(database_url, approve_request_id)
    assert approve_request["status"] == "approved"
    assert approve_request["version"] == 2
    profile_after = await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID)
    assert profile_after[0] == "Approve Winner"
    assert profile_after[3] == profile_before[3] + 1
    assert await _audit_event_types(database_url, approve_request_id) == [
        "employee.profile_change_request.submitted",
        "employee.profile_change_request.approved",
    ]

    approve_reject_id = uuid4()
    assert (
        await _call_submit(
            database_url,
            request_id=approve_reject_id,
            preferred_value="Approve Or Reject",
        )
        == "submitted"
    )
    profile_before = await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID)
    decision_outcomes = await _race_transitions(
        database_url,
        request_id=approve_reject_id,
        contenders=(
            ("approve", HR_A_USER_ID, HR_A_MEMBERSHIP_ID, None),
            ("reject", HR_A_USER_ID, HR_A_MEMBERSHIP_ID, "Race rejection"),
        ),
    )
    assert decision_outcomes.count("version_conflict") == 1
    winner = next(outcome for outcome in decision_outcomes if outcome != "version_conflict")
    assert winner in {"approved", "rejected"}
    decision_request = await _request_state(database_url, approve_reject_id)
    assert decision_request["status"] == winner
    assert decision_request["version"] == 2
    profile_after = await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID)
    if winner == "approved":
        assert profile_after[0] == "Approve Or Reject"
        assert profile_after[3] == profile_before[3] + 1
    else:
        assert profile_after == profile_before
    assert await _audit_event_types(database_url, approve_reject_id) == [
        "employee.profile_change_request.submitted",
        f"employee.profile_change_request.{winner}",
    ]

    approve_cancel_id = uuid4()
    assert (
        await _call_submit(
            database_url,
            request_id=approve_cancel_id,
            preferred_value="Approve Or Cancel",
        )
        == "submitted"
    )
    profile_before = await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID)
    cancel_outcomes = await _race_transitions(
        database_url,
        request_id=approve_cancel_id,
        contenders=(
            ("approve", HR_A_USER_ID, HR_A_MEMBERSHIP_ID, None),
            ("cancel", EMPLOYEE_A_USER_ID, EMPLOYEE_A_MEMBERSHIP_ID, None),
        ),
    )
    assert cancel_outcomes.count("version_conflict") == 1
    winner = next(outcome for outcome in cancel_outcomes if outcome != "version_conflict")
    assert winner in {"approved", "cancelled"}
    cancel_request = await _request_state(database_url, approve_cancel_id)
    assert cancel_request["status"] == winner
    assert cancel_request["version"] == 2
    profile_after = await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID)
    if winner == "approved":
        assert profile_after[0] == "Approve Or Cancel"
        assert profile_after[3] == profile_before[3] + 1
    else:
        assert profile_after == profile_before
    assert await _audit_event_types(database_url, approve_cancel_id) == [
        "employee.profile_change_request.submitted",
        f"employee.profile_change_request.{winner}",
    ]

    submit_approve_id = uuid4()
    assert (
        await _call_submit(
            database_url,
            request_id=submit_approve_id,
            preferred_value="Submit Approve Existing",
        )
        == "submitted"
    )
    profile_before = await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID)
    next_submit_id = uuid4()
    approve_outcome, submit_outcome = await _race_submit_vs_approve(
        database_url,
        active_request_id=submit_approve_id,
        next_request_id=next_submit_id,
    )
    assert approve_outcome == "approved"
    assert submit_outcome in {"active_request_exists", "submitted"}
    profile_after = await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID)
    assert profile_after[0] == "Submit Approve Existing"
    assert profile_after[3] == profile_before[3] + 1
    assert await _audit_event_types(database_url, submit_approve_id) == [
        "employee.profile_change_request.submitted",
        "employee.profile_change_request.approved",
    ]
    expected_next_audit = (
        ["employee.profile_change_request.submitted"] if submit_outcome == "submitted" else []
    )
    assert await _audit_event_types(database_url, next_submit_id) == expected_next_audit
    if submit_outcome == "submitted":
        assert (
            await _call_transition(
                database_url,
                request_id=next_submit_id,
                action="cancel",
                actor_id=EMPLOYEE_A_USER_ID,
                membership_id=EMPLOYEE_A_MEMBERSHIP_ID,
            )
            == "cancelled"
        )


async def _race_submits(
    database_url: URL,
    *,
    request_ids: tuple[UUID, UUID],
) -> tuple[str, str]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    ready: asyncio.Queue[None] = asyncio.Queue()
    release = asyncio.Event()

    async def contender(request_id: UUID, value: str) -> str:
        async with engine.begin() as connection:
            await _bind_database_command(
                connection,
                tenant_id=TENANT_A_ID,
                actor_id=EMPLOYEE_A_USER_ID,
                membership_id=EMPLOYEE_A_MEMBERSHIP_ID,
                intent="p4e_submit",
                target_id=request_id,
            )
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            await ready.put(None)
            await release.wait()
            outcome = await connection.scalar(
                SUBMIT_SQL,
                {
                    "request_id": request_id,
                    "preferred_changed": True,
                    "preferred_value": value,
                    "phone_changed": False,
                    "phone_value": None,
                    "birth_changed": False,
                    "birth_value": None,
                },
            )
            return str(outcome)

    tasks: tuple[asyncio.Task[str], ...] = ()
    try:
        tasks = (
            asyncio.create_task(contender(request_ids[0], "Submit Race One")),
            asyncio.create_task(contender(request_ids[1], "Submit Race Two")),
        )
        await asyncio.wait_for(ready.get(), timeout=5)
        await asyncio.wait_for(ready.get(), timeout=5)
        release.set()
        return tuple(await asyncio.wait_for(asyncio.gather(*tasks), timeout=15))  # type: ignore[return-value]
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()


async def _race_submit_vs_approve(
    database_url: URL,
    *,
    active_request_id: UUID,
    next_request_id: UUID,
) -> tuple[str, str]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    ready: asyncio.Queue[None] = asyncio.Queue()
    release = asyncio.Event()

    async def approve() -> str:
        async with engine.begin() as connection:
            await _bind_database_command(
                connection,
                tenant_id=TENANT_A_ID,
                actor_id=HR_A_USER_ID,
                membership_id=HR_A_MEMBERSHIP_ID,
                intent="p4e_approve",
                target_id=active_request_id,
            )
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            await ready.put(None)
            await release.wait()
            return str(
                await connection.scalar(
                    TRANSITION_SQL,
                    {
                        "request_id": active_request_id,
                        "expected_version": 1,
                        "action": "approve",
                        "reason": None,
                    },
                )
            )

    async def submit() -> str:
        async with engine.begin() as connection:
            await _bind_database_command(
                connection,
                tenant_id=TENANT_A_ID,
                actor_id=EMPLOYEE_A_USER_ID,
                membership_id=EMPLOYEE_A_MEMBERSHIP_ID,
                intent="p4e_submit",
                target_id=next_request_id,
            )
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            await ready.put(None)
            await release.wait()
            return str(
                await connection.scalar(
                    SUBMIT_SQL,
                    {
                        "request_id": next_request_id,
                        "preferred_changed": True,
                        "preferred_value": "Post Approval Request",
                        "phone_changed": False,
                        "phone_value": None,
                        "birth_changed": False,
                        "birth_value": None,
                    },
                )
            )

    tasks = (asyncio.create_task(approve()), asyncio.create_task(submit()))
    try:
        await asyncio.wait_for(ready.get(), timeout=5)
        await asyncio.wait_for(ready.get(), timeout=5)
        release.set()
        outcomes = await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
        return str(outcomes[0]), str(outcomes[1])
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()


async def _race_transitions(
    database_url: URL,
    *,
    request_id: UUID,
    contenders: tuple[tuple[str, UUID, UUID, str | None], ...],
) -> tuple[str, ...]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    ready: asyncio.Queue[None] = asyncio.Queue()
    release = asyncio.Event()

    async def contender(
        action: str,
        actor_id: UUID,
        membership_id: UUID,
        reason: str | None,
    ) -> str:
        async with engine.begin() as connection:
            await _bind_database_command(
                connection,
                tenant_id=TENANT_A_ID,
                actor_id=actor_id,
                membership_id=membership_id,
                intent=f"p4e_{action}",
                target_id=request_id,
            )
            await _set_local_role(connection, TENANT_APPLICATION_ROLE)
            await ready.put(None)
            await release.wait()
            outcome = await connection.scalar(
                TRANSITION_SQL,
                {
                    "request_id": request_id,
                    "expected_version": 1,
                    "action": action,
                    "reason": reason,
                },
            )
            return str(outcome)

    tasks: tuple[asyncio.Task[str], ...] = ()
    try:
        tasks = tuple(asyncio.create_task(contender(*item)) for item in contenders)
        for _ in tasks:
            await asyncio.wait_for(ready.get(), timeout=5)
        release.set()
        return tuple(await asyncio.wait_for(asyncio.gather(*tasks), timeout=15))
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()


async def _seed_pre_p4e_fixture(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone"
                    ") values "
                    "(:tenant_a, 'p4e-a', 'P4E Tenant A', 'active', 'core', "
                    "'tr-1', 'en-US', 'UTC'), "
                    "(:tenant_b, 'p4e-b', 'P4E Tenant B', 'active', 'core', "
                    "'tr-1', 'en-US', 'UTC')"
                ),
                {"tenant_a": TENANT_A_ID, "tenant_b": TENANT_B_ID},
            )
            await connection.execute(
                text(
                    "insert into identities (id, email, status, password_hash) values "
                    "(:employee_a, 'employee-a@p4e.test', 'active', 'p4e-hash'), "
                    "(:hr_a, 'hr-a@p4e.test', 'active', 'p4e-hash'), "
                    "(:manager_a, 'manager-a@p4e.test', 'active', 'p4e-hash'), "
                    "(:employee_b, 'employee-b@p4e.test', 'active', 'p4e-hash')"
                ),
                {
                    "employee_a": EMPLOYEE_A_IDENTITY_ID,
                    "hr_a": HR_A_IDENTITY_ID,
                    "manager_a": MANAGER_A_IDENTITY_ID,
                    "employee_b": EMPLOYEE_B_IDENTITY_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into users ("
                    "id, tenant_id, email, full_name, status, password_hash, permission_version"
                    ") values "
                    "(:employee_a, :tenant_a, 'employee-a@p4e.test', 'Employee A', "
                    "'active', 'p4e-hash', 1), "
                    "(:hr_a, :tenant_a, 'hr-a@p4e.test', 'HR A', "
                    "'active', 'p4e-hash', 1), "
                    "(:manager_a, :tenant_a, 'manager-a@p4e.test', 'Manager A', "
                    "'active', 'p4e-hash', 1), "
                    "(:employee_b, :tenant_b, 'employee-b@p4e.test', 'Employee B', "
                    "'active', 'p4e-hash', 1)"
                ),
                {
                    "tenant_a": TENANT_A_ID,
                    "tenant_b": TENANT_B_ID,
                    "employee_a": EMPLOYEE_A_USER_ID,
                    "hr_a": HR_A_USER_ID,
                    "manager_a": MANAGER_A_USER_ID,
                    "employee_b": EMPLOYEE_B_USER_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into tenant_memberships ("
                    "id, tenant_id, identity_id, legacy_user_id, full_name, status, "
                    "permission_version"
                    ") values "
                    "(:employee_a_membership, :tenant_a, :employee_a_identity, "
                    ":employee_a_user, 'Employee A', 'active', 1), "
                    "(:hr_a_membership, :tenant_a, :hr_a_identity, :hr_a_user, "
                    "'HR A', 'active', 1), "
                    "(:manager_a_membership, :tenant_a, :manager_a_identity, "
                    ":manager_a_user, 'Manager A', 'active', 1), "
                    "(:employee_b_membership, :tenant_b, :employee_b_identity, "
                    ":employee_b_user, 'Employee B', 'active', 1)"
                ),
                {
                    "tenant_a": TENANT_A_ID,
                    "tenant_b": TENANT_B_ID,
                    "employee_a_membership": EMPLOYEE_A_MEMBERSHIP_ID,
                    "hr_a_membership": HR_A_MEMBERSHIP_ID,
                    "manager_a_membership": MANAGER_A_MEMBERSHIP_ID,
                    "employee_b_membership": EMPLOYEE_B_MEMBERSHIP_ID,
                    "employee_a_identity": EMPLOYEE_A_IDENTITY_ID,
                    "hr_a_identity": HR_A_IDENTITY_ID,
                    "manager_a_identity": MANAGER_A_IDENTITY_ID,
                    "employee_b_identity": EMPLOYEE_B_IDENTITY_ID,
                    "employee_a_user": EMPLOYEE_A_USER_ID,
                    "hr_a_user": HR_A_USER_ID,
                    "manager_a_user": MANAGER_A_USER_ID,
                    "employee_b_user": EMPLOYEE_B_USER_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into membership_roles ("
                    "tenant_id, membership_id, role_id, role_scope_type, active"
                    ") values "
                    "(:tenant_a, :employee_a, :employee_role, 'tenant', true), "
                    "(:tenant_a, :hr_a, :hr_role, 'tenant', true), "
                    "(:tenant_a, :manager_a, :manager_role, 'tenant', true), "
                    "(:tenant_b, :employee_b, :hr_role, 'tenant', true)"
                ),
                {
                    "tenant_a": TENANT_A_ID,
                    "tenant_b": TENANT_B_ID,
                    "employee_a": EMPLOYEE_A_MEMBERSHIP_ID,
                    "hr_a": HR_A_MEMBERSHIP_ID,
                    "manager_a": MANAGER_A_MEMBERSHIP_ID,
                    "employee_b": EMPLOYEE_B_MEMBERSHIP_ID,
                    "employee_role": EMPLOYEE_ROLE_ID,
                    "hr_role": HR_DIRECTOR_ROLE_ID,
                    "manager_role": MANAGER_ROLE_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into employees ("
                    "id, tenant_id, employee_number, first_name, last_name, email, "
                    "status, employment_start_date"
                    ") values "
                    "(:employee_a, :tenant_a, 'P4E-A', 'Ada', 'Employee', "
                    "'employee-a@p4e.test', 'active', DATE '2026-07-01'), "
                    "(:employee_b, :tenant_b, 'P4E-B', 'Bora', 'Employee', "
                    "'employee-b@p4e.test', 'active', DATE '2026-07-01')"
                ),
                {
                    "employee_a": EMPLOYEE_A_ID,
                    "employee_b": EMPLOYEE_B_ID,
                    "tenant_a": TENANT_A_ID,
                    "tenant_b": TENANT_B_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into employee_profiles ("
                    "id, tenant_id, employee_id, preferred_name, birth_date, phone, version"
                    ") values "
                    "(:profile_a, :tenant_a, :employee_a, 'Ada   Alias', "
                    "DATE '1990-02-03', '+90 (555) 123-4567', 1), "
                    "(:profile_b, :tenant_b, :employee_b, 'Bora Alias', "
                    "DATE '1991-03-04', '+905551234568', 1)"
                ),
                {
                    "profile_a": PROFILE_A_ID,
                    "profile_b": PROFILE_B_ID,
                    "tenant_a": TENANT_A_ID,
                    "tenant_b": TENANT_B_ID,
                    "employee_a": EMPLOYEE_A_ID,
                    "employee_b": EMPLOYEE_B_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into employee_employments ("
                    "id, tenant_id, employee_id, contract_type, work_type, version"
                    ") values "
                    "(:employment_a, :tenant_a, :employee_a, 'indefinite', 'full_time', 1), "
                    "(:employment_b, :tenant_b, :employee_b, 'indefinite', 'full_time', 1)"
                ),
                {
                    "employment_a": EMPLOYMENT_A_ID,
                    "employment_b": EMPLOYMENT_B_ID,
                    "tenant_a": TENANT_A_ID,
                    "tenant_b": TENANT_B_ID,
                    "employee_a": EMPLOYEE_A_ID,
                    "employee_b": EMPLOYEE_B_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into employee_account_links ("
                    "id, tenant_id, employee_id, membership_id, version"
                    ") values "
                    "(:link_a, :tenant_a, :employee_a, :membership_a, 1), "
                    "(:link_b, :tenant_b, :employee_b, :membership_b, 1)"
                ),
                {
                    "link_a": LINK_A_ID,
                    "link_b": LINK_B_ID,
                    "tenant_a": TENANT_A_ID,
                    "tenant_b": TENANT_B_ID,
                    "employee_a": EMPLOYEE_A_ID,
                    "employee_b": EMPLOYEE_B_ID,
                    "membership_a": EMPLOYEE_A_MEMBERSHIP_ID,
                    "membership_b": EMPLOYEE_B_MEMBERSHIP_ID,
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
                EXECUTOR_ROLE,
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


async def _create_gateway_role(database_url: URL, gateway_role: str) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            quoted_gateway = connection.dialect.identifier_preparer.quote(gateway_role)
            quoted_capability = connection.dialect.identifier_preparer.quote(
                TENANT_APPLICATION_ROLE
            )
            await connection.exec_driver_sql(
                f"CREATE ROLE {quoted_gateway} LOGIN NOSUPERUSER NOBYPASSRLS "
                "NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT"
            )
            await connection.exec_driver_sql(
                f"GRANT {quoted_capability} TO {quoted_gateway} "
                "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE"
            )
    finally:
        await engine.dispose()


async def _drop_gateway_role(database_url: URL, gateway_role: str) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            quoted_gateway = connection.dialect.identifier_preparer.quote(gateway_role)
            quoted_capability = connection.dialect.identifier_preparer.quote(
                TENANT_APPLICATION_ROLE
            )
            await connection.exec_driver_sql(f"DROP OWNED BY {quoted_gateway}")
            await connection.exec_driver_sql(f"REVOKE {quoted_capability} FROM {quoted_gateway}")
            await connection.exec_driver_sql(f"DROP ROLE {quoted_gateway}")
    finally:
        await engine.dispose()


async def _assert_gateway_binding_grants(
    database_url: URL,
    gateway_role: str,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            role = (
                await connection.execute(
                    text(
                        "select rolcanlogin, rolsuper, rolbypassrls, rolcreaterole, "
                        "rolcreatedb, rolreplication from pg_catalog.pg_roles "
                        "where rolname = :role_name"
                    ),
                    {"role_name": gateway_role},
                )
            ).one()
            assert tuple(bool(value) for value in role) == (
                True,
                False,
                False,
                False,
                False,
                False,
            )
            assert bool(
                await connection.scalar(
                    text("select has_schema_privilege(:role, :schema, 'USAGE')"),
                    {"role": gateway_role, "schema": COMMAND_SCHEMA},
                )
            )
            assert not bool(
                await connection.scalar(
                    text("select has_schema_privilege(:role, :schema, 'CREATE')"),
                    {"role": gateway_role, "schema": COMMAND_SCHEMA},
                )
            )
            binder_signature = (
                "p4e_command.bind_database_command(uuid,uuid,uuid,character varying,"
                "uuid,uuid,character varying,character varying,uuid)"
            )
            assert bool(
                await connection.scalar(
                    text("select has_function_privilege(:role, :signature, 'EXECUTE')"),
                    {"role": gateway_role, "signature": binder_signature},
                )
            )
            for private_signature in (
                "p4e_command.claim_database_command(character varying,uuid)",
                "p4e_command.write_employee_profile_change_request_audit()",
            ):
                assert not bool(
                    await connection.scalar(
                        text("select has_function_privilege(:role, :signature, 'EXECUTE')"),
                        {"role": gateway_role, "signature": private_signature},
                    )
                )
            direct_binder_grantees = set(
                await connection.scalars(
                    text(
                        "select grantee.rolname from pg_catalog.pg_proc as procedure "
                        "join pg_catalog.pg_namespace as namespace "
                        "on namespace.oid = procedure.pronamespace "
                        "cross join lateral aclexplode(procedure.proacl) as acl "
                        "join pg_catalog.pg_roles as grantee on grantee.oid = acl.grantee "
                        "where namespace.nspname = 'p4e_command' "
                        "and procedure.proname = 'bind_database_command' "
                        "and acl.privilege_type = 'EXECUTE'"
                    )
                )
            )
            assert direct_binder_grantees == {EXECUTOR_ROLE, gateway_role}
            assert not bool(
                await connection.scalar(
                    text(
                        "select exists (select 1 from pg_catalog.pg_roles as roles "
                        "where roles.rolname = any(:role_names) "
                        "and (roles.rolsuper or roles.rolbypassrls))"
                    ),
                    {"role_names": list(direct_binder_grantees - {EXECUTOR_ROLE})},
                )
            )
    finally:
        await engine.dispose()


async def _assert_permission_denied(
    engine: AsyncEngine,
    statement,
    parameters: dict[str, object],
) -> None:
    with pytest.raises(DBAPIError) as error:
        async with engine.begin() as connection:
            await _set_local_tenant_actor_role(
                connection,
                tenant_id=TENANT_A_ID,
                actor_id=HR_A_USER_ID,
                membership_id=HR_A_MEMBERSHIP_ID,
            )
            await connection.execute(statement, parameters)
    assert sqlstate_from_error(error.value) == "42501"


async def _binding_tombstones(database_url: URL) -> list[tuple[str, UUID]]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return [
                (str(row.state), row.target_id)
                for row in (
                    await connection.execute(
                        text(
                            "select state, target_id from "
                            "p4e_command.database_command_bindings order by bound_at"
                        )
                    )
                )
            ]
    finally:
        await engine.dispose()


async def _audit_event_types(database_url: URL, request_id: UUID) -> list[str]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return list(
                await connection.scalars(
                    text(
                        "select event_type from audit_events "
                        "where resource_type = 'employee_profile_change_request' "
                        "and resource_id = :request_id order by occurred_at, id"
                    ),
                    {"request_id": request_id},
                )
            )
    finally:
        await engine.dispose()


async def _assert_audit_value_redaction(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "select actor_user_id, impersonator_user_id, reason, changed_fields, "
                        "before_data, after_data, metadata, data_classification, visibility_class "
                        "from audit_events where "
                        "resource_type = 'employee_profile_change_request'"
                    )
                )
            ).mappings()
            assert rows
            allowed_actors = {EMPLOYEE_A_USER_ID, HR_A_USER_ID}
            allowed_changed_fields = {"preferred_name", "phone", "birth_date"}
            for row in rows:
                assert row["actor_user_id"] in allowed_actors
                assert row["impersonator_user_id"] is None
                assert row["reason"] is None
                assert set(row["changed_fields"]) <= allowed_changed_fields
                assert row["before_data"] == {}
                assert row["after_data"] == {}
                assert set(row["metadata"]) == {
                    "request_id",
                    "employee_id",
                    "before_request_status",
                    "after_request_status",
                    "reason_code",
                }
                assert row["data_classification"] == "hr_metadata"
                assert row["visibility_class"] == "hr_operations"

            serialized_events = str(
                await connection.scalar(
                    text(
                        "select coalesce(string_agg(to_jsonb(events)::text, ''), '') "
                        "from audit_events as events where "
                        "events.resource_type = 'employee_profile_change_request'"
                    )
                )
                or ""
            )
            for forbidden_value in (
                "Ada Rejected",
                "Employee Proposed",
                "HR Changed",
                "+90 (555) 123-4567",
                "1990-02-03",
                "Policy mismatch",
                str(EMPLOYEE_A_MEMBERSHIP_ID),
                str(HR_A_MEMBERSHIP_ID),
            ):
                assert forbidden_value not in serialized_events
    finally:
        await engine.dispose()


async def _assert_denied_actor_does_not_lock_request(
    database_url: URL,
    *,
    active_request_id: UUID,
) -> None:
    assert (
        await _call_transition(
            database_url,
            request_id=active_request_id,
            action="cancel",
            actor_id=EMPLOYEE_A_USER_ID,
            membership_id=EMPLOYEE_A_MEMBERSHIP_ID,
        )
        == "cancelled"
    )
    request_id = uuid4()
    assert (
        await _call_submit(
            database_url,
            request_id=request_id,
            preferred_value="Authorization Before Lock",
        )
        == "submitted"
    )

    engine = create_async_engine(database_url, poolclass=NullPool)
    denied_connection = await engine.connect()
    denied_transaction = await denied_connection.begin()
    try:
        await _bind_database_command(
            denied_connection,
            tenant_id=TENANT_A_ID,
            actor_id=MANAGER_A_USER_ID,
            membership_id=MANAGER_A_MEMBERSHIP_ID,
            intent="p4e_approve",
            target_id=request_id,
        )
        await _set_local_role(denied_connection, TENANT_APPLICATION_ROLE)
        assert (
            str(
                await denied_connection.scalar(
                    TRANSITION_SQL,
                    {
                        "request_id": request_id,
                        "expected_version": 1,
                        "action": "approve",
                        "reason": None,
                    },
                )
            )
            == "access_denied"
        )

        async def authorized_approval() -> str:
            async with engine.begin() as connection:
                await _bind_database_command(
                    connection,
                    tenant_id=TENANT_A_ID,
                    actor_id=HR_A_USER_ID,
                    membership_id=HR_A_MEMBERSHIP_ID,
                    intent="p4e_approve",
                    target_id=request_id,
                )
                await _set_local_role(connection, TENANT_APPLICATION_ROLE)
                await connection.exec_driver_sql("SET LOCAL lock_timeout = '750ms'")
                return str(
                    await connection.scalar(
                        TRANSITION_SQL,
                        {
                            "request_id": request_id,
                            "expected_version": 1,
                            "action": "approve",
                            "reason": None,
                        },
                    )
                )

        assert await asyncio.wait_for(authorized_approval(), timeout=2) == "approved"
    finally:
        await denied_transaction.rollback()
        await denied_connection.close()
        await engine.dispose()


async def _assert_p4b_update_only_permission(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "delete from role_permissions as grants using permissions "
                    "where grants.permission_id = permissions.id "
                    "and grants.role_id = :role_id "
                    "and permissions.code = 'employee:read:tenant'"
                ),
                {"role_id": HR_DIRECTOR_ROLE_ID},
            )
            permission_codes = set(
                await connection.scalars(
                    text(
                        "select permissions.code from role_permissions as grants "
                        "join permissions on permissions.id = grants.permission_id "
                        "where grants.role_id = :role_id and permissions.code in ("
                        "'employee:read:tenant', 'employee:update:tenant')"
                    ),
                    {"role_id": HR_DIRECTOR_ROLE_ID},
                )
            )
            assert permission_codes == {"employee:update:tenant"}
    finally:
        await engine.dispose()

    before = await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID)
    assert (
        await _call_personal_update(
            database_url,
            employee_id=EMPLOYEE_A_ID,
            expected_version=before[3],
            preferred_value="Update Only Actor",
        )
        == "updated"
    )
    after = await _profile_state(database_url, TENANT_A_ID, EMPLOYEE_A_ID)
    assert after[0] == "Update Only Actor"
    assert after[3] == before[3] + 1


async def _profile_state(
    database_url: URL,
    tenant_id: UUID,
    employee_id: UUID,
) -> tuple[str | None, str | None, date | None, int]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "select preferred_name, phone, birth_date, version "
                        "from employee_profiles "
                        "where tenant_id = :tenant_id and employee_id = :employee_id"
                    ),
                    {"tenant_id": tenant_id, "employee_id": employee_id},
                )
            ).one()
            return row.preferred_name, row.phone, row.birth_date, int(row.version)
    finally:
        await engine.dispose()


async def _request_state(database_url: URL, request_id: UUID) -> dict[str, object]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "select tenant_id, employee_id, requester_membership_id, "
                            "requester_user_id, status, version, base_profile_version, "
                            "previous_preferred_name, proposed_preferred_name, "
                            "previous_phone, proposed_phone "
                            "from employee_profile_change_requests where id = :request_id"
                        ),
                        {"request_id": request_id},
                    )
                )
                .mappings()
                .one()
            )
            return dict(row)
    finally:
        await engine.dispose()


async def _direct_table_privileges(
    connection: AsyncConnection,
    *,
    table_name: str,
    role_name: str,
    schema_name: str = "public",
) -> set[str]:
    return set(
        await connection.scalars(
            text(
                "select privilege_type from information_schema.table_privileges "
                "where table_schema = :schema_name and table_name = :table_name "
                "and grantee = :role_name"
            ),
            {
                "schema_name": schema_name,
                "table_name": table_name,
                "role_name": role_name,
            },
        )
    )


async def _column_privileges(
    connection: AsyncConnection,
    *,
    table_name: str,
    role_name: str,
    privilege: str,
    schema_name: str = "public",
) -> set[str]:
    return set(
        await connection.scalars(
            text(
                "select column_name from information_schema.column_privileges "
                "where table_schema = :schema_name and table_name = :table_name "
                "and grantee = :role_name and privilege_type = :privilege"
            ),
            {
                "schema_name": schema_name,
                "table_name": table_name,
                "role_name": role_name,
                "privilege": privilege,
            },
        )
    )


async def _all_column_privileges(
    connection: AsyncConnection,
    *,
    table_name: str,
    role_name: str,
    schema_name: str = "public",
) -> set[tuple[str, str]]:
    return {
        (row.column_name, row.privilege_type)
        for row in (
            await connection.execute(
                text(
                    "select column_name, privilege_type "
                    "from information_schema.column_privileges "
                    "where table_schema = :schema_name and table_name = :table_name "
                    "and grantee = :role_name"
                ),
                {
                    "schema_name": schema_name,
                    "table_name": table_name,
                    "role_name": role_name,
                },
            )
        )
    }


async def _profile_update_columns(database_url: URL) -> set[str]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await _profile_update_columns_from_connection(connection)
    finally:
        await engine.dispose()


async def _profile_update_columns_from_connection(
    connection: AsyncConnection,
) -> set[str]:
    return await _column_privileges(
        connection,
        table_name="employee_profiles",
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
    )


async def _request_count(database_url: URL) -> int:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return int(
                await connection.scalar(
                    text("select count(*) from employee_profile_change_requests")
                )
            )
    finally:
        await engine.dispose()


async def _request_row_security_flags(database_url: URL) -> tuple[bool, bool]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await _request_row_security_flags_from_connection(connection)
    finally:
        await engine.dispose()


async def _request_row_security_flags_from_connection(
    connection: AsyncConnection,
) -> tuple[bool, bool]:
    row = (
        await connection.execute(
            text(
                "select relrowsecurity, relforcerowsecurity from pg_catalog.pg_class "
                "where oid = 'public.employee_profile_change_requests'::regclass"
            )
        )
    ).one()
    return bool(row[0]), bool(row[1])


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


async def _schema_exists(database_url: URL, schema_name: str) -> bool:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text(
                        "select exists (select 1 from pg_catalog.pg_namespace "
                        "where nspname = :schema_name)"
                    ),
                    {"schema_name": schema_name},
                )
            )
    finally:
        await engine.dispose()


async def _p4c_eligibility_contract(database_url: URL) -> bool:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "select owner.rolname as owner_name, procedure.prosecdef, "
                            "procedure.proconfig, "
                            "has_function_privilege(:app_role, procedure.oid, 'EXECUTE') "
                            "as app_execute from pg_catalog.pg_proc as procedure "
                            "join pg_catalog.pg_namespace as namespace "
                            "on namespace.oid = procedure.pronamespace "
                            "join pg_catalog.pg_roles as owner on owner.oid = procedure.proowner "
                            "where namespace.nspname = 'public' and procedure.proname = "
                            "'is_current_tenant_membership_link_eligible'"
                        ),
                        {"app_role": TENANT_APPLICATION_ROLE},
                    )
                )
                .mappings()
                .one_or_none()
            )
            return bool(
                row
                and row["owner_name"] == EXECUTOR_ROLE
                and row["prosecdef"] is True
                and row["proconfig"] == ["search_path=pg_catalog, public"]
                and row["app_execute"] is True
            )
    finally:
        await engine.dispose()


async def _p4e_functions_exist(database_url: URL) -> bool:
    engine = create_async_engine(database_url, poolclass=NullPool)
    signatures = (
        "public.submit_own_employee_profile_change_request("
        "uuid,boolean,character varying,boolean,character varying,boolean,date)",
        "public.transition_employee_profile_change_request("
        "uuid,integer,character varying,character varying)",
        "public.update_employee_personal_profile_values("
        "uuid,integer,boolean,character varying,boolean,character varying,boolean,date)",
    )
    try:
        async with engine.connect() as connection:
            existence = []
            for signature in signatures:
                existence.append(
                    bool(
                        await connection.scalar(
                            text("select to_regprocedure(:signature) is not null"),
                            {"signature": signature},
                        )
                    )
                )
            return all(existence)
    finally:
        await engine.dispose()


async def _source_counts(database_url: URL) -> tuple[int, ...]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "select (select count(*) from employees), "
                        "(select count(*) from employee_profiles), "
                        "(select count(*) from employee_employments), "
                        "(select count(*) from employee_account_links), "
                        "(select count(*) from tenant_memberships)"
                    )
                )
            ).one()
            return tuple(int(value) for value in row)
    finally:
        await engine.dispose()


async def _set_local_tenant_actor_role(
    connection: AsyncConnection,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    membership_id: UUID,
    role_already_set: bool = False,
) -> None:
    if not role_already_set:
        await _set_local_role(connection, TENANT_APPLICATION_ROLE)
    for key, value in (
        ("tenant_id", tenant_id),
        ("actor_id", actor_id),
        ("membership_id", membership_id),
    ):
        await connection.execute(
            text("select set_config(:setting_name, :setting_value, true)"),
            {"setting_name": f"app.{key}", "setting_value": str(value)},
        )


async def _bind_database_command(
    connection: AsyncConnection,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    membership_id: UUID,
    intent: str,
    target_id: UUID,
    audit_event_id: UUID | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
    session_id: UUID | None = None,
) -> None:
    await connection.execute(
        BIND_COMMAND_SQL,
        {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "membership_id": membership_id,
            "intent": intent,
            "target_id": target_id,
            "audit_event_id": audit_event_id or uuid4(),
            "request_id": request_id or f"p4e-{uuid4().hex}",
            "trace_id": trace_id or uuid4().hex,
            "session_id": session_id or uuid4(),
        },
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
