# ruff: noqa: E402

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.employee import EmployeeStatus
from app.models.leave_request import LeaveRequestStatus
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

TENANT_ID = UUID("11111111-aaaa-4111-8111-111111111111")
OTHER_TENANT_ID = UUID("44444444-dddd-4444-8444-444444444444")
REQUESTING_USER_ID = UUID("22222222-bbbb-4222-8222-222222222222")
APPROVER_USER_ID = UUID("33333333-cccc-4333-8333-333333333333")
OTHER_REQUESTING_USER_ID = UUID("55555555-eeee-4555-8555-555555555555")
TENANT_HEADERS = {
    "X-Tenant-Id": str(TENANT_ID),
    "X-Tenant-Slug": "wealthy-falcon",
}
OTHER_TENANT_HEADERS = {
    "X-Tenant-Id": str(OTHER_TENANT_ID),
    "X-Tenant-Slug": "other-falcon",
}
OPENAPI_PATHS = {
    "/",
    "/health",
    "/api/v1/dashboard/summary",
    "/api/v1/employees",
    "/api/v1/employees/{employee_id}",
    "/api/v1/leave-requests",
    "/api/v1/leave-requests/{leave_request_id}/approve",
    "/api/v1/leave-requests/{leave_request_id}/reject",
    "/api/v1/leave-requests/{leave_request_id}/cancel",
}


async def main() -> None:
    engine, session_factory = await _create_smoke_database()
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://backend-smoke.local",
        ) as client:
            await _smoke_system_endpoints(client)
            primary_employee_id, secondary_employee_id, other_employee_id = (
                await _smoke_employee_endpoints(client)
            )
            await _smoke_leave_request_endpoints(
                client,
                primary_employee_id,
                secondary_employee_id,
                other_employee_id,
            )
            await _smoke_dashboard_endpoint(client)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    print(
        "BACKEND_SMOKE_OK "
        f"tenant_id={TENANT_ID} "
        "checked=health,landing,openapi,dashboard,employees,leave_requests"
    )


async def _create_smoke_database() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
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
                    slug="other-falcon",
                    name="Other Falcon HR",
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
                    id=OTHER_REQUESTING_USER_ID,
                    tenant_id=OTHER_TENANT_ID,
                    email="requester@otherfalcon.test",
                    full_name="Other Requesting User",
                    status=UserStatus.ACTIVE.value,
                ),
            ]
        )
        await session.commit()

    return engine, session_factory


async def _smoke_system_endpoints(client: AsyncClient) -> None:
    health = _expect_json(await client.get("/health"), 200, "GET /health")
    _assert_equal(health["status"], "ok", "health status")
    _assert_equal(health["service"], "IK Platform API", "health service")

    landing = await client.get("/")
    _expect_status(landing, 200, "GET /")
    _assert_contains(landing.text, "Wealthy Falcon HR", "landing brand")

    openapi = _expect_json(await client.get("/openapi.json"), 200, "GET /openapi.json")
    missing_paths = OPENAPI_PATHS.difference(openapi["paths"])
    if missing_paths:
        raise AssertionError(f"OpenAPI is missing paths: {sorted(missing_paths)}")


