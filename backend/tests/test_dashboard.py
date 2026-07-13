from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from app.api.dashboard import get_dashboard_service
from app.db.base import Base
from app.main import create_app
from app.models.department import Department, DepartmentStatus
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_assignment import EmployeeAssignment
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.organization import Branch, BranchStatus, LegalEntity, LegalEntityStatus
from app.models.position import Position, PositionStatus
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.schemas.dashboard import DashboardSummary, DepartmentDistributionItem
from app.services.dashboard_service import DashboardService
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_TENANT_ID = UUID("22222222-2222-4222-8222-222222222222")
USER_ID = UUID("33333333-3333-4333-8333-333333333333")
OTHER_USER_ID = UUID("44444444-4444-4444-8444-444444444444")
TODAY = date(2026, 7, 8)
NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
STRUCTURED_BRANCH_ID = UUID("a3000000-0000-4000-8000-000000000001")
STRUCTURED_DEPARTMENT_ID = UUID("a3000000-0000-4000-8000-000000000002")
EXPIRED_DEPARTMENT_ID = UUID("a3000000-0000-4000-8000-000000000003")
STRUCTURED_POSITION_ID = UUID("a3000000-0000-4000-8000-000000000004")


async def _session_with_seed_data() -> tuple[AsyncSession, AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        use_insertmanyvalues=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()
    session.add_all(
        [
            Tenant(
                id=TENANT_ID,
                slug="wealthy-falcon",
                name="Wealthy Falcon HR",
                status=TenantStatus.ACTIVE.value,
                plan_code="core",
                data_region="tr-1",
                locale="tr-TR",
                timezone="Europe/Istanbul",
            ),
            Tenant(
                id=OTHER_TENANT_ID,
                slug="other",
                name="Other Tenant",
                status=TenantStatus.ACTIVE.value,
                plan_code="core",
                data_region="tr-1",
                locale="tr-TR",
                timezone="Europe/Istanbul",
            ),
            User(
                id=USER_ID,
                tenant_id=TENANT_ID,
                email="hr@wealthyfalcon.test",
                full_name="HR User",
                status=UserStatus.ACTIVE.value,
            ),
            User(
                id=OTHER_USER_ID,
                tenant_id=OTHER_TENANT_ID,
                email="hr@other.test",
                full_name="Other HR",
                status=UserStatus.ACTIVE.value,
            ),
            Employee(
                id=UUID("5aaaaaaa-5555-4555-8555-555555555555"),
                tenant_id=TENANT_ID,
                employee_number="WF-001",
                first_name="Ada",
                last_name="Yilmaz",
                department="People",
                position="HR Specialist",
                status=EmployeeStatus.ACTIVE.value,
                employment_start_date=date(2026, 7, 1),
                created_at=NOW - timedelta(days=1),
            ),
            Employee(
                id=UUID("6bbbbbbb-6666-4666-8666-666666666666"),
                tenant_id=TENANT_ID,
                employee_number="WF-002",
                first_name="Bora",
                last_name="Demir",
                department="Engineering",
                position="Backend Engineer",
                status=EmployeeStatus.ACTIVE.value,
                employment_start_date=date(2026, 7, 7),
                created_at=NOW - timedelta(days=3),
            ),
            Employee(
                id=UUID("7ccccccc-7777-4777-8777-777777777777"),
                tenant_id=TENANT_ID,
                employee_number="WF-003",
                first_name="Cem",
                last_name="Kaya",
                department="People",
                position="People Partner",
                status=EmployeeStatus.ON_LEAVE.value,
                employment_start_date=date(2026, 6, 15),
                created_at=NOW - timedelta(days=10),
            ),
            Employee(
                id=UUID("8ddddddd-8888-4888-8888-888888888888"),
                tenant_id=TENANT_ID,
                employee_number="WF-004",
                first_name="Defne",
                last_name="Sahin",
                department="Sales",
                position="Account Executive",
                status=EmployeeStatus.TERMINATED.value,
                employment_start_date=date(2026, 5, 1),
                employment_end_date=date(2026, 6, 30),
                created_at=NOW - timedelta(days=20),
            ),
            Employee(
                id=UUID("4fffffff-4444-4fff-8fff-ffffffffffff"),
                tenant_id=TENANT_ID,
                employee_number="WF-005",
                first_name="Elif",
                last_name="Arslan",
                department="   ",
                position="Operations Specialist",
                status=EmployeeStatus.ACTIVE.value,
                employment_start_date=date(2026, 4, 1),
                created_at=NOW - timedelta(days=30),
            ),
            Employee(
                id=UUID("9eeeeeee-9999-4999-8999-999999999999"),
                tenant_id=OTHER_TENANT_ID,
                employee_number="OT-001",
                first_name="Other",
                last_name="Person",
                department="Sales",
                position="Manager",
                status=EmployeeStatus.ACTIVE.value,
                employment_start_date=date(2026, 7, 1),
                created_at=NOW - timedelta(hours=1),
            ),
            LeaveRequest(
                id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                tenant_id=TENANT_ID,
                employee_id=UUID("5aaaaaaa-5555-4555-8555-555555555555"),
                leave_type="annual",
                start_date=date(2026, 7, 20),
                end_date=date(2026, 7, 22),
                status=LeaveRequestStatus.PENDING.value,
                requested_by_user_id=USER_ID,
                created_at=NOW - timedelta(hours=2),
            ),
            LeaveRequest(
                id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
                tenant_id=TENANT_ID,
                employee_id=UUID("6bbbbbbb-6666-4666-8666-666666666666"),
                leave_type="sick",
                start_date=date(2026, 7, 10),
                end_date=date(2026, 7, 10),
                status=LeaveRequestStatus.APPROVED.value,
                requested_by_user_id=USER_ID,
                decided_by_user_id=USER_ID,
                created_at=NOW - timedelta(hours=4),
            ),
            LeaveRequest(
                id=UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
                tenant_id=OTHER_TENANT_ID,
                employee_id=UUID("9eeeeeee-9999-4999-8999-999999999999"),
                leave_type="annual",
                start_date=date(2026, 7, 20),
                end_date=date(2026, 7, 22),
                status=LeaveRequestStatus.PENDING.value,
                requested_by_user_id=OTHER_USER_ID,
                created_at=NOW - timedelta(minutes=30),
            ),
        ]
    )
    await session.commit()
    return session, engine


async def _add_structured_assignment_history(session: AsyncSession) -> None:
    session.add_all(
        [
            LegalEntity(
                id=TENANT_ID,
                tenant_id=TENANT_ID,
                code="DEFAULT",
                name="Wealthy Falcon HR",
                registered_name="Wealthy Falcon HR",
                timezone="Europe/Istanbul",
                status=LegalEntityStatus.ACTIVE.value,
                is_default=True,
            ),
            Branch(
                id=STRUCTURED_BRANCH_ID,
                tenant_id=TENANT_ID,
                legal_entity_id=TENANT_ID,
                code="HQ",
                name="Headquarters",
                timezone="Europe/Istanbul",
                status=BranchStatus.ACTIVE.value,
                archived_at=None,
            ),
            Department(
                id=STRUCTURED_DEPARTMENT_ID,
                tenant_id=TENANT_ID,
                parent_id=None,
                code="ENGINEERING",
                name="Engineering",
                status=DepartmentStatus.ACTIVE.value,
                archived_at=None,
            ),
            Department(
                id=EXPIRED_DEPARTMENT_ID,
                tenant_id=TENANT_ID,
                parent_id=None,
                code="SALES",
                name="Sales",
                status=DepartmentStatus.ACTIVE.value,
                archived_at=None,
            ),
            Position(
                id=STRUCTURED_POSITION_ID,
                tenant_id=TENANT_ID,
                code="ENGINEER",
                title="Platform Engineer",
                status=PositionStatus.ACTIVE.value,
                archived_at=None,
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            EmployeeAssignment(
                id=UUID("a3000000-0000-4000-8000-000000000005"),
                tenant_id=TENANT_ID,
                employee_id=UUID("5aaaaaaa-5555-4555-8555-555555555555"),
                legal_entity_id=TENANT_ID,
                branch_id=STRUCTURED_BRANCH_ID,
                department_id=STRUCTURED_DEPARTMENT_ID,
                position_id=STRUCTURED_POSITION_ID,
                manager_user_id=None,
                supersedes_assignment_id=None,
                effective_from=date(2026, 7, 1),
                effective_to=None,
                change_reason="Current structured assignment",
                created_by_user_id=None,
            ),
            EmployeeAssignment(
                id=UUID("a3000000-0000-4000-8000-000000000006"),
                tenant_id=TENANT_ID,
                employee_id=UUID("7ccccccc-7777-4777-8777-777777777777"),
                legal_entity_id=TENANT_ID,
                branch_id=STRUCTURED_BRANCH_ID,
                department_id=EXPIRED_DEPARTMENT_ID,
                position_id=STRUCTURED_POSITION_ID,
                manager_user_id=None,
                supersedes_assignment_id=None,
                effective_from=date(2026, 6, 1),
                effective_to=TODAY,
                change_reason="Expired structured assignment",
                created_by_user_id=None,
            ),
        ]
    )
    await session.commit()


async def test_dashboard_summary_counts_are_tenant_scoped_from_database() -> None:
    session, engine = await _session_with_seed_data()

    summary = await DashboardService(session=session, today=TODAY).get_summary(TENANT_ID)

    assert summary.active_employee_count == 3
    assert summary.employee_count == 4
    assert summary.pending_leave_count == 1
    assert summary.pending_leave_requests == 1
    assert summary.new_starters_this_month == 2
    assert summary.open_tasks == 0
    assert summary.department_distribution == [
        DepartmentDistributionItem(department="People", count=2),
        DepartmentDistributionItem(department="Engineering", count=1),
        DepartmentDistributionItem(department="Unassigned", count=1),
    ]

    await session.close()
    await engine.dispose()


async def test_dashboard_department_distribution_prefers_current_assignment() -> None:
    session, engine = await _session_with_seed_data()
    await _add_structured_assignment_history(session)
    statement_count = 0

    def count_statements(
        _connection,
        _cursor,
        _statement: str,
        _parameters,
        _context,
        _executemany: bool,
    ) -> None:
        nonlocal statement_count
        statement_count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_statements)
    try:
        summary = await DashboardService(
            session=session,
            today=TODAY,
            recent_activity_limit=0,
        ).get_summary(TENANT_ID)

        assert statement_count == 2
        assert summary.department_distribution == [
            DepartmentDistributionItem(department="Engineering", count=2),
            DepartmentDistributionItem(department="People", count=1),
            DepartmentDistributionItem(department="Unassigned", count=1),
        ]
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_statements)
        await session.close()
        await engine.dispose()


