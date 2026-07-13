from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_assignment import EmployeeAssignment
from app.platform.db.tenant_access import TENANT_APPLICATION_ROLE
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.tenancy import TenantContext
from app.schemas.employee_assignment import (
    TeamListCursor,
    TeamListPagination,
)
from app.services.employee_assignment_service import (
    EMPLOYEE_TEAM_READ_PERMISSION,
    EmployeeAssignmentService,
    _assignment_view_statement,
    _effective_on,
)
from sqlalchemy import event, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"
P3H_REVISION = "0029_p3h_position_catalog"
P3I_REVISION = "0030_p3i_employee_assignments"

BACKFILL_TENANT_ID = UUID("ca000000-0000-4000-8000-000000000001")
BACKFILL_LEGAL_ENTITY_ID = UUID("ca010000-0000-4000-8000-000000000001")
EXISTING_DEPARTMENT_ID = UUID("ca020000-0000-4000-8000-000000000001")
EXISTING_POSITION_ID = UUID("ca030000-0000-4000-8000-000000000001")
BACKFILL_EMPLOYEE_IDS = (
    UUID("ca040000-0000-4000-8000-000000000001"),
    UUID("ca040000-0000-4000-8000-000000000002"),
    UUID("ca040000-0000-4000-8000-000000000003"),
    UUID("ca040000-0000-4000-8000-000000000004"),
)

TEAM_TENANT_A_ID = UUID("cb000000-0000-4000-8000-000000000001")
TEAM_TENANT_B_ID = UUID("cb000000-0000-4000-8000-000000000002")
TEAM_LEGAL_ENTITY_A_ID = UUID("cb010000-0000-4000-8000-000000000001")
TEAM_LEGAL_ENTITY_B_ID = UUID("cb010000-0000-4000-8000-000000000002")
TEAM_BRANCH_A_ID = UUID("cb020000-0000-4000-8000-000000000001")
TEAM_BRANCH_B_ID = UUID("cb020000-0000-4000-8000-000000000002")
TEAM_ROOT_DEPARTMENT_A_ID = UUID("cb030000-0000-4000-8000-000000000001")
TEAM_CHILD_DEPARTMENT_A_ID = UUID("cb030000-0000-4000-8000-000000000002")
TEAM_DEPARTMENT_B_ID = UUID("cb030000-0000-4000-8000-000000000003")
TEAM_POSITION_A_ID = UUID("cb040000-0000-4000-8000-000000000001")
TEAM_POSITION_B_ID = UUID("cb040000-0000-4000-8000-000000000002")
MANAGER_A_ID = UUID("cb050000-0000-4000-8000-000000000001")
MANAGER_B_ID = UUID("cb050000-0000-4000-8000-000000000002")
MANAGER_TENANT_B_ID = UUID("cb050000-0000-4000-8000-000000000003")
MANAGER_B_EMPLOYEE_ID = UUID("cb060000-0000-4000-8000-000000000001")
MANAGER_B_ASSIGNMENT_ID = UUID("cb070000-0000-4000-8000-000000000001")

TODAY = date(2026, 7, 13)
DIRECT_REPORT_COUNT = 80
INDIRECT_REPORT_COUNT = 1_500
CROSS_TENANT_REPORT_COUNT = 900
TEAM_PAGE_LIMIT = 25