async def _smoke_employee_endpoints(client: AsyncClient) -> tuple[str, str, str]:
    today = date.today().isoformat()
    created = await _create_employee(
        client,
        {
            "employee_number": "WF-SMOKE-001",
            "first_name": "Ada",
            "last_name": "Yilmaz",
            "email": "ada.smoke@wealthyfalcon.test",
            "department": "People",
            "position": "HR Specialist",
            "employment_start_date": today,
        },
    )
    employee_id = created["id"]
    secondary = await _create_employee(
        client,
        {
            "employee_number": "WF-SMOKE-002",
            "first_name": "Ece",
            "last_name": "Kaya",
            "email": "ece.smoke@wealthyfalcon.test",
            "department": "Engineering",
            "position": "Backend Engineer",
            "employment_start_date": today,
        },
    )
    secondary_employee_id = secondary["id"]
    other_tenant_employee = await _create_employee(
        client,
        {
            "employee_number": "WF-SMOKE-001",
            "first_name": "Other",
            "last_name": "Tenant",
            "email": "cross.tenant@wealthyfalcon.test",
            "department": "People",
            "position": "Tenant Isolation Check",
            "employment_start_date": today,
        },
        headers=OTHER_TENANT_HEADERS,
    )
    other_employee_id = other_tenant_employee["id"]

    employees = _expect_json(
        await client.get("/api/v1/employees", headers=TENANT_HEADERS),
        200,
        "GET /api/v1/employees",
    )
    _assert_equal(
        [employee["employee_number"] for employee in employees],
        ["WF-SMOKE-001", "WF-SMOKE-002"],
        "employee list tenant scope",
    )

    department_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"department": "people"},
        ),
        200,
        "GET /api/v1/employees?department=people",
    )
    _assert_equal(
        [employee["employee_number"] for employee in department_filtered],
        ["WF-SMOKE-001"],
        "employee department filter",
    )
    engineering_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"department": "ENGINEERING"},
        ),
        200,
        "GET /api/v1/employees?department=ENGINEERING",
    )
    _assert_equal(
        [employee["employee_number"] for employee in engineering_filtered],
        ["WF-SMOKE-002"],
        "employee department filter is case-insensitive",
    )

    search_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"q": "ADA.SMOKE"},
        ),
        200,
        "GET /api/v1/employees?q=ADA.SMOKE",
    )
    _assert_equal(
        [employee["employee_number"] for employee in search_filtered],
        ["WF-SMOKE-001"],
        "employee q filter",
    )
    number_search_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"q": "002"},
        ),
        200,
        "GET /api/v1/employees?q=002",
    )
    _assert_equal(
        [employee["employee_number"] for employee in number_search_filtered],
        ["WF-SMOKE-002"],
        "employee q filter searches employee_number",
    )
    cross_tenant_search_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"q": "cross.tenant"},
        ),
        200,
        "GET /api/v1/employees?q=cross.tenant",
    )
    _assert_equal(cross_tenant_search_filtered, [], "employee q filter tenant scope")

    detail = _expect_json(
        await client.get(f"/api/v1/employees/{employee_id}", headers=TENANT_HEADERS),
        200,
        "GET /api/v1/employees/{employee_id}",
    )
    _assert_equal(detail["employee_number"], "WF-SMOKE-001", "employee detail number")

    updated = _expect_json(
        await client.patch(
            f"/api/v1/employees/{employee_id}",
            headers=TENANT_HEADERS,
            json={"status": EmployeeStatus.ON_LEAVE.value},
        ),
        200,
        "PATCH /api/v1/employees/{employee_id}",
    )
    _assert_equal(updated["status"], EmployeeStatus.ON_LEAVE.value, "employee status")

    status_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"status": EmployeeStatus.ON_LEAVE.value},
        ),
        200,
        "GET /api/v1/employees?status=on_leave",
    )
    _assert_equal(
        [employee["employee_number"] for employee in status_filtered],
        ["WF-SMOKE-001"],
        "employee status filter",
    )
    active_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"status": EmployeeStatus.ACTIVE.value},
        ),
        200,
        "GET /api/v1/employees?status=active",
    )
    _assert_equal(
        [employee["employee_number"] for employee in active_filtered],
        ["WF-SMOKE-002"],
        "employee active status filter",
    )

    delete_candidate = await _create_employee(
        client,
        {
            "employee_number": "WF-SMOKE-DELETE",
            "first_name": "Delete",
            "last_name": "Candidate",
            "employment_start_date": today,
        },
    )
    paginated = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"limit": 1, "offset": 2},
        ),
        200,
        "GET /api/v1/employees?limit=1&offset=2",
    )
    _assert_equal(
        [employee["employee_number"] for employee in paginated],
        ["WF-SMOKE-DELETE"],
        "employee pagination",
    )
    _expect_status(
        await client.delete(
            f"/api/v1/employees/{delete_candidate['id']}",
            headers=TENANT_HEADERS,
        ),
        204,
        "DELETE /api/v1/employees/{employee_id}",
    )
    _expect_status(
        await client.get(
            f"/api/v1/employees/{delete_candidate['id']}",
            headers=TENANT_HEADERS,
        ),
        404,
        "GET deleted /api/v1/employees/{employee_id}",
    )

    return employee_id, secondary_employee_id, other_employee_id


