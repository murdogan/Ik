from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.employee import Employee, EmployeeStatus
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.schemas.leave_request import LEAVE_REQUEST_LIST_DEFAULT_LIMIT
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
SECOND_EMPLOYEE_ID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
OTHER_EMPLOYEE_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
REQUESTING_USER_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
APPROVER_USER_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
OTHER_USER_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
PENDING_REQUEST_ID = UUID("aaaaaaaa-1111-4aaa-8aaa-aaaaaaaa1111")
APPROVED_REQUEST_ID = UUID("bbbbbbbb-2222-4bbb-8bbb-bbbbbbbb2222")
REJECTED_REQUEST_ID = UUID("cccccccc-4444-4ccc-8ccc-cccccccc4444")
OTHER_REQUEST_ID = UUID("dddddddd-3333-4ddd-8ddd-dddddddd3333")
NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)


async def _client_with_database(
    extra_current_leave_request_count: int = 0,
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
            User(
                id=REQUESTING_USER_ID,
                tenant_id=TENANT_ID,
                email="requester@wealthyfalcon.test",
                full_name="Requesting User",
                status=UserStatus.ACTIVE.value,
            ),
            User(
                id=APPROVER_USER_ID,
                tenant_id=TENANT_ID,
                email="approver@wealthyfalcon.test",
                full_name="Approver User",
                status=UserStatus.ACTIVE.value,
            ),
            User(
                id=OTHER_USER_ID,
                tenant_id=OTHER_TENANT_ID,
                email="other@wealthyfalcon.test",
                full_name="Other User",
                status=UserStatus.ACTIVE.value,
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
                id=OTHER_EMPLOYEE_ID,
                tenant_id=OTHER_TENANT_ID,
                employee_number="OT-001",
                first_name="Other",
                last_name="Person",
                status=EmployeeStatus.ACTIVE.value,
                employment_start_date=date(2026, 7, 1),
            ),
            Employee(
                id=SECOND_EMPLOYEE_ID,
                tenant_id=TENANT_ID,
                employee_number="WF-002",
                first_name="Ece",
                last_name="Kaya",
                email="ece@wealthyfalcon.test",
                department="Engineering",
                position="Backend Engineer",
                status=EmployeeStatus.ACTIVE.value,
                employment_start_date=date(2026, 7, 1),
            ),
            LeaveRequest(
                id=PENDING_REQUEST_ID,
                tenant_id=TENANT_ID,
                employee_id=EMPLOYEE_ID,
                leave_type="annual",
                start_date=date(2026, 7, 20),
                end_date=date(2026, 7, 22),
                status=LeaveRequestStatus.PENDING.value,
                requested_by_user_id=REQUESTING_USER_ID,
                created_at=NOW - timedelta(hours=1),
            ),
            LeaveRequest(
                id=APPROVED_REQUEST_ID,
                tenant_id=TENANT_ID,
                employee_id=EMPLOYEE_ID,
                leave_type="sick",
                start_date=date(2026, 7, 10),
                end_date=date(2026, 7, 10),
                status=LeaveRequestStatus.APPROVED.value,
                requested_by_user_id=REQUESTING_USER_ID,
                decided_by_user_id=APPROVER_USER_ID,
                created_at=NOW - timedelta(hours=2),
            ),
            LeaveRequest(
                id=REJECTED_REQUEST_ID,
                tenant_id=TENANT_ID,
                employee_id=SECOND_EMPLOYEE_ID,
                leave_type="annual",
                start_date=date(2026, 7, 25),
                end_date=date(2026, 7, 26),
                status=LeaveRequestStatus.REJECTED.value,
                requested_by_user_id=REQUESTING_USER_ID,
                decided_by_user_id=APPROVER_USER_ID,
                decision_note="Coverage conflict",
                created_at=NOW - timedelta(minutes=30),
            ),
            LeaveRequest(
                id=OTHER_REQUEST_ID,
                tenant_id=OTHER_TENANT_ID,
                employee_id=OTHER_EMPLOYEE_ID,
                leave_type="annual",
                start_date=date(2026, 7, 20),
                end_date=date(2026, 7, 22),
                status=LeaveRequestStatus.PENDING.value,
                requested_by_user_id=OTHER_USER_ID,
                created_at=NOW,
            ),
        ]
        records.extend(
            LeaveRequest(
                id=uuid4(),
                tenant_id=TENANT_ID,
                employee_id=EMPLOYEE_ID,
                leave_type="annual",
                start_date=date(2026, 8, 1) + timedelta(days=index),
                end_date=date(2026, 8, 1) + timedelta(days=index),
                status=LeaveRequestStatus.PENDING.value,
                requested_by_user_id=REQUESTING_USER_ID,
                created_at=NOW - timedelta(days=1, minutes=index),
            )
            for index in range(extra_current_leave_request_count)
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


def _create_payload(
    employee_id: UUID = EMPLOYEE_ID,
    requested_by_user_id: UUID = REQUESTING_USER_ID,
) -> dict[str, str]:
    return {
        "employee_id": str(employee_id),
        "leave_type": "annual",
        "start_date": "2026-08-03",
        "end_date": "2026-08-07",
        "requested_by_user_id": str(requested_by_user_id),
    }


def _decision_payload(decided_by_user_id: UUID = APPROVER_USER_ID) -> dict[str, str]:
    return {
        "decided_by_user_id": str(decided_by_user_id),
        "decision_note": "Coverage is planned",
    }


async def test_create_leave_request_uses_tenant_header_and_pending_status() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            json=_create_payload(),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["id"]
        assert "tenant_id" not in body
        assert body["status"] == LeaveRequestStatus.PENDING.value
        assert body["employee_id"] == str(EMPLOYEE_ID)

        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            created = await session.scalar(
                select(LeaveRequest).where(LeaveRequest.id == UUID(body["id"]))
            )

        assert created is not None
        assert created.tenant_id == TENANT_ID
        assert created.status == LeaveRequestStatus.PENDING.value
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_leave_request_rejects_client_controlled_status() -> None:
    client, engine = await _client_with_database()
    try:
        payload = _create_payload()
        payload["status"] = LeaveRequestStatus.APPROVED.value

        response = await client.post(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            json=payload,
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_request_validation_error",
            message="Leave request validation failed",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_leave_request_rejects_datetime_strings_for_leave_dates() -> None:
    client, engine = await _client_with_database()
    try:
        payload = _create_payload()
        payload["start_date"] = "2026-08-03T00:00:00"

        response = await client.post(
            "/api/v1/leave-requests",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": "w2a6-leave-validation",
            },
            json=payload,
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_request_validation_error",
            message="Leave request validation failed",
            correlation_id="w2a6-leave-validation",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_leave_request_rejects_compact_leave_date_string() -> None:
    client, engine = await _client_with_database()
    try:
        payload = _create_payload()
        payload["start_date"] = "20260803"

        response = await client.post(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            json=payload,
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_request_validation_error",
            message="Leave request validation failed",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_leave_request_rejects_cross_tenant_employee() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            json=_create_payload(employee_id=OTHER_EMPLOYEE_ID),
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


async def test_create_leave_request_rejects_cross_tenant_requesting_user() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            json=_create_payload(requested_by_user_id=OTHER_USER_ID),
        )

        _assert_error_response(
            response,
            status_code=404,
            code="user_not_found",
            message="User not found",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_requests_returns_current_tenant_records_only() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get("/api/v1/leave-requests", headers=_tenant_headers())

        assert response.status_code == 200
        ids = {item["id"] for item in response.json()}
        assert ids == {
            str(PENDING_REQUEST_ID),
            str(APPROVED_REQUEST_ID),
            str(REJECTED_REQUEST_ID),
        }
        assert str(OTHER_REQUEST_ID) not in ids
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_requests_paginates_current_tenant_records() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={"limit": 1, "offset": 1},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [str(PENDING_REQUEST_ID)]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_requests_paginates_after_filters_within_current_tenant() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={"employee_id": str(EMPLOYEE_ID), "limit": 1, "offset": 1},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [str(APPROVED_REQUEST_ID)]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_requests_uses_bounded_default_limit() -> None:
    client, engine = await _client_with_database(extra_current_leave_request_count=52)
    try:
        response = await client.get("/api/v1/leave-requests", headers=_tenant_headers())

        assert response.status_code == 200
        assert len(response.json()) == LEAVE_REQUEST_LIST_DEFAULT_LIMIT
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_requests_rejects_unbounded_pagination_values() -> None:
    client, engine = await _client_with_database()
    try:
        for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
            response = await client.get(
                "/api/v1/leave-requests",
                headers=_tenant_headers(),
                params=params,
            )

            _assert_error_response(
                response,
                status_code=422,
                code="leave_request_validation_error",
                message="Leave request validation failed",
            )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_requests_filters_by_status_within_current_tenant() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={"status": LeaveRequestStatus.PENDING.value},
        )

        assert response.status_code == 200
        ids = {item["id"] for item in response.json()}
        assert ids == {str(PENDING_REQUEST_ID)}
        assert str(OTHER_REQUEST_ID) not in ids
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_requests_filters_by_employee_id_within_current_tenant() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={"employee_id": str(SECOND_EMPLOYEE_ID)},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [str(REJECTED_REQUEST_ID)]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_request_filters_remain_tenant_scoped() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={
                "employee_id": str(OTHER_EMPLOYEE_ID),
                "status": LeaveRequestStatus.PENDING.value,
            },
        )

        assert response.status_code == 200
        assert response.json() == []
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_requests_combines_status_employee_and_date_filters() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={
                "status": LeaveRequestStatus.PENDING.value,
                "employee_id": str(EMPLOYEE_ID),
                "start_date": "2026-07-21",
                "end_date": "2026-07-21",
            },
        )
        cross_tenant_response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={
                "status": LeaveRequestStatus.PENDING.value,
                "employee_id": str(OTHER_EMPLOYEE_ID),
                "start_date": "2026-07-21",
                "end_date": "2026-07-21",
            },
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [str(PENDING_REQUEST_ID)]
        assert cross_tenant_response.status_code == 200
        assert cross_tenant_response.json() == []
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_requests_filters_by_overlapping_date_range() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={"start_date": "2026-07-22", "end_date": "2026-07-24"},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [str(PENDING_REQUEST_ID)]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_requests_rejects_invalid_filter_date_range() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={"start_date": "2026-07-24", "end_date": "2026-07-20"},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_request_invalid_date_range",
            message="Leave request end_date filter must be on or after start_date",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_requests_rejects_datetime_strings_for_date_filters() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={"start_date": "2026-07-22T00:00:00", "end_date": "2026-07-24"},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_request_validation_error",
            message="Leave request validation failed",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_requests_rejects_week_date_filter_string() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={"start_date": "2026-W30-3"},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_request_validation_error",
            message="Leave request validation failed",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_approve_pending_leave_request() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            f"/api/v1/leave-requests/{PENDING_REQUEST_ID}/approve",
            headers=_tenant_headers(),
            json=_decision_payload(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == LeaveRequestStatus.APPROVED.value
        assert body["decided_by_user_id"] == str(APPROVER_USER_ID)
        assert body["decision_note"] == "Coverage is planned"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_reject_pending_leave_request_supports_decision_note() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            f"/api/v1/leave-requests/{PENDING_REQUEST_ID}/reject",
            headers=_tenant_headers(),
            json=_decision_payload(),
        )

        assert response.status_code == 200
        assert response.json()["status"] == LeaveRequestStatus.REJECTED.value
        assert response.json()["decision_note"] == "Coverage is planned"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_cancel_pending_leave_request() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            f"/api/v1/leave-requests/{PENDING_REQUEST_ID}/cancel",
            headers=_tenant_headers(),
            json=_decision_payload(),
        )

        assert response.status_code == 200
        assert response.json()["status"] == LeaveRequestStatus.CANCELLED.value
    finally:
        await client.aclose()
        await engine.dispose()