def test_populated_p3i_postgresql_backfill_reuses_and_preserves_legacy_data(
    postgres_database_url: URL,
) -> None:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, P3H_REVISION)
    asyncio.run(_seed_populated_p3h_database(postgres_database_url))

    alembic_command.upgrade(config, "head")

    script = ScriptDirectory.from_config(config)
    assert script.get_revision(P3I_REVISION) is not None
    heads = script.get_heads()
    assert len(heads) == 1
    report = asyncio.run(_read_backfill_report(postgres_database_url))

    assert report["revision"] == heads[0]
    assignments = report["assignments"]
    assert isinstance(assignments, list)
    assert len(assignments) == len(BACKFILL_EMPLOYEE_IDS)

    expected_intervals = {
        "P3K-001": (date(2025, 1, 1), None),
        "P3K-002": (date(2025, 2, 1), None),
        "P3K-003": (date(2025, 3, 1), date(2026, 7, 1)),
        "P3K-004": (date(2025, 4, 1), None),
    }
    assert {
        row["employee_number"]: (row["effective_from"], row["effective_to"]) for row in assignments
    } == expected_intervals
    assert {
        row["employee_number"]: (row["legacy_department"], row["legacy_position"])
        for row in assignments
    } == {
        "P3K-001": (" Engineering ", " Developer "),
        "P3K-002": ("", "  "),
        "P3K-003": ("ENGINEERING", "developer"),
        "P3K-004": (" People ", "Partner"),
    }

    assignments_by_number = {row["employee_number"]: row for row in assignments}
    for employee_number in ("P3K-001", "P3K-003"):
        assert assignments_by_number[employee_number]["department_id"] == (EXISTING_DEPARTMENT_ID)
        assert assignments_by_number[employee_number]["position_id"] == (EXISTING_POSITION_ID)

    unspecified_department_id = _deterministic_uuid(
        f"p3i:department:{BACKFILL_TENANT_ID}:unspecified"
    )
    unspecified_position_id = _deterministic_uuid(f"p3i:position:{BACKFILL_TENANT_ID}:unspecified")
    people_department_id = _deterministic_uuid(f"p3i:department:{BACKFILL_TENANT_ID}:people")
    partner_position_id = _deterministic_uuid(f"p3i:position:{BACKFILL_TENANT_ID}:partner")
    assert assignments_by_number["P3K-002"]["department_id"] == (unspecified_department_id)
    assert assignments_by_number["P3K-002"]["position_id"] == unspecified_position_id
    assert assignments_by_number["P3K-004"]["department_id"] == people_department_id
    assert assignments_by_number["P3K-004"]["position_id"] == partner_position_id

    for row in assignments:
        assert row["assignment_id"] == _deterministic_uuid(
            f"p3i:assignment:{BACKFILL_TENANT_ID}:{row['employee_id']}"
        )
        assert row["legal_entity_id"] == BACKFILL_LEGAL_ENTITY_ID
        assert row["change_reason"] == "P3I legacy employee backfill"

    assert report["legacy_branch"] == {
        "id": _deterministic_uuid(f"p3i:branch:{BACKFILL_TENANT_ID}"),
        "code": "LEGACY",
        "name": "Legacy / Unspecified",
        "status": "active",
        "legal_entity_id": BACKFILL_LEGAL_ENTITY_ID,
    }
    assert report["legacy_branch_count"] == 1
    assert report["department_catalog"] == [
        (EXISTING_DEPARTMENT_ID, "Engineering"),
        (people_department_id, "People"),
        (unspecified_department_id, "Unspecified"),
    ]
    assert report["position_catalog"] == [
        (EXISTING_POSITION_ID, "Developer"),
        (partner_position_id, "Partner"),
        (unspecified_position_id, "Unspecified"),
    ]


@pytest.fixture
def p3k_manager_postgres_database(postgres_database_url: URL) -> URL:
    # The function-scoped database fixture keeps this migration lane isolated and sequential.
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


def test_manager_team_scope_cursor_budget_and_postgresql_index_evidence(
    p3k_manager_postgres_database: URL,
) -> None:
    evidence = asyncio.run(_assert_manager_team_gate(p3k_manager_postgres_database))
    print(f"P3K_MANAGER_QUERY_EVIDENCE={json.dumps(evidence, sort_keys=True)}")

    assert evidence["direct_reports"] == DIRECT_REPORT_COUNT + 1
    assert evidence["pages"] == 4
    assert evidence["selects_per_page"] == [3, 3, 3, 3]
    assert evidence["statements_per_page"] == [5, 5, 5, 5]
    assert evidence["indexes"] == ["ix_employee_assignments_tenant_manager_scope"]
    assert evidence["explain_actual_rows"] == TEAM_PAGE_LIMIT + 1
    assert evidence["execution_time_ms"] >= 0


