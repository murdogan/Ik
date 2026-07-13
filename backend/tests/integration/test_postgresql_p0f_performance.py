from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.schemas.employee import (
    EmployeeListCursor,
    EmployeeListFilters,
    EmployeeListPagination,
)
from app.schemas.leave_request import (
    LeaveRequestListCursor,
    LeaveRequestListFilters,
    LeaveRequestListPagination,
)
from app.services.dashboard_service import _dashboard_counts_statement
from app.services.employee_service import _employee_list_statement
from app.services.leave_request_service import _leave_request_list_statement
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"
TENANT_ID = UUID("10000000-0000-4000-8000-000000000000")
OTHER_TENANT_ID = UUID("10000000-0000-4000-8000-000000000001")
USER_ID = UUID("20000000-0000-4000-8000-000000000000")
EMPLOYEE_COUNT = 10_000


@pytest.fixture
def p0f_migrated_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


def test_representative_10k_queries_capture_index_and_buffer_evidence(
    p0f_migrated_postgres_database: URL,
) -> None:
    evidence = asyncio.run(_capture_representative_plans(p0f_migrated_postgres_database))
    print(f"P0F_EXPLAIN_EVIDENCE={json.dumps(evidence, sort_keys=True)}")

    assert evidence["employee_count"] == EMPLOYEE_COUNT
    assert {
        "ix_employees_email_trgm",
        "ix_employees_employee_number_trgm",
    } <= set(evidence["search_indexes"])
    assert {
        "ix_employees_email_trgm",
        "ix_employees_employee_number_trgm",
    } <= set(evidence["employee_search"]["indexes"])
    assert (
        "ix_employees_tenant_directory_cursor"
        in evidence["employee_cursor"]["indexes"]
    )
    assert (
        "ix_leave_requests_tenant_created_cursor"
        in evidence["leave_request_cursor"]["indexes"]
    )
    assert evidence["employee_search"]["actual_rows"] == 1
    assert evidence["employee_cursor"]["actual_rows"] == 51
    assert evidence["leave_request_cursor"]["actual_rows"] == 51
    assert evidence["employee_cursor"]["rows_removed_by_filter"] <= 1
    assert evidence["leave_request_cursor"]["rows_removed_by_filter"] <= 1
    assert evidence["dashboard_counts"]["actual_rows"] == 1
    assert all(
        query_evidence["execution_time_ms"] >= 0
        and query_evidence["shared_hit_blocks"] >= 0
        for query_evidence in evidence.values()
        if isinstance(query_evidence, dict)
    )


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


async def _capture_representative_plans(database_url: URL) -> dict[str, object]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await _seed_representative_data(connection)

        async with engine.connect() as maintenance_connection:
            maintenance_connection = await maintenance_connection.execution_options(
                isolation_level="AUTOCOMMIT"
            )
            await maintenance_connection.execute(text("vacuum (analyze) employees"))
            await maintenance_connection.execute(text("vacuum (analyze) leave_requests"))

        async with engine.begin() as connection:
            employee_count = int(
                await connection.scalar(
                    text("select count(*) from employees where tenant_id = :tenant_id"),
                    {"tenant_id": TENANT_ID},
                )
                or 0
            )
            plans = {
                "employee_search": await _explain_statement(
                    connection,
                    _employee_list_statement(
                        TENANT_ID,
                        EmployeeListFilters(q="employee009999"),
                        EmployeeListPagination(limit=50),
                    ),
                ),
                "employee_cursor": await _explain_statement(
                    connection,
                    _employee_list_statement(
                        TENANT_ID,
                        EmployeeListFilters(),
                        EmployeeListPagination(
                            limit=50,
                            cursor=EmployeeListCursor(
                                id=UUID("10000000-0000-4000-8000-000000004999"),
                            ),
                        ),
                    ),
                ),
                "leave_request_cursor": await _explain_statement(
                    connection,
                    _leave_request_list_statement(
                        TENANT_ID,
                        LeaveRequestListFilters(),
                        LeaveRequestListPagination(
                            limit=50,
                            cursor=LeaveRequestListCursor(
                                created_at=datetime(2026, 6, 29, 6, 20, tzinfo=UTC),
                                start_date=date(2026, 10, 10),
                                id=UUID("30000000-0000-4000-8000-000000002500"),
                            ),
                        ),
                        dialect_name="postgresql",
                    ),
                ),
                "dashboard_counts": await _explain_statement(
                    connection,
                    _dashboard_counts_statement(
                        tenant_id=TENANT_ID,
                        start_date=date(2026, 7, 1),
                        end_date=date(2026, 8, 1),
                    ),
                ),
            }
            search_indexes = list(
                await connection.scalars(
                    text(
                        """
                        select indexname
                        from pg_indexes
                        where schemaname = current_schema()
                          and indexname in (
                            'ix_employees_employee_number_trgm',
                            'ix_employees_email_trgm'
                          )
                        order by indexname
                        """
                    )
                )
            )
    finally:
        await engine.dispose()

    return {
        "employee_count": employee_count,
        "search_indexes": search_indexes,
        **{name: _plan_evidence(plan) for name, plan in plans.items()},
    }


