from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"
PRE_P0D_REVISION = "0008_employee_lifecycle_status_dates"
EXPAND_REVISION = "0009_expand_tenant_relational_integrity"
COMPOSITE_CONSTRAINTS = {
    "fk_leave_requests_tenant_employee_id_employees": (
        "FOREIGN KEY (tenant_id, employee_id) "
        "REFERENCES employees(tenant_id, id) ON DELETE CASCADE"
    ),
    "fk_leave_requests_tenant_requested_by_user_id_users": (
        "FOREIGN KEY (tenant_id, requested_by_user_id) "
        "REFERENCES users(tenant_id, id)"
    ),
    "fk_leave_requests_tenant_decided_by_user_id_users": (
        "FOREIGN KEY (tenant_id, decided_by_user_id) "
        "REFERENCES users(tenant_id, id)"
    ),
    "fk_leave_balance_summaries_tenant_employee_id_employees": (
        "FOREIGN KEY (tenant_id, employee_id) "
        "REFERENCES employees(tenant_id, id) ON DELETE CASCADE"
    ),
}
HEAD_COMPOSITE_CONSTRAINTS = {
    **COMPOSITE_CONSTRAINTS,
    "fk_leave_requests_tenant_employee_id_employees": (
        "FOREIGN KEY (tenant_id, employee_id) "
        "REFERENCES employees(tenant_id, id) ON DELETE RESTRICT"
    ),
    "fk_leave_balance_summaries_tenant_employee_id_employees": (
        "FOREIGN KEY (tenant_id, employee_id) "
        "REFERENCES employees(tenant_id, id) ON DELETE RESTRICT"
    ),
}
CANDIDATE_KEY_CONSTRAINTS = {
    "uq_employees_tenant_id_id": "UNIQUE (tenant_id, id)",
    "uq_users_tenant_id_id": "UNIQUE (tenant_id, id)",
}
LEGACY_TENANT_OWNED_CONSTRAINTS = {
    "leave_requests_employee_id_fkey": (
        "FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE"
    ),
    "leave_requests_requested_by_user_id_fkey": (
        "FOREIGN KEY (requested_by_user_id) REFERENCES users(id)"
    ),
    "leave_requests_decided_by_user_id_fkey": (
        "FOREIGN KEY (decided_by_user_id) REFERENCES users(id)"
    ),
    "leave_balance_summaries_employee_id_fkey": (
        "FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE"
    ),
}


@pytest.fixture
def p0d_postgres_database(postgres_database_url: URL) -> URL:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, "head")
    return postgres_database_url


def test_preflight_query_detects_cross_tenant_and_orphan_rows(
    p0d_postgres_database: URL,
) -> None:
    config = _alembic_config(p0d_postgres_database)
    alembic_command.downgrade(config, PRE_P0D_REVISION)
    valid_pending_request_id = asyncio.run(
        _seed_preflight_violations(p0d_postgres_database)
    )

    preflight_sql = _preflight_sql(config)
    violations = asyncio.run(
        _fetch_preflight_violations(p0d_postgres_database, preflight_sql)
    )
    violation_signatures = {
        (row["relationship_name"], row["violation_type"]) for row in violations
    }

    assert all(row["child_id"] != valid_pending_request_id for row in violations)
    assert len(violations) == 12
    assert violation_signatures == {
        ("users.tenant_id", "orphan"),
        ("employees.tenant_id", "orphan"),
        ("leave_requests.tenant_id", "orphan"),
        ("leave_balance_summaries.tenant_id", "orphan"),
        ("leave_requests.employee_id", "cross_tenant"),
        ("leave_requests.employee_id", "orphan"),
        ("leave_requests.requested_by_user_id", "cross_tenant"),
        ("leave_requests.requested_by_user_id", "orphan"),
        ("leave_requests.decided_by_user_id", "cross_tenant"),
        ("leave_requests.decided_by_user_id", "orphan"),
        ("leave_balance_summaries.employee_id", "cross_tenant"),
        ("leave_balance_summaries.employee_id", "orphan"),
    }

    with pytest.raises(RuntimeError, match="tenant relational integrity preflight failed"):
        alembic_command.upgrade(config, EXPAND_REVISION)

    assert asyncio.run(_current_revision(p0d_postgres_database)) == PRE_P0D_REVISION