async def test_dashboard_excludes_archived_employees_from_workforce_views() -> None:
    session, engine = await _session_with_seed_data()
    archived_employee_id = UUID("5aaaaaaa-5555-4555-8555-555555555555")
    await session.execute(
        update(Employee)
        .where(Employee.employee_number == "WF-001")
        .values(archived_at=NOW)
    )
    await session.flush()

    summary = await DashboardService(
        session=session,
        today=TODAY,
        recent_activity_limit=20,
    ).get_summary(TENANT_ID)

    assert summary.active_employee_count == 2
    assert summary.employee_count == 3
    assert summary.new_starters_this_month == 1
    assert summary.department_distribution == [
        DepartmentDistributionItem(department="Engineering", count=1),
        DepartmentDistributionItem(department="People", count=1),
        DepartmentDistributionItem(department="Unassigned", count=1),
    ]
    assert not any(
        item.entity_type == "employee" and item.entity_id == archived_employee_id
        for item in summary.recent_activity
    )

    await session.close()
    await engine.dispose()


async def test_dashboard_summary_enrichment_reflects_database_changes() -> None:
    session, engine = await _session_with_seed_data()
    service = DashboardService(session=session, today=TODAY, recent_activity_limit=0)

    before = await service.get_summary(TENANT_ID)
    employee_id = UUID("a2000000-0000-4000-8000-000000000001")
    session.add_all(
        [
            Employee(
                id=employee_id,
                tenant_id=TENANT_ID,
                employee_number="WF-006",
                first_name="Funda",
                last_name="Acar",
                department="Legal",
                position="Counsel",
                status=EmployeeStatus.ACTIVE.value,
                employment_start_date=TODAY,
            ),
            LeaveRequest(
                id=UUID("a2000000-0000-4000-8000-000000000002"),
                tenant_id=TENANT_ID,
                employee_id=employee_id,
                leave_type="annual",
                start_date=TODAY + timedelta(days=10),
                end_date=TODAY + timedelta(days=11),
                status=LeaveRequestStatus.PENDING.value,
                requested_by_user_id=USER_ID,
            ),
        ]
    )
    await session.commit()

    after = await service.get_summary(TENANT_ID)

    assert after.active_employee_count == before.active_employee_count + 1
    assert after.employee_count == before.employee_count + 1
    assert after.pending_leave_count == before.pending_leave_count + 1
    assert after.pending_leave_requests == after.pending_leave_count
    assert after.new_starters_this_month == before.new_starters_this_month + 1
    assert after.department_distribution == [
        DepartmentDistributionItem(department="People", count=2),
        DepartmentDistributionItem(department="Engineering", count=1),
        DepartmentDistributionItem(department="Legal", count=1),
        DepartmentDistributionItem(department="Unassigned", count=1),
    ]

    await session.close()
    await engine.dispose()