async def _smoke_leave_request_endpoints(
    client: AsyncClient,
    employee_id: str,
    secondary_employee_id: str,
    other_employee_id: str,
) -> None:
    pending_request = await _create_leave_request(
        client,
        secondary_employee_id,
        day_offset=7,
        leave_type="personal",
    )
    approved_request = await _create_leave_request(client, employee_id, day_offset=14)
    rejected_request = await _create_leave_request(client, employee_id, day_offset=21)
    cancelled_request = await _create_leave_request(client, employee_id, day_offset=28)
    other_tenant_request = await _create_leave_request(
        client,
        other_employee_id,
        day_offset=35,
        headers=OTHER_TENANT_HEADERS,
        requested_by_user_id=str(OTHER_REQUESTING_USER_ID),
    )

    decision_payload = {
        "decided_by_user_id": str(APPROVER_USER_ID),
        "decision_note": "W1B2 backend smoke decision",
    }
    approved = _expect_json(
        await client.post(
            f"/api/v1/leave-requests/{approved_request['id']}/approve",
            headers=TENANT_HEADERS,
            json=decision_payload,
        ),
        200,
        "POST /api/v1/leave-requests/{leave_request_id}/approve",
    )
    _assert_equal(
        approved["status"],
        LeaveRequestStatus.APPROVED.value,
        "approved leave status",
    )
    _assert_equal(
        approved["decided_by_user_id"],
        str(APPROVER_USER_ID),
        "approved leave decider",
    )
    _assert_equal(
        approved["decision_note"],
        "W1B2 backend smoke decision",
        "approved leave decision note",
    )

    rejected = _expect_json(
        await client.post(
            f"/api/v1/leave-requests/{rejected_request['id']}/reject",
            headers=TENANT_HEADERS,
            json=decision_payload,
        ),
        200,
        "POST /api/v1/leave-requests/{leave_request_id}/reject",
    )
    _assert_equal(
        rejected["status"],
        LeaveRequestStatus.REJECTED.value,
        "rejected leave status",
    )

    cancelled = _expect_json(
        await client.post(
            f"/api/v1/leave-requests/{cancelled_request['id']}/cancel",
            headers=TENANT_HEADERS,
            json=decision_payload,
        ),
        200,
        "POST /api/v1/leave-requests/{leave_request_id}/cancel",
    )
    _assert_equal(
        cancelled["status"],
        LeaveRequestStatus.CANCELLED.value,
        "cancelled leave status",
    )

    _expect_error_code(
        await client.post(
            f"/api/v1/leave-requests/{approved_request['id']}/approve",
            headers=TENANT_HEADERS,
            json=decision_payload,
        ),
        409,
        "leave_request_transition_conflict",
        "POST decided /api/v1/leave-requests/{leave_request_id}/approve",
    )
    _expect_error_code(
        await client.post(
            f"/api/v1/leave-requests/{other_tenant_request['id']}/approve",
            headers=TENANT_HEADERS,
            json=decision_payload,
        ),
        404,
        "leave_request_not_found",
        "POST cross-tenant /api/v1/leave-requests/{leave_request_id}/approve",
    )
    _expect_error_code(
        await client.post(
            f"/api/v1/leave-requests/{pending_request['id']}/approve",
            headers=TENANT_HEADERS,
            json={
                "decided_by_user_id": str(OTHER_REQUESTING_USER_ID),
                "decision_note": "Cross tenant decider",
            },
        ),
        404,
        "user_not_found",
        "POST /api/v1/leave-requests/{leave_request_id}/approve cross-tenant user",
    )

    leave_requests = _expect_json(
        await client.get("/api/v1/leave-requests", headers=TENANT_HEADERS),
        200,
        "GET /api/v1/leave-requests",
    )
    statuses = {leave_request["status"] for leave_request in leave_requests}
    _assert_equal(
        statuses,
        {
            LeaveRequestStatus.PENDING.value,
            LeaveRequestStatus.APPROVED.value,
            LeaveRequestStatus.REJECTED.value,
            LeaveRequestStatus.CANCELLED.value,
        },
        "leave request statuses",
    )
    _assert_equal(
        {leave_request["id"] for leave_request in leave_requests},
        {
            pending_request["id"],
            approved_request["id"],
            rejected_request["id"],
            cancelled_request["id"],
        },
        "leave request list tenant scope",
    )

    paginated = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"limit": 2, "offset": 1},
        ),
        200,
        "GET /api/v1/leave-requests?limit=2&offset=1",
    )
    _assert_equal(len(paginated), 2, "leave request pagination")

    approved_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"status": "approved"},
        ),
        200,
        "GET /api/v1/leave-requests?status=approved",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in approved_filtered],
        [approved_request["id"]],
        "leave request status filter",
    )
    pending_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"status": LeaveRequestStatus.PENDING.value},
        ),
        200,
        "GET /api/v1/leave-requests?status=pending",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in pending_filtered],
        [pending_request["id"]],
        "leave request pending status filter",
    )

    employee_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"employee_id": employee_id},
        ),
        200,
        "GET /api/v1/leave-requests?employee_id=<employee_id>",
    )
    _assert_equal(
        {leave_request["id"] for leave_request in employee_filtered},
        {approved_request["id"], rejected_request["id"], cancelled_request["id"]},
        "leave request employee_id filter",
    )
    secondary_employee_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"employee_id": secondary_employee_id},
        ),
        200,
        "GET /api/v1/leave-requests?employee_id=<secondary_employee_id>",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in secondary_employee_filtered],
        [pending_request["id"]],
        "leave request secondary employee_id filter",
    )
    cross_tenant_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={
                "employee_id": other_employee_id,
                "status": LeaveRequestStatus.PENDING.value,
            },
        ),
        200,
        "GET /api/v1/leave-requests?employee_id=<other_employee_id>&status=pending",
    )
    _assert_equal(cross_tenant_filtered, [], "leave request filter tenant scope")

    date_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={
                "start_date": rejected_request["start_date"],
                "end_date": rejected_request["end_date"],
            },
        ),
        200,
        "GET /api/v1/leave-requests?start_date=<date>&end_date=<date>",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in date_filtered],
        [rejected_request["id"]],
        "leave request date range filter",
    )
    overlap_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={
                "start_date": approved_request["end_date"],
                "end_date": rejected_request["start_date"],
            },
        ),
        200,
        "GET /api/v1/leave-requests overlapping date window",
    )
    _assert_equal(
        {leave_request["id"] for leave_request in overlap_filtered},
        {approved_request["id"], rejected_request["id"]},
        "leave request overlapping date range filter",
    )
    _expect_status(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={
                "start_date": rejected_request["end_date"],
                "end_date": rejected_request["start_date"],
            },
        ),
        422,
        "GET /api/v1/leave-requests invalid date range",
    )