def test_expand_contract_round_trip_preserves_valid_data_and_constraint_state(
    p0d_postgres_database: URL,
) -> None:
    config = _alembic_config(p0d_postgres_database)
    alembic_command.downgrade(config, PRE_P0D_REVISION)
    fixture_ids = asyncio.run(_seed_valid_relationships(p0d_postgres_database))
    fixture_snapshot = asyncio.run(
        _relationship_snapshot(p0d_postgres_database, fixture_ids)
    )

    alembic_command.upgrade(config, EXPAND_REVISION)

    expanded_constraints = asyncio.run(
        _named_constraint_definitions(p0d_postgres_database)
    )
    assert {
        name: expanded_constraints[name] for name in COMPOSITE_CONSTRAINTS
    } == {
        name: f"{definition} NOT VALID"
        for name, definition in COMPOSITE_CONSTRAINTS.items()
    }
    assert {
        name: expanded_constraints[name] for name in CANDIDATE_KEY_CONSTRAINTS
    } == CANDIDATE_KEY_CONSTRAINTS
    assert LEGACY_TENANT_OWNED_CONSTRAINTS.keys() <= expanded_constraints.keys()
    expanded_validation = asyncio.run(
        _constraint_validation_state(
            p0d_postgres_database,
            set(COMPOSITE_CONSTRAINTS) | set(CANDIDATE_KEY_CONSTRAINTS),
        )
    )
    assert expanded_validation == {
        **{name: False for name in COMPOSITE_CONSTRAINTS},
        **{name: True for name in CANDIDATE_KEY_CONSTRAINTS},
    }
    expanded_parent_ids = asyncio.run(
        _seed_two_tenant_parents(p0d_postgres_database)
    )
    asyncio.run(
        _assert_cross_tenant_writes_rejected(
            p0d_postgres_database,
            expanded_parent_ids,
        )
    )

    alembic_command.upgrade(config, "head")

    assert asyncio.run(
        _relationship_snapshot(p0d_postgres_database, fixture_ids)
    ) == fixture_snapshot
    head_constraints = asyncio.run(_named_constraint_definitions(p0d_postgres_database))
    assert {
        name: head_constraints[name] for name in HEAD_COMPOSITE_CONSTRAINTS
    } == HEAD_COMPOSITE_CONSTRAINTS
    assert {
        name: head_constraints[name] for name in CANDIDATE_KEY_CONSTRAINTS
    } == CANDIDATE_KEY_CONSTRAINTS
    assert LEGACY_TENANT_OWNED_CONSTRAINTS.keys().isdisjoint(head_constraints)
    assert asyncio.run(
        _constraint_validation_state(
            p0d_postgres_database,
            set(COMPOSITE_CONSTRAINTS) | set(CANDIDATE_KEY_CONSTRAINTS),
        )
    ) == {
        name: True
        for name in set(COMPOSITE_CONSTRAINTS) | set(CANDIDATE_KEY_CONSTRAINTS)
    }

    alembic_command.downgrade(config, PRE_P0D_REVISION)

    assert asyncio.run(
        _relationship_snapshot(p0d_postgres_database, fixture_ids)
    ) == fixture_snapshot
    downgraded_constraints = asyncio.run(
        _named_constraint_definitions(p0d_postgres_database)
    )
    assert {
        name: downgraded_constraints[name]
        for name in LEGACY_TENANT_OWNED_CONSTRAINTS
    } == LEGACY_TENANT_OWNED_CONSTRAINTS
    assert asyncio.run(
        _constraint_validation_state(
            p0d_postgres_database,
            set(LEGACY_TENANT_OWNED_CONSTRAINTS),
        )
    ) == {name: True for name in LEGACY_TENANT_OWNED_CONSTRAINTS}
    assert set(COMPOSITE_CONSTRAINTS).isdisjoint(downgraded_constraints)
    assert set(CANDIDATE_KEY_CONSTRAINTS).isdisjoint(downgraded_constraints)

    alembic_command.upgrade(config, "head")
    assert asyncio.run(
        _relationship_snapshot(p0d_postgres_database, fixture_ids)
    ) == fixture_snapshot