async def test_dashboard_this_month_starters_use_calendar_month_window() -> None:
    session, engine = await _session_with_seed_data()
    session.add_all(
        [
            Employee(
                id=UUID("a1000000-0000-4000-8000-000000000001"),
                tenant_id=TENANT_ID,
                employee_number="WF-006",
                first_name="Gizem",
                last_name="Aydin",
                department="Finance",
                position="Finance Lead",
                status=EmployeeStatus.ACTIVE.value,
                employment_start_date=date(2026, 12, 1),
            ),
            Employee(
                id=UUID("a1000000-0000-4000-8000-000000000002"),
                tenant_id=TENANT_ID,
                employee_number="WF-007",
                first_name="Hakan",
                last_name="Oz",
                department="Finance",
                position="Analyst",
                status=EmployeeStatus.ON_LEAVE.value,
                employment_start_date=date(2026, 12, 31),
            ),
            Employee(
                id=UUID("a1000000-0000-4000-8000-000000000003"),
                tenant_id=TENANT_ID,
                employee_number="WF-008",
                first_name="Ipek",
                last_name="Can",
                department="Finance",
                position="Former Analyst",
                status=EmployeeStatus.TERMINATED.value,
                employment_start_date=date(2026, 12, 15),
                employment_end_date=date(2026, 12, 20),
            ),
            Employee(
                id=UUID("a1000000-0000-4000-8000-000000000004"),
                tenant_id=TENANT_ID,
                employee_number="WF-009",
                first_name="Jale",
                last_name="Kurt",
                department="Finance",
                position="Controller",
                status=EmployeeStatus.ACTIVE.value,
                employment_start_date=date(2027, 1, 1),
            ),
            Employee(
                id=UUID("a1000000-0000-4000-8000-000000000005"),
                tenant_id=OTHER_TENANT_ID,
                employee_number="OT-002",
                first_name="Other",
                last_name="Starter",
                department="Finance",
                position="Analyst",
                status=EmployeeStatus.ACTIVE.value,
                employment_start_date=date(2026, 12, 10),
            ),
        ]
    )
    await session.commit()

    summary = await DashboardService(
        session=session,
        today=date(2026, 12, 31),
        recent_activity_limit=0,
    ).get_summary(TENANT_ID)

    assert summary.new_starters_this_month == 2

    await session.close()
    await engine.dispose()