async def _seed_populated_p3h_database(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone"
                    ") values ("
                    ":tenant_id, 'p3k-backfill', 'P3K Backfill', 'active', "
                    "'core', 'tr-1', 'en-US', 'UTC'"
                    ")"
                ),
                {"tenant_id": BACKFILL_TENANT_ID},
            )
            await connection.execute(
                text(
                    "insert into legal_entities ("
                    "id, tenant_id, code, name, registered_name, timezone, status, "
                    "is_default"
                    ") values ("
                    ":id, :tenant_id, 'DEFAULT', 'P3K Backfill', 'P3K Backfill', "
                    "'UTC', 'active', true"
                    ")"
                ),
                {
                    "id": BACKFILL_LEGAL_ENTITY_ID,
                    "tenant_id": BACKFILL_TENANT_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into departments (id, tenant_id, code, name, status) "
                    "values (:id, :tenant_id, 'ENG', 'Engineering', 'active')"
                ),
                {
                    "id": EXISTING_DEPARTMENT_ID,
                    "tenant_id": BACKFILL_TENANT_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into positions (id, tenant_id, code, title, status) "
                    "values (:id, :tenant_id, 'DEV', 'Developer', 'active')"
                ),
                {
                    "id": EXISTING_POSITION_ID,
                    "tenant_id": BACKFILL_TENANT_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into employees ("
                    "id, tenant_id, employee_number, first_name, last_name, department, "
                    "position, status, employment_start_date, employment_end_date, archived_at"
                    ") values "
                    "(:active_id, :tenant_id, 'P3K-001', 'Ada', 'Active', "
                    "' Engineering ', ' Developer ', 'active', DATE '2025-01-01', null, null), "
                    "(:leave_id, :tenant_id, 'P3K-002', 'Bora', 'Leave', "
                    "'', '  ', 'on_leave', DATE '2025-02-01', null, null), "
                    "(:terminated_id, :tenant_id, 'P3K-003', 'Cem', 'Terminated', "
                    "'ENGINEERING', 'developer', 'terminated', DATE '2025-03-01', "
                    "DATE '2026-06-30', null), "
                    "(:archived_id, :tenant_id, 'P3K-004', 'Derya', 'Archived', "
                    "' People ', 'Partner', 'active', DATE '2025-04-01', null, "
                    "CURRENT_TIMESTAMP)"
                ),
                {
                    "tenant_id": BACKFILL_TENANT_ID,
                    "active_id": BACKFILL_EMPLOYEE_IDS[0],
                    "leave_id": BACKFILL_EMPLOYEE_IDS[1],
                    "terminated_id": BACKFILL_EMPLOYEE_IDS[2],
                    "archived_id": BACKFILL_EMPLOYEE_IDS[3],
                },
            )
    finally:
        await engine.dispose()


async def _read_backfill_report(database_url: URL) -> dict[str, object]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            revision = await connection.scalar(text("select version_num from alembic_version"))
            await _set_local_tenant_role(connection, BACKFILL_TENANT_ID)
            assignment_rows = (
                (
                    await connection.execute(
                        text(
                            "select assignment.id as assignment_id, assignment.employee_id, "
                            "employee.employee_number, employee.department as legacy_department, "
                            "employee.position as legacy_position, assignment.legal_entity_id, "
                            "assignment.department_id, assignment.position_id, "
                            "assignment.effective_from, assignment.effective_to, "
                            "assignment.change_reason "
                            "from employee_assignments as assignment "
                            "join employees as employee "
                            "on employee.tenant_id = assignment.tenant_id "
                            "and employee.id = assignment.employee_id "
                            "order by employee.employee_number"
                        )
                    )
                )
                .mappings()
                .all()
            )
            branch_rows = (
                (
                    await connection.execute(
                        text(
                            "select id, code, name, status, legal_entity_id "
                            "from branches where code_normalized = 'legacy' "
                            "and status = 'active' and archived_at is null order by id"
                        )
                    )
                )
                .mappings()
                .all()
            )
            department_catalog = (
                await connection.execute(text("select id, name from departments order by name, id"))
            ).all()
            position_catalog = (
                await connection.execute(text("select id, title from positions order by title, id"))
            ).all()
    finally:
        await engine.dispose()

    assert len(branch_rows) == 1
    return {
        "revision": revision,
        "assignments": [dict(row) for row in assignment_rows],
        "legacy_branch": dict(branch_rows[0]),
        "legacy_branch_count": len(branch_rows),
        "department_catalog": department_catalog,
        "position_catalog": position_catalog,
    }


async def _assert_manager_team_gate(database_url: URL) -> dict[str, object]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _seed_manager_hierarchy(engine)
        service = EmployeeAssignmentService(
            session_factory=session_factory,
            today_factory=lambda: TODAY,
        )
        captured: list[str] = []

        def capture_statement(
            _connection,
            _cursor,
            statement: str,
            _parameters,
            _context,
            _executemany: bool,
        ) -> None:
            captured.append(statement)

        select_counts: list[int] = []
        statement_counts: list[int] = []
        employee_numbers: list[str] = []
        cursor: TeamListCursor | None = None
        event.listen(engine.sync_engine, "before_cursor_execute", capture_statement)
        try:
            while True:
                captured.clear()
                page = await service.my_team(
                    request_context=_team_request_context(
                        tenant_id=TEAM_TENANT_A_ID,
                        tenant_slug="p3k-team-a",
                        actor_id=MANAGER_A_ID,
                    ),
                    pagination=TeamListPagination(
                        limit=TEAM_PAGE_LIMIT,
                        cursor=cursor,
                    ),
                    granted_permissions=(EMPLOYEE_TEAM_READ_PERMISSION,),
                )
                counts = _statement_counts(captured)
                select_counts.append(counts["SELECT"])
                statement_counts.append(sum(counts.values()))
                assert any(
                    statement.startswith("SET LOCAL ROLE") and TENANT_APPLICATION_ROLE in statement
                    for statement in captured
                )
                assert any(
                    statement.startswith("SET LOCAL app.tenant_id")
                    and str(TEAM_TENANT_A_ID) in statement
                    for statement in captured
                )
                employee_numbers.extend(item.employee.employee_number for item in page.items)
                if page.next_cursor is None:
                    break
                cursor = TeamListCursor.from_token(page.next_cursor)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", capture_statement)

        expected_numbers = {"A-DIRECT-000000"} | {
            f"A-DIRECT-{number:06d}" for number in range(1, DIRECT_REPORT_COUNT + 1)
        }
        assert len(employee_numbers) == len(set(employee_numbers))
        assert set(employee_numbers) == expected_numbers
        assert employee_numbers == sorted(employee_numbers)
        assert not any(number.startswith("A-INDIRECT-") for number in employee_numbers)
        assert not any(number.startswith("B-CROSS-") for number in employee_numbers)

        manager_b_page = await service.my_team(
            request_context=_team_request_context(
                tenant_id=TEAM_TENANT_A_ID,
                tenant_slug="p3k-team-a",
                actor_id=MANAGER_B_ID,
            ),
            pagination=TeamListPagination(limit=3),
            granted_permissions=(EMPLOYEE_TEAM_READ_PERMISSION,),
        )
        assert [item.employee.employee_number for item in manager_b_page.items] == [
            "A-INDIRECT-000001",
            "A-INDIRECT-000002",
            "A-INDIRECT-000003",
        ]

        cross_tenant_page = await service.my_team(
            request_context=_team_request_context(
                tenant_id=TEAM_TENANT_B_ID,
                tenant_slug="p3k-team-b",
                actor_id=MANAGER_TENANT_B_ID,
            ),
            pagination=TeamListPagination(limit=3),
            granted_permissions=(EMPLOYEE_TEAM_READ_PERMISSION,),
        )
        assert [item.employee.employee_number for item in cross_tenant_page.items] == [
            "B-CROSS-000001",
            "B-CROSS-000002",
            "B-CROSS-000003",
        ]
        forged_cross_tenant_page = await service.my_team(
            request_context=_team_request_context(
                tenant_id=TEAM_TENANT_B_ID,
                tenant_slug="p3k-team-b",
                actor_id=MANAGER_A_ID,
            ),
            pagination=TeamListPagination(limit=3),
            granted_permissions=(EMPLOYEE_TEAM_READ_PERMISSION,),
        )
        assert forged_cross_tenant_page.items == []
        assert forged_cross_tenant_page.next_cursor is None

        plan = await _manager_query_plan(engine)
        plan_root = plan["Plan"]
        assert isinstance(plan_root, dict)
        indexes = sorted(_index_names(plan_root))
        assert "ix_employee_assignments_tenant_manager_scope" in indexes
        return {
            "dataset_assignments": (
                DIRECT_REPORT_COUNT + INDIRECT_REPORT_COUNT + CROSS_TENANT_REPORT_COUNT + 1
            ),
            "direct_reports": len(employee_numbers),
            "pages": len(select_counts),
            "selects_per_page": select_counts,
            "statements_per_page": statement_counts,
            "indexes": [
                name for name in indexes if name == "ix_employee_assignments_tenant_manager_scope"
            ],
            "explain_actual_rows": int(plan_root["Actual Rows"]),
            "execution_time_ms": round(float(plan["Execution Time"]), 3),
        }
    finally:
        await engine.dispose()


async def _seed_manager_hierarchy(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into tenants ("
                "id, slug, name, status, plan_code, data_region, locale, timezone"
                ") values "
                "(:tenant_a, 'p3k-team-a', 'P3K Team A', 'active', "
                "'core', 'tr-1', 'en-US', 'UTC'), "
                "(:tenant_b, 'p3k-team-b', 'P3K Team B', 'active', "
                "'core', 'tr-1', 'en-US', 'UTC')"
            ),
            {"tenant_a": TEAM_TENANT_A_ID, "tenant_b": TEAM_TENANT_B_ID},
        )
        await connection.execute(
            text(
                "insert into tenant_feature_flags (tenant_id, key, enabled) values "
                "(:tenant_a, 'organization', true), "
                "(:tenant_b, 'organization', true)"
            ),
            {"tenant_a": TEAM_TENANT_A_ID, "tenant_b": TEAM_TENANT_B_ID},
        )
        await connection.execute(
            text(
                "insert into legal_entities ("
                "id, tenant_id, code, name, registered_name, timezone, status, is_default"
                ") values "
                "(:entity_a, :tenant_a, 'DEFAULT', 'P3K Team A', 'P3K Team A', "
                "'UTC', 'active', true), "
                "(:entity_b, :tenant_b, 'DEFAULT', 'P3K Team B', 'P3K Team B', "
                "'UTC', 'active', true)"
            ),
            {
                "entity_a": TEAM_LEGAL_ENTITY_A_ID,
                "tenant_a": TEAM_TENANT_A_ID,
                "entity_b": TEAM_LEGAL_ENTITY_B_ID,
                "tenant_b": TEAM_TENANT_B_ID,
            },
        )
        await connection.execute(
            text(
                "insert into branches ("
                "id, tenant_id, legal_entity_id, code, name, timezone, status"
                ") values "
                "(:branch_a, :tenant_a, :entity_a, 'HQ', 'Tenant A HQ', 'UTC', 'active'), "
                "(:branch_b, :tenant_b, :entity_b, 'HQ', 'Tenant B HQ', 'UTC', 'active')"
            ),
            {
                "branch_a": TEAM_BRANCH_A_ID,
                "tenant_a": TEAM_TENANT_A_ID,
                "entity_a": TEAM_LEGAL_ENTITY_A_ID,
                "branch_b": TEAM_BRANCH_B_ID,
                "tenant_b": TEAM_TENANT_B_ID,
                "entity_b": TEAM_LEGAL_ENTITY_B_ID,
            },
        )
        await connection.execute(
            text(
                "insert into departments (id, tenant_id, parent_id, code, name, status) "
                "values "
                "(:root_a, :tenant_a, null, 'ROOT', 'Root Team', 'active'), "
                "(:child_a, :tenant_a, :root_a, 'CHILD', 'Child Team', 'active'), "
                "(:department_b, :tenant_b, null, 'ROOT', 'Tenant B Team', 'active')"
            ),
            {
                "root_a": TEAM_ROOT_DEPARTMENT_A_ID,
                "child_a": TEAM_CHILD_DEPARTMENT_A_ID,
                "department_b": TEAM_DEPARTMENT_B_ID,
                "tenant_a": TEAM_TENANT_A_ID,
                "tenant_b": TEAM_TENANT_B_ID,
            },
        )
        await connection.execute(
            text(
                "insert into positions (id, tenant_id, code, title, status) values "
                "(:position_a, :tenant_a, 'MEMBER', 'Team Member', 'active'), "
                "(:position_b, :tenant_b, 'MEMBER', 'Team Member', 'active')"
            ),
            {
                "position_a": TEAM_POSITION_A_ID,
                "tenant_a": TEAM_TENANT_A_ID,
                "position_b": TEAM_POSITION_B_ID,
                "tenant_b": TEAM_TENANT_B_ID,
            },
        )
        await connection.execute(
            text(
                "insert into users (id, tenant_id, email, full_name, status) values "
                "(:manager_a, :tenant_a, 'manager-a@p3k.test', 'Manager A', 'active'), "
                "(:manager_b, :tenant_a, 'manager-b@p3k.test', 'Manager B', 'active'), "
                "(:manager_tenant_b, :tenant_b, 'manager@tenant-b.p3k.test', "
                "'Tenant B Manager', 'active')"
            ),
            {
                "manager_a": MANAGER_A_ID,
                "manager_b": MANAGER_B_ID,
                "manager_tenant_b": MANAGER_TENANT_B_ID,
                "tenant_a": TEAM_TENANT_A_ID,
                "tenant_b": TEAM_TENANT_B_ID,
            },
        )
        await connection.execute(
            text(
                "insert into employees ("
                "id, tenant_id, employee_number, first_name, last_name, email, status, "
                "employment_start_date"
                ") values ("
                ":employee_id, :tenant_id, 'A-DIRECT-000000', 'Manager', 'B', "
                "'manager-b@p3k.test', 'active', DATE '2025-01-01'"
                ")"
            ),
            {
                "employee_id": MANAGER_B_EMPLOYEE_ID,
                "tenant_id": TEAM_TENANT_A_ID,
            },
        )
        await _insert_generated_employees(
            connection,
            id_prefix="cb610001-0000-4000-8000-",
            tenant_id=TEAM_TENANT_A_ID,
            employee_number_prefix="A-DIRECT-",
            count=DIRECT_REPORT_COUNT,
        )
        await _insert_generated_employees(
            connection,
            id_prefix="cb610002-0000-4000-8000-",
            tenant_id=TEAM_TENANT_A_ID,
            employee_number_prefix="A-INDIRECT-",
            count=INDIRECT_REPORT_COUNT,
        )
        await _insert_generated_employees(
            connection,
            id_prefix="cb610003-0000-4000-8000-",
            tenant_id=TEAM_TENANT_B_ID,
            employee_number_prefix="B-CROSS-",
            count=CROSS_TENANT_REPORT_COUNT,
        )
        await connection.execute(
            text(
                "insert into employee_assignments ("
                "id, tenant_id, employee_id, legal_entity_id, branch_id, department_id, "
                "position_id, manager_user_id, effective_from, change_reason"
                ") values ("
                ":assignment_id, :tenant_id, :employee_id, :entity_id, :branch_id, "
                ":department_id, :position_id, :manager_id, DATE '2025-01-01', "
                "'P3K synthetic reporting hierarchy'"
                ")"
            ),
            {
                "assignment_id": MANAGER_B_ASSIGNMENT_ID,
                "tenant_id": TEAM_TENANT_A_ID,
                "employee_id": MANAGER_B_EMPLOYEE_ID,
                "entity_id": TEAM_LEGAL_ENTITY_A_ID,
                "branch_id": TEAM_BRANCH_A_ID,
                "department_id": TEAM_ROOT_DEPARTMENT_A_ID,
                "position_id": TEAM_POSITION_A_ID,
                "manager_id": MANAGER_A_ID,
            },
        )
        await _insert_generated_assignments(
            connection,
            employee_id_prefix="cb610001-0000-4000-8000-",
            assignment_id_prefix="cb710001-0000-4000-8000-",
            tenant_id=TEAM_TENANT_A_ID,
            legal_entity_id=TEAM_LEGAL_ENTITY_A_ID,
            branch_id=TEAM_BRANCH_A_ID,
            department_id=TEAM_ROOT_DEPARTMENT_A_ID,
            position_id=TEAM_POSITION_A_ID,
            manager_id=MANAGER_A_ID,
            count=DIRECT_REPORT_COUNT,
        )
        await _insert_generated_assignments(
            connection,
            employee_id_prefix="cb610002-0000-4000-8000-",
            assignment_id_prefix="cb710002-0000-4000-8000-",
            tenant_id=TEAM_TENANT_A_ID,
            legal_entity_id=TEAM_LEGAL_ENTITY_A_ID,
            branch_id=TEAM_BRANCH_A_ID,
            department_id=TEAM_CHILD_DEPARTMENT_A_ID,
            position_id=TEAM_POSITION_A_ID,
            manager_id=MANAGER_B_ID,
            count=INDIRECT_REPORT_COUNT,
        )
        await _insert_generated_assignments(
            connection,
            employee_id_prefix="cb610003-0000-4000-8000-",
            assignment_id_prefix="cb710003-0000-4000-8000-",
            tenant_id=TEAM_TENANT_B_ID,
            legal_entity_id=TEAM_LEGAL_ENTITY_B_ID,
            branch_id=TEAM_BRANCH_B_ID,
            department_id=TEAM_DEPARTMENT_B_ID,
            position_id=TEAM_POSITION_B_ID,
            manager_id=MANAGER_TENANT_B_ID,
            count=CROSS_TENANT_REPORT_COUNT,
        )

    async with engine.begin() as connection:
        await connection.execute(text("analyze employees"))
        await connection.execute(text("analyze employee_assignments"))


async def _insert_generated_employees(
    connection: AsyncConnection,
    *,
    id_prefix: str,
    tenant_id: UUID,
    employee_number_prefix: str,
    count: int,
) -> None:
    await connection.execute(
        text(
            "insert into employees ("
            "id, tenant_id, employee_number, first_name, last_name, status, "
            "employment_start_date"
            ") select "
            "(:id_prefix || lpad(gs::text, 12, '0'))::uuid, :tenant_id, "
            ":employee_number_prefix || lpad(gs::text, 6, '0'), "
            "'Employee', lpad(gs::text, 6, '0'), 'active', DATE '2025-01-01' "
            "from generate_series(1, :row_count) as gs"
        ),
        {
            "id_prefix": id_prefix,
            "tenant_id": tenant_id,
            "employee_number_prefix": employee_number_prefix,
            "row_count": count,
        },
    )


async def _insert_generated_assignments(
    connection: AsyncConnection,
    *,
    employee_id_prefix: str,
    assignment_id_prefix: str,
    tenant_id: UUID,
    legal_entity_id: UUID,
    branch_id: UUID,
    department_id: UUID,
    position_id: UUID,
    manager_id: UUID,
    count: int,
) -> None:
    await connection.execute(
        text(
            "insert into employee_assignments ("
            "id, tenant_id, employee_id, legal_entity_id, branch_id, department_id, "
            "position_id, manager_user_id, effective_from, change_reason"
            ") select "
            "(:assignment_id_prefix || lpad(gs::text, 12, '0'))::uuid, :tenant_id, "
            "(:employee_id_prefix || lpad(gs::text, 12, '0'))::uuid, :legal_entity_id, "
            ":branch_id, :department_id, :position_id, :manager_id, DATE '2025-01-01', "
            "'P3K synthetic reporting hierarchy' "
            "from generate_series(1, :row_count) as gs"
        ),
        {
            "assignment_id_prefix": assignment_id_prefix,
            "employee_id_prefix": employee_id_prefix,
            "tenant_id": tenant_id,
            "legal_entity_id": legal_entity_id,
            "branch_id": branch_id,
            "department_id": department_id,
            "position_id": position_id,
            "manager_id": manager_id,
            "row_count": count,
        },
    )


async def _manager_query_plan(engine: AsyncEngine) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TEAM_TENANT_A_ID)
        statement = (
            _assignment_view_statement(tenant_id=TEAM_TENANT_A_ID)
            .where(
                EmployeeAssignment.manager_user_id == MANAGER_A_ID,
                _effective_on(TODAY),
                Employee.archived_at.is_(None),
                Employee.status.in_((EmployeeStatus.ACTIVE.value, EmployeeStatus.ON_LEAVE.value)),
            )
            .order_by(Employee.employee_number.asc(), Employee.id.asc())
            .limit(TEAM_PAGE_LIMIT + 1)
        )
        compiled = statement.compile(
            dialect=connection.dialect,
            compile_kwargs={"literal_binds": True},
        )
        payload = await connection.scalar(
            text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {compiled}")
        )
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert isinstance(payload, list) and len(payload) == 1
    plan = payload[0]
    assert isinstance(plan, dict)
    return plan


