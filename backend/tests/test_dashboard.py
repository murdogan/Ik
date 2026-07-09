from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from app.api.dashboard import get_dashboard_service
from app.db.base import Base
from app.main import create_app
from app.models.employee import Employee, EmployeeStatus
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.schemas.dashboard import DashboardSummary, DepartmentDistributionItem
from app.services.dashboard_service import DashboardService
from fastapi.testclient import TestClient
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
    client = TestClient(create_app())

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 422


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