async def _seed_representative_data(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            """
            insert into tenants (
                id, slug, name, status, plan_code, data_region, locale, timezone
            ) values
            (
                :tenant_id, 'p0f-performance', 'P0F Performance', 'active', 'core',
                'tr-1', 'tr-TR', 'Europe/Istanbul'
            ),
            (
                :other_tenant_id, 'p0f-other', 'P0F Other', 'active', 'core',
                'tr-1', 'tr-TR', 'Europe/Istanbul'
            )
            """
        ),
        {"tenant_id": TENANT_ID, "other_tenant_id": OTHER_TENANT_ID},
    )
    await connection.execute(
        text(
            """
            insert into users (id, tenant_id, email, full_name, status)
            values (:user_id, :tenant_id, 'p0f@performance.test', 'P0F User', 'active')
            """
        ),
        {"user_id": USER_ID, "tenant_id": TENANT_ID},
    )
    # Interleaving archived even IDs makes the non-archived partial cursor index
    # observably preferable to the primary-key and tenant/id unique indexes.
    await connection.execute(
        text(
            """
            insert into employees (
                id, tenant_id, employee_number, first_name, last_name, email,
                department, position, status, employment_start_date,
                employment_end_date, archived_at, created_at, updated_at
            )
            select
                ('10000000-0000-4000-8000-' || lpad((gs * 2 - 1)::text, 12, '0'))::uuid,
                :tenant_id,
                'WF-' || lpad(gs::text, 6, '0'),
                'Employee' || gs,
                'Performance',
                'employee' || lpad(gs::text, 6, '0') || '@performance.test',
                (array['Engineering', 'People', 'Sales', 'Operations'])[1 + gs % 4],
                'Specialist',
                case
                    when gs % 20 = 0 then 'terminated'
                    when gs % 10 = 0 then 'on_leave'
                    else 'active'
                end,
                date '2024-01-01' + (gs % 700),
                case when gs % 20 = 0 then date '2026-06-30' else null end,
                case
                    when gs % 2 = 0 then timestamptz '2026-07-02 00:00:00+00'
                    else null
                end,
                timestamptz '2026-07-01 00:00:00+00'
                    + (gs - 5000) * interval '1 second',
                timestamptz '2026-07-01 00:00:00+00'
                    + (gs - 5000) * interval '1 second'
            from generate_series(1, :employee_count) as gs
            """
        ),
        {"tenant_id": TENANT_ID, "employee_count": EMPLOYEE_COUNT},
    )
    await connection.execute(
        text(
            """
            insert into employees (
                id, tenant_id, employee_number, first_name, last_name, email,
                department, position, status, employment_start_date,
                employment_end_date, created_at, updated_at
            )
            select
                ('10000000-0000-4000-8000-' || lpad((gs * 2)::text, 12, '0'))::uuid,
                :other_tenant_id,
                'OT-' || lpad(gs::text, 6, '0'),
                'OtherEmployee' || gs,
                'Performance',
                'other' || lpad(gs::text, 6, '0') || '@performance.test',
                'Other',
                'Specialist',
                'active',
                date '2024-01-01' + (gs % 700),
                null,
                timestamptz '2026-07-01 00:00:00+00' + gs * interval '1 second',
                timestamptz '2026-07-01 00:00:00+00' + gs * interval '1 second'
            from generate_series(1, :employee_count) as gs
            """
        ),
        {
            "other_tenant_id": OTHER_TENANT_ID,
            "employee_count": EMPLOYEE_COUNT,
        },
    )
    await connection.execute(
        text(
            """
            insert into leave_requests (
                id, tenant_id, employee_id, leave_type, start_date, end_date, status,
                requested_by_user_id, created_at, updated_at
            )
            select
                ('30000000-0000-4000-8000-' || lpad(gs::text, 12, '0'))::uuid,
                :tenant_id,
                ('10000000-0000-4000-8000-' || lpad((gs * 2 - 1)::text, 12, '0'))::uuid,
                case when gs % 5 = 0 then 'sick' else 'annual' end,
                date '2026-08-01' + (gs % 90),
                date '2026-08-03' + (gs % 90),
                case when gs % 4 = 0 then 'approved' else 'pending' end,
                :user_id,
                timestamptz '2026-07-01 00:00:00+00' - gs * interval '1 minute',
                timestamptz '2026-07-01 00:00:00+00' - gs * interval '1 minute'
            from generate_series(1, :leave_request_count) as gs
            """
        ),
        {
            "tenant_id": TENANT_ID,
            "user_id": USER_ID,
            "leave_request_count": EMPLOYEE_COUNT // 2,
        },
    )


async def _explain(
    connection: AsyncConnection,
    query: str,
    parameters: dict[str, object],
) -> dict[str, object]:
    payload = await connection.scalar(
        text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"),
        parameters,
    )
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert isinstance(payload, list) and len(payload) == 1
    return payload[0]


async def _explain_statement(
    connection: AsyncConnection,
    statement,
) -> dict[str, object]:
    compiled = statement.compile(
        dialect=connection.dialect,
        compile_kwargs={"literal_binds": True},
    )
    return await _explain(connection, str(compiled), {})


def _plan_evidence(explain: dict[str, object]) -> dict[str, object]:
    plan = explain["Plan"]
    assert isinstance(plan, dict)
    return {
        "actual_rows": int(plan["Actual Rows"]),
        "execution_time_ms": round(float(explain["Execution Time"]), 3),
        "indexes": sorted(_index_names(plan)),
        "planning_time_ms": round(float(explain["Planning Time"]), 3),
        "rows_removed_by_filter": _sum_plan_metric(plan, "Rows Removed by Filter"),
        "shared_hit_blocks": int(plan.get("Shared Hit Blocks", 0)),
        "shared_read_blocks": int(plan.get("Shared Read Blocks", 0)),
    }


def _index_names(plan: dict[str, object]) -> set[str]:
    names = set()
    index_name = plan.get("Index Name")
    if isinstance(index_name, str):
        names.add(index_name)
    for child in plan.get("Plans", []):
        if isinstance(child, dict):
            names.update(_index_names(child))
    return names


def _sum_plan_metric(plan: dict[str, object], metric: str) -> int:
    value = int(plan.get(metric, 0))
    return value + sum(
        _sum_plan_metric(child, metric)
        for child in plan.get("Plans", [])
        if isinstance(child, dict)
    )