async def test_approve_non_pending_leave_request_returns_conflict() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            f"/api/v1/leave-requests/{APPROVED_REQUEST_ID}/approve",
            headers=_tenant_headers(),
            json=_decision_payload(),
        )

        _assert_error_response(
            response,
            status_code=409,
            code="leave_request_transition_conflict",
            message="Only pending leave requests can be decided",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_decision_routes_are_tenant_scoped() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            f"/api/v1/leave-requests/{OTHER_REQUEST_ID}/approve",
            headers=_tenant_headers(),
            json=_decision_payload(),
        )

        _assert_error_response(
            response,
            status_code=404,
            code="leave_request_not_found",
            message="Leave request not found",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_decision_routes_reject_cross_tenant_decider() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            f"/api/v1/leave-requests/{PENDING_REQUEST_ID}/approve",
            headers=_tenant_headers(),
            json=_decision_payload(decided_by_user_id=OTHER_USER_ID),
        )

        _assert_error_response(
            response,
            status_code=404,
            code="user_not_found",
            message="User not found",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_leave_request_rejects_invalid_date_order() -> None:
    client, engine = await _client_with_database()
    try:
        payload = _create_payload()
        payload["start_date"] = "2026-08-07"
        payload["end_date"] = "2026-08-03"

        response = await client.post(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            json=payload,
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_request_invalid_date_range",
            message="Leave end date must be on or after start date",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_leave_request_routes_require_tenant_header() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get("/api/v1/leave-requests")

        _assert_error_response(
            response,
            status_code=400,
            code="tenant_header_missing",
            message="X-Tenant-Id header is required",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_leave_request_routes_are_exposed_in_openapi() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get("/openapi.json")

        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/api/v1/leave-requests" in paths
        query_params = {
            parameter["name"]
            for parameter in paths["/api/v1/leave-requests"]["get"]["parameters"]
        }
        assert {"status", "employee_id", "start_date", "end_date", "limit", "offset"}.issubset(
            query_params
        )
        assert "/api/v1/leave-requests/{leave_request_id}/approve" in paths
        assert "/api/v1/leave-requests/{leave_request_id}/reject" in paths
        assert "/api/v1/leave-requests/{leave_request_id}/cancel" in paths
    finally:
        await client.aclose()
        await engine.dispose()