def test_postgresql_direct_writes_reject_every_cross_tenant_relationship(
    p0d_postgres_database: URL,
) -> None:
    parent_ids = asyncio.run(_seed_two_tenant_parents(p0d_postgres_database))

    asyncio.run(_assert_cross_tenant_writes_rejected(p0d_postgres_database, parent_ids))


def test_expand_reuses_candidate_index_left_by_an_interrupted_attempt(
    p0d_postgres_database: URL,
) -> None:
    config = _alembic_config(p0d_postgres_database)
    alembic_command.downgrade(config, PRE_P0D_REVISION)
    candidate_index_oid = asyncio.run(
        _create_interrupted_attempt_index(p0d_postgres_database)
    )

    alembic_command.upgrade(config, EXPAND_REVISION)

    expanded_constraints = asyncio.run(
        _named_constraint_definitions(p0d_postgres_database)
    )
    assert {
        name: expanded_constraints[name] for name in CANDIDATE_KEY_CONSTRAINTS
    } == CANDIDATE_KEY_CONSTRAINTS
    assert asyncio.run(
        _index_oid(p0d_postgres_database, "uq_employees_tenant_id_id")
    ) == candidate_index_oid
    assert asyncio.run(_current_revision(p0d_postgres_database)) == EXPAND_REVISION

    alembic_command.upgrade(config, "head")


def test_contract_validation_failure_keeps_committed_expanded_revision(
    p0d_postgres_database: URL,
) -> None:
    config = _alembic_config(p0d_postgres_database)
    alembic_command.downgrade(config, "base")
    alembic_command.upgrade(config, EXPAND_REVISION)
    parent_ids = asyncio.run(_seed_two_tenant_parents(p0d_postgres_database))
    asyncio.run(
        _inject_existing_invalid_balance(p0d_postgres_database, parent_ids)
    )

    with pytest.raises(IntegrityError) as error:
        alembic_command.upgrade(config, "head")

    assert "fk_leave_balance_summaries_tenant_employee_id_employees" in str(
        error.value
    )
    assert asyncio.run(_current_revision(p0d_postgres_database)) == EXPAND_REVISION
    constraint_definitions = asyncio.run(
        _named_constraint_definitions(p0d_postgres_database)
    )
    assert LEGACY_TENANT_OWNED_CONSTRAINTS.keys() <= constraint_definitions.keys()
    assert set(COMPOSITE_CONSTRAINTS) <= constraint_definitions.keys()
    assert asyncio.run(
        _constraint_validation_state(
            p0d_postgres_database,
            set(COMPOSITE_CONSTRAINTS),
        )
    ) == {name: False for name in COMPOSITE_CONSTRAINTS}


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


def _preflight_sql(config: Config) -> str:
    revision = ScriptDirectory.from_config(config).get_revision(EXPAND_REVISION)
    assert revision is not None
    return str(revision.module.TENANT_RELATIONSHIP_PREFLIGHT_SQL)


async def _current_revision(database_url: URL) -> str | None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: MigrationContext.configure(
                    sync_connection
                ).get_current_revision()
            )
    finally:
        await engine.dispose()


