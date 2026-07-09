from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID

from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.employee import Employee, EmployeeStatus
from app.models.leave_balance_summary import LeaveBalanceSummary
from app.models.tenant import Tenant, TenantStatus
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

TENANT_ID = UUID("11111111-aaaa-4111-8111-111111111111")
OTHER_TENANT_ID = UUID("22222222-bbbb-4222-8222-222222222222")
EMPLOYEE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
EMPTY_EMPLOYEE_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
OTHER_EMPLOYEE_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
ANNUAL_2026_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
SICK_2026_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
ANNUAL_2025_ID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
OTHER_BALANCE_ID = UUID("99999999-9999-4999-8999-999999999999")


async def _client_with_database() -> tuple[AsyncClient, AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        use_insertmanyvalues=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
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
                Employee(
                    id=EMPLOYEE_ID,
                    tenant_id=TENANT_ID,
                    employee_number="WF-001",
                    first_name="Ada",
                    last_name="Yilmaz",
                    email="ada@wealthyfalcon.test",
                    department="People",
                    position="HR Specialist",
                    status=EmployeeStatus.ACTIVE.value,
                    employment_start_date=date(2026, 1, 1),
                ),
                Employee(
                    id=EMPTY_EMPLOYEE_ID,
                    tenant_id=TENANT_ID,
                    employee_number="WF-002",
                    first_name="Ece",
                    last_name="Kaya",
                    status=EmployeeStatus.ACTIVE.value,
                    employment_start_date=date(2026, 1, 1),
                ),
                Employee(
                    id=OTHER_EMPLOYEE_ID,
                    tenant_id=OTHER_TENANT_ID,
                    employee_number="OT-001",
                    first_name="Other",
                    last_name="Person",
                    status=EmployeeStatus.ACTIVE.value,
                    employment_start_date=date(2026, 1, 1),
                ),
                LeaveBalanceSummary(
                    id=ANNUAL_2026_ID,
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type="annual",
                    period_year=2026,
                    opening_balance_days=20.0,
                    used_days=5.0,
                    planned_days=2.0,
                ),
                LeaveBalanceSummary(
                    id=SICK_2026_ID,
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type="sick",
                    period_year=2026,
                    opening_balance_days=8.0,
                    used_days=1.5,
                    planned_days=0.5,
                ),
                LeaveBalanceSummary(
                    id=ANNUAL_2025_ID,
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type="annual",
                    period_year=2025,
                    opening_balance_days=10.0,
                    used_days=4.0,
                    planned_days=0.0,
                ),
                LeaveBalanceSummary(
                    id=OTHER_BALANCE_ID,
                    tenant_id=OTHER_TENANT_ID,
                    employee_id=OTHER_EMPLOYEE_ID,
                    leave_type="annual",
                    period_year=2026,
                    opening_balance_days=99.0,
                    used_days=0.0,
                    planned_days=0.0,
                ),
            ]
        )
        await session.commit()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session

    return (
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ),
        engine,
    )


def _tenant_headers(tenant_id: UUID = TENANT_ID) -> dict[str, str]:
    return {"X-Tenant-Id": str(tenant_id)}


def _assert_error_response(
    response,
    *,
    status_code: int,
    code: str,
    message: str,
    correlation_id: str | None = None,
) -> None:
    assert response.status_code == status_code
    assert response.json() == {
        "error": {
            "code": code,
            "message": message,
            "details": None,
            "correlation_id": correlation_id,
        }
    }


async def test_list_employee_leave_balances_returns_manual_placeholder_summaries() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/leave-balances",
            headers=_tenant_headers(),
        )

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body] == [
            str(ANNUAL_2026_ID),
            str(SICK_2026_ID),
            str(ANNUAL_2025_ID),
        ]
        assert body[0] == {
            "id": str(ANNUAL_2026_ID),
            "employee_id": str(EMPLOYEE_ID),
            "leave_type": "annual",
            "period_year": 2026,
            "opening_balance_days": 20.0,
            "used_days": 5.0,
            "planned_days": 2.0,
            "remaining_days": 13.0,
            "calculation_mode": "manual_placeholder",
            "external_integration_enabled": False,
        }
        assert "tenant_id" not in body[0]
        assert str(OTHER_BALANCE_ID) not in {item["id"] for item in body}
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employee_leave_balances_filters_by_period_year() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/leave-balances",
            headers=_tenant_headers(),
            params={"period_year": 2025},
        )

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body] == [str(ANNUAL_2025_ID)]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employee_leave_balances_returns_empty_list_for_employee_without_rows() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            f"/api/v1/employees/{EMPTY_EMPLOYEE_ID}/leave-balances",
            headers=_tenant_headers(),
        )

        assert response.status_code == 200
        assert response.json() == []
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employee_leave_balances_rejects_cross_tenant_employee() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            f"/api/v1/employees/{OTHER_EMPLOYEE_ID}/leave-balances",
            headers=_tenant_headers(),
        )

        _assert_error_response(
            response,
            status_code=404,
            code="employee_not_found",
            message="Employee not found",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employee_leave_balances_rejects_invalid_period_year_envelope() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/leave-balances",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": "w2a6-leave-balance-validation",
            },
            params={"period_year": 1800},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_balance_validation_error",
            message="Leave balance request validation failed",
            correlation_id="w2a6-leave-balance-validation",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_leave_balance_path_validation_uses_standard_error_envelope() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees/not-a-uuid/leave-balances",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": "w3a6-leave-balance-path-validation",
            },
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_balance_validation_error",
            message="Leave balance request validation failed",
            correlation_id="w3a6-leave-balance-path-validation",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_leave_balance_routes_require_tenant_header() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(f"/api/v1/employees/{EMPLOYEE_ID}/leave-balances")

        _assert_error_response(
            response,
            status_code=400,
            code="tenant_header_missing",
            message="X-Tenant-Id header is required",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_leave_balance_route_is_exposed_in_openapi() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get("/openapi.json")

        assert response.status_code == 200
        paths = response.json()["paths"]
        path = "/api/v1/employees/{employee_id}/leave-balances"
        assert path in paths
        assert "period_year" in {
            parameter["name"] for parameter in paths[path]["get"]["parameters"]
        }
    finally:
        await client.aclose()
        await engine.dispose()