async def test_dashboard_recent_activity_uses_current_tenant_records_only() -> None:
    session, engine = await _session_with_seed_data()

    summary = await DashboardService(session=session, today=TODAY).get_summary(TENANT_ID)

    assert [
        (activity.activity_type, activity.entity_id)
        for activity in summary.recent_activity[:3]
    ] == [
        ("leave.requested", UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")),
        ("leave.approved", UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")),
        ("employee.created", UUID("5aaaaaaa-5555-4555-8555-555555555555")),
    ]
    assert UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc") not in {
        activity.entity_id for activity in summary.recent_activity
    }

    await session.close()
    await engine.dispose()


async def test_dashboard_recent_activity_limit_is_applied_after_source_merge() -> None:
    session, engine = await _session_with_seed_data()

    summary = await DashboardService(
        session=session,
        today=TODAY,
        recent_activity_limit=2,
    ).get_summary(TENANT_ID)

    assert [
        (activity.activity_type, activity.entity_id)
        for activity in summary.recent_activity
    ] == [
        ("leave.requested", UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")),
        ("leave.approved", UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")),
    ]

    await session.close()
    await engine.dispose()


async def test_dashboard_default_summary_uses_four_select_statements() -> None:
    session, engine = await _session_with_seed_data()
    statements: list[str] = []

    def capture_statement(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture_statement)
    try:
        await DashboardService(session=session, today=TODAY).get_summary(TENANT_ID)

        assert len(statements) == 4
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_statement)
        await session.close()
        await engine.dispose()


async def test_dashboard_without_activity_uses_two_select_statements() -> None:
    session, engine = await _session_with_seed_data()
    statement_count = 0

    def count_statements(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany: bool,
    ) -> None:
        nonlocal statement_count
        statement_count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_statements)
    try:
        await DashboardService(
            session=session,
            today=TODAY,
            recent_activity_limit=0,
        ).get_summary(TENANT_ID)

        assert statement_count == 2
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_statements)
        await session.close()
        await engine.dispose()


