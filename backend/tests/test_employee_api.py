from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.api.auth_dependencies import require_authenticated_session
from app.api.dependencies import (
    get_authenticated_tenant_request_context,
    get_phase0_tenant_request_context,
)
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.command_idempotency import CommandIdempotency
from app.models.employee import Employee, EmployeeStatus
from app.models.tenant import Tenant, TenantStatus
from app.platform.pagination import encode_cursor
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
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
FIRST_CREATED_AT = datetime(2026, 7, 13, 9, 0, tzinfo=UTC)
LATER_CREATED_AT = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)


async def _client_with_database(
    extra_current_employee_count: int = 0,
    *,
    permissions: tuple[str, ...] = (
        "employee:read:tenant",
        "employee:update:tenant",
    ),
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
                created_at=FIRST_CREATED_AT,
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
                created_at=FIRST_CREATED_AT,
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
                created_at=LATER_CREATED_AT,
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
                created_at=FIRST_CREATED_AT,
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
    app.dependency_overrides[get_authenticated_tenant_request_context] = (
        get_phase0_tenant_request_context
    )
    app.dependency_overrides[require_authenticated_session] = lambda: SimpleNamespace(
        user=SimpleNamespace(permissions=permissions)
    )

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
                "email": "new.employee@wealthyfalcon.test",
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


async def test_employee_api_enforces_read_and_update_permissions_independently() -> None:
    read_client, read_engine = await _client_with_database(
        permissions=("employee:read:tenant",)
    )
    denied_client, denied_engine = await _client_with_database(permissions=())
    try:
        assert (
            await read_client.get("/api/v1/employees", headers=_tenant_headers())
        ).status_code == 200
        read_only_create = await read_client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "employee_number": "WF-READ-ONLY",
                "first_name": "Read",
                "last_name": "Only",
                "employment_start_date": "2026-07-08",
            },
        )
        assert read_only_create.status_code == 403
        assert read_only_create.json()["error"]["code"] == "authorization_denied"

        denied_read = await denied_client.get(
            "/api/v1/employees", headers=_tenant_headers()
        )
        denied_create = await denied_client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "employee_number": "WF-DENIED",
                "first_name": "Denied",
                "last_name": "Actor",
                "employment_start_date": "2026-07-08",
            },
        )
        assert denied_read.status_code == 403
        assert denied_create.status_code == 403
    finally:
        await read_client.aclose()
        await read_engine.dispose()
        await denied_client.aclose()
        await denied_engine.dispose()


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


async def test_create_employee_rejects_terminated_lifecycle_without_end_date() -> None:
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
            },
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


async def test_employee_routes_prioritize_tenant_header_error_over_payload_validation() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers={"X-Correlation-Id": "w4a6-employee-tenant-first"},
            json={},
        )

        _assert_error_response(
            response,
            status_code=400,
            code="tenant_header_missing",
            message="X-Tenant-Id header is required",
            correlation_id="w4a6-employee-tenant-first",
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


async def test_create_employee_rejects_numeric_employment_date() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "employee_number": "WF-002",
                "first_name": "Bora",
                "last_name": "Demir",
                "employment_start_date": 0,
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


async def test_list_employees_exposes_lifecycle_fields_for_supported_statuses() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get("/api/v1/employees", headers=_tenant_headers())

        assert response.status_code == 200
        employees_by_number = {
            employee["employee_number"]: employee for employee in response.json()
        }
        assert employees_by_number["WF-001"]["status"] == EmployeeStatus.ACTIVE.value
        assert employees_by_number["WF-001"]["employment_start_date"] == "2026-07-01"
        assert employees_by_number["WF-001"]["employment_end_date"] is None
        assert employees_by_number["WF-010"]["status"] == EmployeeStatus.ON_LEAVE.value
        assert employees_by_number["WF-010"]["employment_start_date"] == "2026-07-02"
        assert employees_by_number["WF-010"]["employment_end_date"] is None
        assert employees_by_number["WF-020"]["status"] == EmployeeStatus.TERMINATED.value
        assert employees_by_number["WF-020"]["employment_start_date"] == "2026-07-03"
        assert employees_by_number["WF-020"]["employment_end_date"] == "2026-07-31"
        assert all("tenant_id" not in employee for employee in employees_by_number.values())
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


async def test_list_employees_validates_structured_assignment_filter_ids() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"department_id": "not-a-uuid"},
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


