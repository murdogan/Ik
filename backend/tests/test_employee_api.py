from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID, uuid4

from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.employee import Employee, EmployeeStatus
from app.models.tenant import Tenant, TenantStatus
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
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
ON_LEAVE_EMPLOYEE_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
TERMINATED_EMPLOYEE_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
OTHER_EMPLOYEE_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


async def _client_with_database(
    extra_current_employee_count: int = 0,
) -> tuple[AsyncClient, AsyncEngine]:
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
        records = [
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
                employment_start_date=date(2026, 7, 1),
            ),
            Employee(
                id=ON_LEAVE_EMPLOYEE_ID,
                tenant_id=TENANT_ID,
                employee_number="WF-010",
                first_name="Bora",
                last_name="Demir",
                email="bora@wealthyfalcon.test",
                department="People",
                position="People Partner",
                status=EmployeeStatus.ON_LEAVE.value,
                employment_start_date=date(2026, 7, 2),
            ),
            Employee(
                id=TERMINATED_EMPLOYEE_ID,
                tenant_id=TENANT_ID,
                employee_number="WF-020",
                first_name="Cem",
                last_name="Kaya",
                email="cem@wealthyfalcon.test",
                department="Engineering",
                position="Backend Engineer",
                status=EmployeeStatus.TERMINATED.value,
                employment_start_date=date(2026, 7, 3),
                employment_end_date=date(2026, 7, 31),
            ),
            Employee(
                id=OTHER_EMPLOYEE_ID,
                tenant_id=OTHER_TENANT_ID,
                employee_number="OT-001",
                first_name="Other",
                last_name="Person",
                email="other@wealthyfalcon.test",
                department="People",
                status=EmployeeStatus.ACTIVE.value,
                employment_start_date=date(2026, 7, 1),
            ),
        ]
        records.extend(
            Employee(
                id=uuid4(),
                tenant_id=TENANT_ID,
                employee_number=f"WF-{100 + index:03d}",
                first_name=f"Extra{index}",
                last_name="Employee",
                status=EmployeeStatus.ACTIVE.value,
                employment_start_date=date(2026, 7, 4),
            )
            for index in range(extra_current_employee_count)
        )
        session.add_all(records)
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