async def test_dashboard_summary_returns_zero_state_for_empty_tenant() -> None:
    session, engine = await _session_with_seed_data()

    summary = await DashboardService(session=session, today=TODAY).get_summary(
        UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
    )

    assert summary.active_employee_count == 0
    assert summary.employee_count == 0
    assert summary.pending_leave_count == 0
    assert summary.pending_leave_requests == 0
    assert summary.new_starters_this_month == 0
    assert summary.open_tasks == 0
    assert summary.department_distribution == []
    assert summary.recent_activity == []

    await session.close()
    await engine.dispose()


async def test_dashboard_summary_endpoint_reads_enriched_metrics_from_database() -> None:
    session, engine = await _session_with_seed_data()
    app = create_app()

    def override_dashboard_service() -> DashboardService:
        return DashboardService(session=session, today=TODAY, recent_activity_limit=0)

    app.dependency_overrides[get_dashboard_service] = override_dashboard_service

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/api/v1/dashboard/summary",
                headers={
                    "X-Tenant-Id": str(TENANT_ID),
                    "X-Tenant-Slug": "wealthy-falcon",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["active_employee_count"] == 3
        assert body["employee_count"] == 4
        assert body["pending_leave_count"] == 1
        assert body["pending_leave_requests"] == 1
        assert body["new_starters_this_month"] == 2
        assert body["department_distribution"] == [
            {"department": "People", "count": 2},
            {"department": "Engineering", "count": 1},
            {"department": "Unassigned", "count": 1},
        ]
        assert body["recent_activity"] == []
    finally:
        app.dependency_overrides.clear()
        await session.close()
        await engine.dispose()


def test_dashboard_summary_endpoint_uses_tenant_header() -> None:
    class FakeDashboardService:
        tenant_ids: list[UUID] = []

        async def get_summary(self, tenant_id: UUID) -> DashboardSummary:
            self.tenant_ids.append(tenant_id)
            return DashboardSummary(
                active_employee_count=6,
                pending_leave_count=2,
                employee_count=7,
                pending_leave_requests=2,
                new_starters_this_month=1,
                open_tasks=0,
                department_distribution=[
                    DepartmentDistributionItem(department="People", count=7)
                ],
                recent_activity=[],
            )

    fake_service = FakeDashboardService()

    def override_dashboard_service() -> FakeDashboardService:
        return fake_service

    app = create_app()
    app.dependency_overrides[get_dashboard_service] = override_dashboard_service
    client = TestClient(app)

    response = client.get(
        "/api/v1/dashboard/summary",
        headers={"X-Tenant-Id": str(TENANT_ID), "X-Tenant-Slug": "wealthy-falcon"},
    )

    assert response.status_code == 200
    assert fake_service.tenant_ids == [TENANT_ID]
    assert response.json()["active_employee_count"] == 6
    assert response.json()["employee_count"] == 7
    assert response.json()["pending_leave_count"] == 2
    assert response.json()["recent_activity"] == []


def test_dashboard_summary_endpoint_requires_tenant_header() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "tenant_header_missing",
            "message": "X-Tenant-Id header is required",
            "details": None,
            "correlation_id": None,
        }
    }


def test_dashboard_summary_endpoint_rejects_invalid_tenant_header() -> None:
    with TestClient(create_app()) as client:
        response = client.get(
            "/api/v1/dashboard/summary",
            headers={"X-Tenant-Id": "not-a-uuid", "X-Correlation-Id": "dashboard-tenant"},
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "tenant_header_invalid",
            "message": "X-Tenant-Id header must be a single canonical hyphenated UUID",
            "details": None,
            "correlation_id": "dashboard-tenant",
        }
    }


def test_dashboard_summary_is_exposed_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    assert "/api/v1/dashboard/summary" in openapi["paths"]
    summary_properties = openapi["components"]["schemas"]["DashboardSummary"]["properties"]
    assert "active_employee_count" in summary_properties
    assert "pending_leave_count" in summary_properties
    assert "department_distribution" in summary_properties
    assert "new_starters_this_month" in summary_properties