async def test_list_employees_exposes_deterministic_id_cursor_with_array_body() -> None:
    client, engine = await _client_with_database()
    try:
        first_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"limit": 1},
        )

        assert first_response.status_code == 200
        assert [employee["id"] for employee in first_response.json()] == [str(EMPLOYEE_ID)]
        first_cursor = first_response.headers["X-Next-Cursor"]

        second_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"limit": 1, "cursor": first_cursor},
        )

        assert second_response.status_code == 200
        assert [employee["id"] for employee in second_response.json()] == [
            str(ON_LEAVE_EMPLOYEE_ID)
        ]
        second_cursor = second_response.headers["X-Next-Cursor"]

        final_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"limit": 1, "cursor": second_cursor},
        )

        assert final_response.status_code == 200
        assert [employee["id"] for employee in final_response.json()] == [
            str(TERMINATED_EMPLOYEE_ID)
        ]
        assert "X-Next-Cursor" not in final_response.headers
    finally:
        await client.aclose()
        await engine.dispose()


async def test_employee_cursor_does_not_skip_unseen_employee_after_number_update() -> None:
    client, engine = await _client_with_database()
    try:
        first_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"limit": 1},
        )
        assert first_response.status_code == 200
        assert [employee["id"] for employee in first_response.json()] == [
            str(EMPLOYEE_ID)
        ]
        first_cursor = first_response.headers["X-Next-Cursor"]

        update_response = await client.patch(
            f"/api/v1/employees/{ON_LEAVE_EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"employee_number": "WF-000"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["employee_number"] == "WF-000"

        second_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"limit": 1, "cursor": first_cursor},
        )
        assert second_response.status_code == 200
        assert [employee["id"] for employee in second_response.json()] == [
            str(ON_LEAVE_EMPLOYEE_ID)
        ]
        second_cursor = second_response.headers["X-Next-Cursor"]

        final_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"limit": 1, "cursor": second_cursor},
        )
        assert final_response.status_code == 200
        assert [employee["id"] for employee in final_response.json()] == [
            str(TERMINATED_EMPLOYEE_ID)
        ]
        assert "X-Next-Cursor" not in final_response.headers
    finally:
        await client.aclose()
        await engine.dispose()


async def test_employee_cursor_does_not_duplicate_seen_employee_after_number_update() -> None:
    client, engine = await _client_with_database()
    try:
        first_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"limit": 1},
        )
        assert first_response.status_code == 200
        assert [employee["id"] for employee in first_response.json()] == [
            str(EMPLOYEE_ID)
        ]
        first_cursor = first_response.headers["X-Next-Cursor"]

        update_response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"employee_number": "WF-005"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["employee_number"] == "WF-005"

        second_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"limit": 1, "cursor": first_cursor},
        )
        assert second_response.status_code == 200
        assert [employee["id"] for employee in second_response.json()] == [
            str(ON_LEAVE_EMPLOYEE_ID)
        ]
        assert set(employee["id"] for employee in first_response.json()).isdisjoint(
            employee["id"] for employee in second_response.json()
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employees_rejects_invalid_cursor_and_cursor_offset_mix() -> None:
    client, engine = await _client_with_database()
    try:
        invalid_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"cursor": "not-a-cursor"},
        )
        legacy_cursor_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={
                "cursor": encode_cursor(
                    "employees",
                    {
                        "employee_number": "WF-001",
                        "id": str(EMPLOYEE_ID),
                    },
                )
            },
        )
        legacy_created_at_cursor_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={
                "cursor": encode_cursor(
                    "employees",
                    {
                        "created_at": "2026-07-13T09:00:00.000001Z",
                        "id": str(EMPLOYEE_ID),
                    },
                )
            },
        )
        wrong_resource_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={
                "cursor": encode_cursor(
                    "leave_requests",
                    {
                        "id": str(EMPLOYEE_ID),
                    },
                )
            },
        )
        first_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"limit": 1},
        )
        mixed_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={
                "cursor": first_response.headers["X-Next-Cursor"],
                "offset": 1,
            },
        )

        for response in (
            invalid_response,
            legacy_cursor_response,
            legacy_created_at_cursor_response,
            wrong_resource_response,
            mixed_response,
        ):
            _assert_error_response(
                response,
                status_code=422,
                code="employee_validation_error",
                message="Employee request validation failed",
            )
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