async def _seed_preflight_violations(database_url: URL) -> UUID:
    engine = create_async_engine(database_url, poolclass=NullPool)
    tenant_a_id = uuid4()
    tenant_b_id = uuid4()
    employee_a_id = uuid4()
    employee_b_id = uuid4()
    user_a_id = uuid4()
    user_b_id = uuid4()
    valid_pending_request_id = uuid4()
    try:
        async with engine.begin() as connection:
            await _insert_tenant(connection, tenant_a_id, "preflight-a")
            await _insert_tenant(connection, tenant_b_id, "preflight-b")
            await _insert_employee(connection, employee_a_id, tenant_a_id, "PRE-A")
            await _insert_employee(connection, employee_b_id, tenant_b_id, "PRE-B")
            await _insert_user(connection, user_a_id, tenant_a_id, "preflight-a")
            await _insert_user(connection, user_b_id, tenant_b_id, "preflight-b")

            valid_pending_parameters = _leave_request_parameters(
                tenant_id=tenant_a_id,
                employee_id=employee_a_id,
                requested_by_user_id=user_a_id,
            )
            valid_pending_parameters["id"] = valid_pending_request_id
            await connection.execute(
                text(_leave_request_insert_sql()),
                valid_pending_parameters,
            )

            # The pre-P0D scalar foreign keys allow all four cross-tenant links.
            await connection.execute(
                text(
                    """
                    insert into leave_requests (
                        id, tenant_id, employee_id, leave_type, start_date, end_date,
                        status, requested_by_user_id, decided_by_user_id
                    ) values (
                        :id, :tenant_id, :employee_id, 'annual', :start_date, :end_date,
                        'approved', :requested_by_user_id, :decided_by_user_id
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "tenant_id": tenant_a_id,
                    "employee_id": employee_b_id,
                    "start_date": date(2026, 7, 20),
                    "end_date": date(2026, 7, 21),
                    "requested_by_user_id": user_b_id,
                    "decided_by_user_id": user_b_id,
                },
            )
            await connection.execute(
                text(
                    """
                    insert into leave_balance_summaries (
                        id, tenant_id, employee_id, leave_type, period_year,
                        opening_balance_days, used_days, planned_days
                    ) values (
                        :id, :tenant_id, :employee_id, 'annual', 2026, 14, 1, 2
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "tenant_id": tenant_a_id,
                    "employee_id": employee_b_id,
                },
            )

            # Remove the old guards deliberately so every orphan branch in the
            # preflight can be characterized. A normal 0008 database prevents
            # these rows, but an import/maintenance-damaged database may not.
            for table_name, constraint_name in (
                ("users", "users_tenant_id_fkey"),
                ("employees", "employees_tenant_id_fkey"),
                ("leave_requests", "leave_requests_tenant_id_fkey"),
                (
                    "leave_balance_summaries",
                    "leave_balance_summaries_tenant_id_fkey",
                ),
                ("leave_requests", "leave_requests_employee_id_fkey"),
                ("leave_requests", "leave_requests_requested_by_user_id_fkey"),
                ("leave_requests", "leave_requests_decided_by_user_id_fkey"),
                (
                    "leave_balance_summaries",
                    "leave_balance_summaries_employee_id_fkey",
                ),
            ):
                await connection.exec_driver_sql(
                    f'alter table "{table_name}" drop constraint "{constraint_name}"'
                )

            orphan_tenant_id = uuid4()
            orphan_tenant_employee_id = uuid4()
            orphan_tenant_user_id = uuid4()
            await _insert_employee(
                connection,
                orphan_tenant_employee_id,
                orphan_tenant_id,
                "ORPHAN-TENANT",
            )
            await _insert_user(
                connection,
                orphan_tenant_user_id,
                orphan_tenant_id,
                "orphan-tenant",
            )
            await connection.execute(
                text(_leave_request_insert_sql()),
                _leave_request_parameters(
                    tenant_id=orphan_tenant_id,
                    employee_id=orphan_tenant_employee_id,
                    requested_by_user_id=orphan_tenant_user_id,
                ),
            )
            await connection.execute(
                text(
                    """
                    insert into leave_balance_summaries (
                        id, tenant_id, employee_id, leave_type, period_year,
                        opening_balance_days, used_days, planned_days
                    ) values (
                        :id, :tenant_id, :employee_id, 'annual', 2026, 5, 0, 0
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "tenant_id": orphan_tenant_id,
                    "employee_id": orphan_tenant_employee_id,
                },
            )

            await connection.execute(
                text(_leave_request_insert_sql()),
                _leave_request_parameters(
                    tenant_id=tenant_a_id,
                    employee_id=uuid4(),
                    requested_by_user_id=user_a_id,
                ),
            )
            await connection.execute(
                text(_leave_request_insert_sql()),
                _leave_request_parameters(
                    tenant_id=tenant_a_id,
                    employee_id=employee_a_id,
                    requested_by_user_id=uuid4(),
                ),
            )
            await connection.execute(
                text(_leave_request_insert_sql()),
                _leave_request_parameters(
                    tenant_id=tenant_a_id,
                    employee_id=employee_a_id,
                    requested_by_user_id=user_a_id,
                    decided_by_user_id=uuid4(),
                ),
            )
            await connection.execute(
                text(
                    """
                    insert into leave_balance_summaries (
                        id, tenant_id, employee_id, leave_type, period_year,
                        opening_balance_days, used_days, planned_days
                    ) values (
                        :id, :tenant_id, :employee_id, 'medical', 2026, 5, 0, 0
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "tenant_id": tenant_a_id,
                    "employee_id": uuid4(),
                },
            )
    finally:
        await engine.dispose()
    return valid_pending_request_id


async def _create_interrupted_attempt_index(database_url: URL) -> int:
    engine = create_async_engine(
        database_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.exec_driver_sql(
                "create unique index concurrently uq_employees_tenant_id_id "
                "on employees (tenant_id, id)"
            )
            index_oid = await connection.scalar(
                text("select 'uq_employees_tenant_id_id'::regclass::oid")
            )
            assert index_oid is not None
            return int(index_oid)
    finally:
        await engine.dispose()


async def _index_oid(database_url: URL, index_name: str) -> int:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            index_oid = await connection.scalar(
                text(
                    """
                    select index_relation.oid
                    from pg_class as index_relation
                    join pg_namespace as index_namespace
                      on index_namespace.oid = index_relation.relnamespace
                    where index_namespace.nspname = current_schema()
                      and index_relation.relname = :index_name
                    """
                ),
                {"index_name": index_name},
            )
            assert index_oid is not None
            return int(index_oid)
    finally:
        await engine.dispose()


async def _inject_existing_invalid_balance(
    database_url: URL,
    ids: dict[str, UUID],
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(
                "alter table leave_balance_summaries drop constraint "
                "fk_leave_balance_summaries_tenant_employee_id_employees"
            )
            await connection.execute(
                text(
                    """
                    insert into leave_balance_summaries (
                        id, tenant_id, employee_id, leave_type, period_year,
                        opening_balance_days, used_days, planned_days
                    ) values (
                        :id, :tenant_id, :employee_id, 'annual', 2026, 14, 0, 0
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "tenant_id": ids["tenant_a"],
                    "employee_id": ids["employee_b"],
                },
            )
            await connection.exec_driver_sql(
                "alter table leave_balance_summaries add constraint "
                "fk_leave_balance_summaries_tenant_employee_id_employees "
                "foreign key (tenant_id, employee_id) "
                "references employees (tenant_id, id) on delete cascade not valid"
            )
    finally:
        await engine.dispose()


async def _fetch_preflight_violations(
    database_url: URL,
    preflight_sql: str,
) -> list[dict[str, object]]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            rows = (await connection.execute(text(preflight_sql))).mappings()
            return [dict(row) for row in rows]
    finally:
        await engine.dispose()


async def _seed_valid_relationships(database_url: URL) -> tuple[UUID, UUID]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    tenant_id = uuid4()
    employee_id = uuid4()
    user_id = uuid4()
    leave_request_id = uuid4()
    leave_balance_id = uuid4()
    try:
        async with engine.begin() as connection:
            await _insert_tenant(connection, tenant_id, "round-trip")
            await _insert_employee(connection, employee_id, tenant_id, "ROUND-TRIP")
            await _insert_user(connection, user_id, tenant_id, "round-trip")
            await connection.execute(
                text(
                    """
                    insert into leave_requests (
                        id, tenant_id, employee_id, leave_type, start_date, end_date,
                        status, requested_by_user_id, decided_by_user_id
                    ) values (
                        :id, :tenant_id, :employee_id, 'annual', :start_date, :end_date,
                        'approved', :user_id, :user_id
                    )
                    """
                ),
                {
                    "id": leave_request_id,
                    "tenant_id": tenant_id,
                    "employee_id": employee_id,
                    "start_date": date(2026, 8, 3),
                    "end_date": date(2026, 8, 4),
                    "user_id": user_id,
                },
            )
            await connection.execute(
                text(
                    """
                    insert into leave_balance_summaries (
                        id, tenant_id, employee_id, leave_type, period_year,
                        opening_balance_days, used_days, planned_days
                    ) values (
                        :id, :tenant_id, :employee_id, 'annual', 2026, 14, 1, 2
                    )
                    """
                ),
                {
                    "id": leave_balance_id,
                    "tenant_id": tenant_id,
                    "employee_id": employee_id,
                },
            )
    finally:
        await engine.dispose()
    return leave_request_id, leave_balance_id


async def _relationship_snapshot(
    database_url: URL,
    fixture_ids: tuple[UUID, UUID],
) -> tuple[dict[str, object], dict[str, object]]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    leave_request_id, leave_balance_id = fixture_ids
    try:
        async with engine.connect() as connection:
            leave_request = (
                await connection.execute(
                    text(
                        """
                        select
                            id, tenant_id, employee_id, leave_type, start_date, end_date,
                            status, requested_by_user_id, decided_by_user_id, decision_note
                        from leave_requests
                        where id = :id
                        """
                    ),
                    {"id": leave_request_id},
                )
            ).mappings().one()
            leave_balance = (
                await connection.execute(
                    text(
                        """
                        select
                            id, tenant_id, employee_id, leave_type, period_year,
                            opening_balance_days, used_days, planned_days
                        from leave_balance_summaries
                        where id = :id
                        """
                    ),
                    {"id": leave_balance_id},
                )
            ).mappings().one()
            return dict(leave_request), dict(leave_balance)
    finally:
        await engine.dispose()


async def _named_constraint_definitions(database_url: URL) -> dict[str, str]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    """
                    select conname, pg_get_constraintdef(oid) as definition
                    from pg_constraint
                    where connamespace = current_schema()::regnamespace
                    """
                )
            )
            return {str(row.conname): str(row.definition) for row in rows}
    finally:
        await engine.dispose()


async def _constraint_validation_state(
    database_url: URL,
    constraint_names: set[str],
) -> dict[str, bool]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    """
                    select conname, convalidated
                    from pg_constraint
                    where connamespace = current_schema()::regnamespace
                      and conname = any(:constraint_names)
                    """
                ),
                {"constraint_names": sorted(constraint_names)},
            )
            return {str(row.conname): bool(row.convalidated) for row in rows}
    finally:
        await engine.dispose()


async def _seed_two_tenant_parents(database_url: URL) -> dict[str, UUID]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    ids = {
        "tenant_a": uuid4(),
        "tenant_b": uuid4(),
        "employee_a": uuid4(),
        "employee_b": uuid4(),
        "user_a": uuid4(),
        "user_b": uuid4(),
    }
    try:
        async with engine.begin() as connection:
            await _insert_tenant(connection, ids["tenant_a"], "direct-a")
            await _insert_tenant(connection, ids["tenant_b"], "direct-b")
            await _insert_employee(
                connection, ids["employee_a"], ids["tenant_a"], "DIRECT-A"
            )
            await _insert_employee(
                connection, ids["employee_b"], ids["tenant_b"], "DIRECT-B"
            )
            await _insert_user(connection, ids["user_a"], ids["tenant_a"], "direct-a")
            await _insert_user(connection, ids["user_b"], ids["tenant_b"], "direct-b")
    finally:
        await engine.dispose()
    return ids


async def _assert_cross_tenant_writes_rejected(
    database_url: URL,
    ids: dict[str, UUID],
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        await _expect_constraint_error(
            engine,
            _leave_request_insert_sql(),
            _leave_request_parameters(
                tenant_id=ids["tenant_a"],
                employee_id=ids["employee_b"],
                requested_by_user_id=ids["user_a"],
            ),
            "fk_leave_requests_tenant_employee_id_employees",
        )
        await _expect_constraint_error(
            engine,
            _leave_request_insert_sql(),
            _leave_request_parameters(
                tenant_id=ids["tenant_a"],
                employee_id=ids["employee_a"],
                requested_by_user_id=ids["user_b"],
            ),
            "fk_leave_requests_tenant_requested_by_user_id_users",
        )
        await _expect_constraint_error(
            engine,
            _leave_request_insert_sql(),
            _leave_request_parameters(
                tenant_id=ids["tenant_a"],
                employee_id=ids["employee_a"],
                requested_by_user_id=ids["user_a"],
                decided_by_user_id=ids["user_b"],
            ),
            "fk_leave_requests_tenant_decided_by_user_id_users",
        )
        await _expect_constraint_error(
            engine,
            """
            insert into leave_balance_summaries (
                id, tenant_id, employee_id, leave_type, period_year,
                opening_balance_days, used_days, planned_days
            ) values (:id, :tenant_id, :employee_id, 'annual', 2026, 14, 0, 0)
            """,
            {
                "id": uuid4(),
                "tenant_id": ids["tenant_a"],
                "employee_id": ids["employee_b"],
            },
            "fk_leave_balance_summaries_tenant_employee_id_employees",
        )

        async with engine.begin() as connection:
            await connection.execute(
                text(_leave_request_insert_sql()),
                _leave_request_parameters(
                    tenant_id=ids["tenant_a"],
                    employee_id=ids["employee_a"],
                    requested_by_user_id=ids["user_a"],
                ),
            )
    finally:
        await engine.dispose()


async def _expect_constraint_error(
    engine,
    sql: str,
    parameters: dict[str, object],
    constraint_name: str,
) -> None:
    with pytest.raises(IntegrityError) as error:
        async with engine.begin() as connection:
            await connection.execute(text(sql), parameters)

    assert error.value.orig.sqlstate == "23503"
    assert constraint_name in str(error.value)


def _leave_request_insert_sql() -> str:
    return """
        insert into leave_requests (
            id, tenant_id, employee_id, leave_type, start_date, end_date,
            status, requested_by_user_id, decided_by_user_id
        ) values (
            :id, :tenant_id, :employee_id, 'annual', :start_date, :end_date,
            'pending', :requested_by_user_id, :decided_by_user_id
        )
    """


def _leave_request_parameters(
    *,
    tenant_id: UUID,
    employee_id: UUID,
    requested_by_user_id: UUID,
    decided_by_user_id: UUID | None = None,
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "employee_id": employee_id,
        "start_date": date(2026, 9, 1),
        "end_date": date(2026, 9, 2),
        "requested_by_user_id": requested_by_user_id,
        "decided_by_user_id": decided_by_user_id,
    }


async def _insert_tenant(connection, tenant_id: UUID, slug_prefix: str) -> None:
    await connection.execute(
        text(
            """
            insert into tenants (
                id, slug, name, status, plan_code, data_region, locale, timezone
            ) values (
                :id, :slug, 'P0D tenant', 'active', 'core', 'tr-1',
                'tr-TR', 'Europe/Istanbul'
            )
            """
        ),
        {"id": tenant_id, "slug": f"{slug_prefix}-{uuid4().hex}"},
    )


async def _insert_employee(
    connection,
    employee_id: UUID,
    tenant_id: UUID,
    employee_number: str,
) -> None:
    await connection.execute(
        text(
            """
            insert into employees (
                id, tenant_id, employee_number, first_name, last_name,
                status, employment_start_date
            ) values (
                :id, :tenant_id, :employee_number, 'P0D', 'Employee',
                'active', :employment_start_date
            )
            """
        ),
        {
            "id": employee_id,
            "tenant_id": tenant_id,
            "employee_number": employee_number,
            "employment_start_date": date(2026, 1, 1),
        },
    )


async def _insert_user(
    connection,
    user_id: UUID,
    tenant_id: UUID,
    email_prefix: str,
) -> None:
    await connection.execute(
        text(
            """
            insert into users (id, tenant_id, email, full_name, status)
            values (:id, :tenant_id, :email, 'P0D User', 'active')
            """
        ),
        {
            "id": user_id,
            "tenant_id": tenant_id,
            "email": f"{email_prefix}-{uuid4().hex}@example.test",
        },
    )