async def _smoke_dashboard_endpoint(client: AsyncClient) -> None:
    summary = _expect_json(
        await client.get("/api/v1/dashboard/summary", headers=TENANT_HEADERS),
        200,
        "GET /api/v1/dashboard/summary",
    )
    _assert_equal(summary["active_employee_count"], 1, "dashboard active_employee_count")
    _assert_equal(summary["employee_count"], 2, "dashboard employee_count")
    _assert_equal(summary["pending_leave_count"], 1, "dashboard pending_leave_count")
    _assert_equal(summary["pending_leave_requests"], 1, "dashboard pending_leave_requests")
    _assert_equal(summary["new_starters_this_month"], 2, "dashboard new_starters_this_month")
    _assert_equal(summary["open_tasks"], 0, "dashboard open_tasks")
    _assert_equal(
        summary["department_distribution"],
        [
            {"department": "Engineering", "count": 1},
            {"department": "People", "count": 1},
        ],
        "dashboard department_distribution",
    )


async def _create_employee(
    client: AsyncClient,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    return _expect_json(
        await client.post(
            "/api/v1/employees",
            headers=headers or TENANT_HEADERS,
            json=payload,
        ),
        201,
        "POST /api/v1/employees",
    )


async def _create_leave_request(
    client: AsyncClient,
    employee_id: str,
    day_offset: int,
    *,
    headers: dict[str, str] | None = None,
    requested_by_user_id: str | None = None,
    leave_type: str = "annual",
) -> dict[str, Any]:
    start_date = date.today() + timedelta(days=day_offset)
    end_date = start_date + timedelta(days=1)
    return _expect_json(
        await client.post(
            "/api/v1/leave-requests",
            headers=headers or TENANT_HEADERS,
            json={
                "employee_id": employee_id,
                "leave_type": leave_type,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "requested_by_user_id": requested_by_user_id or str(REQUESTING_USER_ID),
            },
        ),
        201,
        "POST /api/v1/leave-requests",
    )


def _expect_json(response: Response, status_code: int, label: str) -> Any:
    _expect_status(response, status_code, label)
    return response.json()


def _expect_error_code(response: Response, status_code: int, code: str, label: str) -> None:
    body = _expect_json(response, status_code, label)
    _assert_equal(body["error"]["code"], code, f"{label} error code")


def _expect_status(response: Response, status_code: int, label: str) -> None:
    if response.status_code != status_code:
        raise AssertionError(
            f"{label} expected {status_code}, got {response.status_code}: {response.text}"
        )


def _assert_equal(actual: Any, expected: Any, label: str = "value") -> None:
    if actual != expected:
        raise AssertionError(f"{label} expected {expected!r}, got {actual!r}")


def _assert_contains(value: str, expected: str, label: str) -> None:
    if expected not in value:
        raise AssertionError(f"{label} expected to contain {expected!r}")


if __name__ == "__main__":
    asyncio.run(main())