async def test_list_employees_cursor_is_applied_after_tenant_filters() -> None:
    client, engine = await _client_with_database()
    try:
        first_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"department": "people", "limit": 1},
        )
        first_cursor = first_response.headers["X-Next-Cursor"]
        second_response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={
                "department": "people",
                "limit": 1,
                "cursor": first_cursor,
            },
        )

        assert [employee["employee_number"] for employee in first_response.json()] == [
            "WF-001"
        ]
        assert [employee["employee_number"] for employee in second_response.json()] == [
            "WF-010"
        ]
        assert "X-Next-Cursor" not in second_response.headers
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


async def test_list_employee_department_filter_requires_exact_match() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"department": "peop"},
        )

        assert response.status_code == 200
        assert response.json() == []
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


async def test_list_employees_rejects_invalid_status_filter() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"status": "inactive"},
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


async def test_list_employee_query_treats_sql_wildcards_as_literal_text() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"q": "%"},
        )

        assert response.status_code == 200
        assert response.json() == []
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


async def test_list_employee_query_searches_full_name() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=_tenant_headers(),
            params={"q": "Demir"},
        )

        assert response.status_code == 200
        assert [employee["employee_number"] for employee in response.json()] == ["WF-010"]
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


async def test_employee_path_validation_uses_standard_error_envelope() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees/not-a-uuid",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": "w3a6-employee-path-validation",
            },
        )

        _assert_error_response(
            response,
            status_code=422,
            code="employee_validation_error",
            message="Employee request validation failed",
            correlation_id="w3a6-employee-path-validation",
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


async def test_update_employee_rejects_stale_version_with_stable_conflict() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"version": 2, "position": "People Lead"},
        )

        _assert_error_response(
            response,
            status_code=409,
            code="concurrent_write_conflict",
            message="The request conflicted with another write; retry the request",
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


async def test_update_employee_rejects_null_status_with_lifecycle_error_envelope() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": "w4a6-employee-null-status",
            },
            json={"status": None},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="employee_invalid_lifecycle",
            message="Status must not be null",
            correlation_id="w4a6-employee-null-status",
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