def _team_request_context(
    *,
    tenant_id: UUID,
    tenant_slug: str,
    actor_id: UUID,
) -> RequestContext:
    return RequestContext(
        request_id="req_p3k_manager_scope",
        trace_id="cb000000000040008000000000000001",
        tenant=TenantContext(tenant_id=tenant_id, slug=tenant_slug),
        actor_id=actor_id,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )


async def _set_local_tenant_role(
    connection: AsyncConnection,
    tenant_id: UUID,
) -> None:
    quoted_role = connection.dialect.identifier_preparer.quote(TENANT_APPLICATION_ROLE)
    await connection.exec_driver_sql(f"SET LOCAL ROLE {quoted_role}")
    await connection.exec_driver_sql(f"SET LOCAL app.tenant_id = '{tenant_id}'")


def _statement_counts(statements: list[str]) -> Counter[str]:
    return Counter(statement.lstrip().partition(" ")[0].upper() for statement in statements)


def _deterministic_uuid(value: str) -> UUID:
    digest = hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()
    return UUID(digest)


def _index_names(plan: dict[str, object]) -> set[str]:
    names: set[str] = set()
    index_name = plan.get("Index Name")
    if isinstance(index_name, str):
        names.add(index_name)
    for child in plan.get("Plans", []):
        if isinstance(child, dict):
            names.update(_index_names(child))
    return names


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config