async def test_create_employee_uses_tenant_header_and_server_generated_id() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "employee_number": "WF-002",
                "first_name": "Bora",
                "last_name": "Demir",
                "email": "bora@wealthyfalcon.test",
                "department": "Engineering",
                "position": "Backend Engineer",
                "employment_start_date": "2026-07-08",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["id"]
        assert "tenant_id" not in body
        assert body["employee_number"] == "WF-002"
        assert body["status"] == EmployeeStatus.ACTIVE.value

        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            created = await session.scalar(
                select(Employee).where(Employee.employee_number == "WF-002")
            )

        assert created is not None
        assert created.tenant_id == TENANT_ID
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_employee_accepts_terminated_lifecycle_with_end_date() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "employee_number": "WF-002",
                "first_name": "Bora",
                "last_name": "Demir",
                "status": EmployeeStatus.TERMINATED.value,
                "employment_start_date": "2026-07-08",
                "employment_end_date": "2026-07-31",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == EmployeeStatus.TERMINATED.value
        assert body["employment_end_date"] == "2026-07-31"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_employee_rejects_end_date_without_terminated_status() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "employee_number": "WF-002",
                "first_name": "Bora",
                "last_name": "Demir",
                "employment_start_date": "2026-07-08",
                "employment_end_date": "2026-07-31",
            },
        )

        _assert_error_response(
            response,
            status_code=422,
            code="employee_invalid_lifecycle",
            message="Employment end date is only allowed when status is terminated",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_employee_rejects_invalid_date_order_with_error_envelope() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "employee_number": "WF-002",
                "first_name": "Bora",
                "last_name": "Demir",
                "status": EmployeeStatus.TERMINATED.value,
                "employment_start_date": "2026-08-01",
                "employment_end_date": "2026-07-31",
            },
        )

        _assert_error_response(
            response,
            status_code=422,
            code="employee_invalid_date_range",
            message="Employment end date must be on or after start date",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_employee_rejects_client_controlled_tenant_id() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "tenant_id": str(OTHER_TENANT_ID),
                "employee_number": "WF-002",
                "first_name": "Bora",
                "last_name": "Demir",
                "employment_start_date": "2026-07-08",
            },
        )

        _assert_error_response(
            response,
            status_code=422,
            code="employee_validation_error",
            message="Employee request validation failed",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_employee_rejects_datetime_string_for_employment_date() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": "w2a6-employee-validation",
            },
            json={
                "employee_number": "WF-002",
                "first_name": "Bora",
                "last_name": "Demir",
                "employment_start_date": "2026-07-08T00:00:00",
            },
        )

        _assert_error_response(
            response,
            status_code=422,
            code="employee_validation_error",
            message="Employee request validation failed",
            correlation_id="w2a6-employee-validation",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_employee_rejects_compact_employment_date_string() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "employee_number": "WF-002",
                "first_name": "Bora",
                "last_name": "Demir",
                "employment_start_date": "20260708",
            },
        )

        _assert_error_response(
            response,
            status_code=422,
            code="employee_validation_error",
            message="Employee request validation failed",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employees_returns_current_tenant_records_only() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get("/api/v1/employees", headers=_tenant_headers())

        assert response.status_code == 200
        assert [employee["employee_number"] for employee in response.json()] == [
            "WF-001",
            "WF-010",
            "WF-020",
        ]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employee_blank_filter_values_are_ignored() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"department": "   ", "q": "   "},
        )

        assert response.status_code == 200
        assert [employee["employee_number"] for employee in response.json()] == [
            "WF-001",
            "WF-010",
            "WF-020",
        ]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employees_paginates_current_tenant_records() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"limit": 1, "offset": 1},
        )

        assert response.status_code == 200
        assert [employee["employee_number"] for employee in response.json()] == ["WF-010"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employees_paginates_after_filters_within_current_tenant() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"department": "people", "limit": 1, "offset": 1},
        )

        assert response.status_code == 200
        assert [employee["employee_number"] for employee in response.json()] == ["WF-010"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employees_uses_bounded_default_limit() -> None:
    client, engine = await _client_with_database(extra_current_employee_count=52)
    try:
        response = await client.get("/api/v1/employees", headers=_tenant_headers())

        assert response.status_code == 200
        assert len(response.json()) == 50
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employees_rejects_unbounded_pagination_values() -> None:
    client, engine = await _client_with_database()
    try:
        for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
            response = await client.get(
                "/api/v1/employees",
                headers=_tenant_headers(),
                params=params,
            )

            _assert_error_response(
                response,
                status_code=422,
                code="employee_validation_error",
                message="Employee request validation failed",
            )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employees_filters_by_department_within_current_tenant() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"department": "people"},
        )

        assert response.status_code == 200
        assert [employee["employee_number"] for employee in response.json()] == [
            "WF-001",
            "WF-010",
        ]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employees_filters_by_status_within_current_tenant() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"status": EmployeeStatus.ON_LEAVE.value},
        )

        assert response.status_code == 200
        assert [employee["employee_number"] for employee in response.json()] == ["WF-010"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employees_searches_employee_number_and_email() -> None:
    client, engine = await _client_with_database()
    try:
        number_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"q": "010"},
        )
        email_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"q": "CEM@WEALTHYFALCON"},
        )

        assert number_response.status_code == 200
        assert [employee["employee_number"] for employee in number_response.json()] == ["WF-010"]
        assert email_response.status_code == 200
        assert [employee["employee_number"] for employee in email_response.json()] == ["WF-020"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employee_filters_are_combined_within_current_tenant() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={
                "department": "people",
                "status": EmployeeStatus.ON_LEAVE.value,
                "q": "BORA@WEALTHYFALCON",
            },
        )

        assert response.status_code == 200
        assert [employee["employee_number"] for employee in response.json()] == ["WF-010"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employee_query_does_not_search_names() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"q": "Demir"},
        )

        assert response.status_code == 200
        assert response.json() == []
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employee_filters_remain_tenant_scoped() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"q": "other@wealthyfalcon.test"},
        )

        assert response.status_code == 200
        assert response.json() == []
    finally:
        await client.aclose()
        await engine.dispose()


async def test_get_employee_is_tenant_scoped() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
        )
        cross_tenant_response = await client.get(
            f"/api/v1/employees/{OTHER_EMPLOYEE_ID}",
            headers=_tenant_headers(),
        )

        assert response.status_code == 200
        assert response.json()["employee_number"] == "WF-001"
        _assert_error_response(
            cross_tenant_response,
            status_code=404,
            code="employee_not_found",
            message="Employee not found",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_update_employee_changes_only_current_tenant_record() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"department": "Operations", "email": None},
        )

        assert response.status_code == 200
        assert response.json()["department"] == "Operations"
        assert response.json()["email"] is None

        cross_tenant_response = await client.patch(
            f"/api/v1/employees/{OTHER_EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"department": "Operations"},
        )

        assert cross_tenant_response.status_code == 404
    finally:
        await client.aclose()
        await engine.dispose()