async def test_create_employee_rejects_duplicate_work_email_with_stable_conflict() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "employee_number": "WF-099",
                "first_name": "Duplicate",
                "last_name": "Email",
                "email": "ADA@WEALTHYFALCON.TEST",
                "employment_start_date": "2026-07-08",
            },
        )

        _assert_error_response(
            response,
            status_code=409,
            code="employee_work_email_conflict",
            message="Work email already exists for this tenant",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_employee_idempotency_replays_and_rejects_changed_payload() -> None:
    client, engine = await _client_with_database()
    payload = {
        "employee_number": "WF-IDEMPOTENT",
        "first_name": "Retry",
        "last_name": "Safe",
        "employment_start_date": "2026-07-10",
    }
    headers = {
        **_tenant_headers(),
        "X-Idempotency-Key": "employee-create-retry-001",
        "X-Correlation-Id": "p0e-employee-idempotency",
    }
    try:
        first_response = await client.post(
            "/api/v1/employees",
            headers=headers,
            json=payload,
        )
        replay_response = await client.post(
            "/api/v1/employees",
            headers=headers,
            json=payload,
        )
        mismatch_response = await client.post(
            "/api/v1/employees",
            headers=headers,
            json={**payload, "first_name": "Changed"},
        )

        assert first_response.status_code == 201
        assert replay_response.status_code == 201
        assert replay_response.json() == first_response.json()
        _assert_error_response(
            mismatch_response,
            status_code=409,
            code="idempotency_key_mismatch",
            message=(
                "X-Idempotency-Key was already used for a different request in this tenant"
            ),
            correlation_id="p0e-employee-idempotency",
        )

        async with AsyncSession(engine, expire_on_commit=False) as session:
            employee_count = await session.scalar(
                select(func.count())
                .select_from(Employee)
                .where(Employee.tenant_id == TENANT_ID)
                .where(Employee.employee_number == "WF-IDEMPOTENT")
            )
            receipt_count = await session.scalar(
                select(func.count())
                .select_from(CommandIdempotency)
                .where(CommandIdempotency.tenant_id == TENANT_ID)
                .where(
                    CommandIdempotency.idempotency_key
                    == "employee-create-retry-001"
                )
            )
        assert employee_count == 1
        assert receipt_count == 1
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_employee_rejects_repeated_idempotency_header() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=[
                ("X-Tenant-Id", str(TENANT_ID)),
                ("X-Idempotency-Key", "first-key"),
                ("X-Idempotency-Key", "second-key"),
                ("X-Correlation-Id", "p0e-idempotency-header"),
            ],
            json={
                "employee_number": "WF-HEADER",
                "first_name": "Header",
                "last_name": "Validation",
                "employment_start_date": "2026-07-10",
            },
        )
        whitespace_response = await client.post(
            "/api/v1/employees",
            headers={
                **_tenant_headers(),
                "X-Idempotency-Key": "invalid key",
                "X-Correlation-Id": "p0e-idempotency-whitespace",
            },
            json={
                "employee_number": "WF-HEADER",
                "first_name": "Header",
                "last_name": "Validation",
                "employment_start_date": "2026-07-10",
            },
        )

        _assert_error_response(
            response,
            status_code=400,
            code="idempotency_key_invalid",
            message=(
                "X-Idempotency-Key must be sent at most once and contain 1 to 128 "
                "non-whitespace characters"
            ),
            correlation_id="p0e-idempotency-header",
        )
        _assert_error_response(
            whitespace_response,
            status_code=400,
            code="idempotency_key_invalid",
            message=(
                "X-Idempotency-Key must be sent at most once and contain 1 to 128 "
                "non-whitespace characters"
            ),
            correlation_id="p0e-idempotency-whitespace",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_delete_employee_archives_current_tenant_record_idempotently() -> None:
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
        repeated_response = await client.delete(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
        )

        assert response.status_code == 204
        assert repeated_response.status_code == 204
        _assert_error_response(
            get_response,
            status_code=404,
            code="employee_not_found",
            message="Employee not found",
        )
        async with AsyncSession(engine, expire_on_commit=False) as session:
            archived_employee = await session.get(Employee, EMPLOYEE_ID)
            other_employee = await session.get(Employee, OTHER_EMPLOYEE_ID)
        assert archived_employee is not None
        assert archived_employee.archived_at is not None
        assert archived_employee.status == EmployeeStatus.ACTIVE.value
        assert other_employee is not None
        assert other_employee.archived_at is None
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


async def test_employee_routes_reject_invalid_tenant_header_before_query_validation() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers={
                "X-Tenant-Id": str(TENANT_ID).replace("-", ""),
                "X-Correlation-Id": "w4b4-employee-tenant-invalid",
            },
            params={"limit": 0},
        )

        _assert_error_response(
            response,
            status_code=400,
            code="tenant_header_invalid",
            message="X-Tenant-Id header must be a single canonical hyphenated UUID",
            correlation_id="w4b4-employee-tenant-invalid",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_employee_routes_reject_repeated_tenant_header() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/employees",
            headers=[
                ("X-Tenant-Id", str(TENANT_ID)),
                ("X-Tenant-Id", str(OTHER_TENANT_ID)),
                ("X-Correlation-Id", "w4b4-employee-tenant-repeated"),
            ],
        )

        _assert_error_response(
            response,
            status_code=400,
            code="tenant_header_invalid",
            message="X-Tenant-Id header must be a single canonical hyphenated UUID",
            correlation_id="w4b4-employee-tenant-repeated",
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
        assert {
            "department",
            "status",
            "q",
            "legal_entity_id",
            "branch_id",
            "department_id",
            "position_id",
            "limit",
            "offset",
            "cursor",
        }.issubset(
            employee_list_parameters
        )
    finally:
        await client.aclose()
        await engine.dispose()