async def test_update_employee_rejects_duplicate_employee_number_within_tenant() -> None:
    client, engine = await _client_with_database()
    try:
        create_response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "employee_number": "WF-002",
                "first_name": "Bora",
                "last_name": "Demir",
                "employment_start_date": "2026-07-08",
            },
        )
        assert create_response.status_code == 201

        response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"employee_number": "WF-002"},
        )

        _assert_error_response(
            response,
            status_code=409,
            code="employee_number_conflict",
            message="Employee number already exists for this tenant",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_update_employee_rejects_invalid_existing_date_order_with_error_envelope() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"employment_end_date": "2026-06-30"},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="employee_invalid_date_range",
            message="Employment end date must be on or after start date",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_update_employee_rejects_start_date_after_existing_end_date() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.patch(
            f"/api/v1/employees/{TERMINATED_EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"employment_start_date": "2026-08-01"},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="employee_invalid_date_range",
            message="Employment end date must be on or after start date",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_update_employee_rejects_null_start_date() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"employment_start_date": None},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="employee_validation_error",
            message="Employee request validation failed",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_update_employee_terminates_when_status_and_end_date_are_provided() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={
                "status": EmployeeStatus.TERMINATED.value,
                "employment_end_date": "2026-07-31",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == EmployeeStatus.TERMINATED.value
        assert body["employment_end_date"] == "2026-07-31"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_update_employee_changes_active_employee_to_on_leave() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"status": EmployeeStatus.ON_LEAVE.value},
        )

        assert response.status_code == 200
        assert response.json()["status"] == EmployeeStatus.ON_LEAVE.value
        assert response.json()["employment_end_date"] is None
    finally:
        await client.aclose()
        await engine.dispose()


async def test_update_employee_rejects_terminated_status_without_end_date() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"status": EmployeeStatus.TERMINATED.value},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="employee_invalid_lifecycle",
            message="Terminated employees must have an employment end date",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_update_employee_rejects_end_date_without_terminated_status() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"employment_end_date": "2026-07-31"},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="employee_invalid_lifecycle",
            message="Employment end date is only allowed when status is terminated",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_update_employee_rejects_reactivation_without_clearing_end_date() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.patch(
            f"/api/v1/employees/{TERMINATED_EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"status": EmployeeStatus.ON_LEAVE.value},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="employee_invalid_lifecycle",
            message="Employment end date is only allowed when status is terminated",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_update_employee_allows_reactivation_when_end_date_is_cleared() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.patch(
            f"/api/v1/employees/{TERMINATED_EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"status": EmployeeStatus.ACTIVE.value, "employment_end_date": None},
        )

        assert response.status_code == 200
        assert response.json()["status"] == EmployeeStatus.ACTIVE.value
        assert response.json()["employment_end_date"] is None
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_employee_allows_same_employee_number_in_different_tenants() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(OTHER_TENANT_ID),
            json={
                "employee_number": "WF-001",
                "first_name": "Other",
                "last_name": "Duplicate",
                "employment_start_date": "2026-07-08",
            },
        )

        assert response.status_code == 201
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_employee_rejects_duplicate_employee_number_within_tenant() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers={**_tenant_headers(), "X-Correlation-Id": "w1a6-employee-error"},
            json={
                "employee_number": "WF-001",
                "first_name": "Duplicate",
                "last_name": "Person",
                "employment_start_date": "2026-07-08",
            },
        )

        _assert_error_response(
            response,
            status_code=409,
            code="employee_number_conflict",
            message="Employee number already exists for this tenant",
            correlation_id="w1a6-employee-error",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_delete_employee_hard_deletes_current_tenant_record() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.delete(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
        )
        get_response = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
        )
        cross_tenant_response = await client.delete(
            f"/api/v1/employees/{OTHER_EMPLOYEE_ID}",
            headers=_tenant_headers(),
        )

        assert response.status_code == 204
        _assert_error_response(
            get_response,
            status_code=404,
            code="employee_not_found",
            message="Employee not found",
        )
        _assert_error_response(
            cross_tenant_response,
            status_code=404,
            code="employee_not_found",
            message="Employee not found",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_employee_routes_require_tenant_header() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get("/api/v1/employees")

        _assert_error_response(
            response,
            status_code=400,
            code="tenant_header_missing",
            message="X-Tenant-Id header is required",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_employee_routes_are_exposed_in_openapi() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get("/openapi.json")

        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/api/v1/employees" in paths
        assert "/api/v1/employees/{employee_id}" in paths
        employee_list_parameters = {
            parameter["name"] for parameter in paths["/api/v1/employees"]["get"]["parameters"]
        }
        assert {"department", "status", "q", "limit", "offset"}.issubset(
            employee_list_parameters
        )
    finally:
        await client.aclose()
        await engine.dispose()
