# ruff: noqa: E402

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
API_IMPLEMENTATION_STATUS_DOC = (
    ROOT / "docs" / "09-uygulama" / "11-api-implementation-status.md"
)
OPENAPI_ENDPOINT_DRAFT_DOC = (
    ROOT / "docs" / "09-uygulama" / "03-openapi-endpoint-taslagi.md"
)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.employee import EmployeeStatus
from app.models.leave_balance_summary import LeaveBalanceSummary
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
HTTP_METHODS = {"delete", "get", "patch", "post", "put"}
DOCUMENTED_OPENAPI_OPERATIONS = {
    ("get", "/"),
    ("get", "/health"),
    ("get", "/api/v1/dashboard/summary"),
    ("get", "/api/v1/employees"),
    ("post", "/api/v1/employees"),
    ("get", "/api/v1/employees/{employee_id}"),
    ("patch", "/api/v1/employees/{employee_id}"),
    ("delete", "/api/v1/employees/{employee_id}"),
    ("get", "/api/v1/employees/{employee_id}/leave-balances"),
    ("get", "/api/v1/leave-requests"),
    ("post", "/api/v1/leave-requests"),
    ("post", "/api/v1/leave-requests/{leave_request_id}/approve"),
    ("post", "/api/v1/leave-requests/{leave_request_id}/reject"),
    ("post", "/api/v1/leave-requests/{leave_request_id}/cancel"),
}
DOCUMENTED_RUNTIME_ENDPOINTS = {
    ("get", "/openapi.json"),
}
DOCUMENTED_SMOKE_ENDPOINTS = DOCUMENTED_OPENAPI_OPERATIONS | DOCUMENTED_RUNTIME_ENDPOINTS
DOCUMENTED_ENDPOINT_TABLES = {
    API_IMPLEMENTATION_STATUS_DOC: "## Completed API Surface",
    OPENAPI_ENDPOINT_DRAFT_DOC: "## 0. Güncel uygulama yüzeyi",
}
EXECUTED_DOCUMENTED_ENDPOINTS: set[tuple[str, str]] = set()


async def main() -> None:
    EXECUTED_DOCUMENTED_ENDPOINTS.clear()
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
            _smoke_documented_endpoint_tables()
            await _smoke_tenant_header_errors(client)
            primary_employee_id, secondary_employee_id, other_employee_id = (
                await _smoke_employee_endpoints(client)
            )
            leave_request_ids = await _smoke_leave_request_endpoints(
                client,
                primary_employee_id,
                secondary_employee_id,
                other_employee_id,
            )
            await _smoke_leave_balance_endpoint(
                client,
                session_factory,
                primary_employee_id,
                secondary_employee_id,
                other_employee_id,
            )
            await _smoke_dashboard_endpoint(
                client,
                other_employee_id=other_employee_id,
                other_tenant_leave_request_id=leave_request_ids["other_tenant"],
            )
            _expect_executed_documented_endpoint_coverage()
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    print(
        "BACKEND_SMOKE_OK "
        f"tenant_id={TENANT_ID} "
        f"documented_endpoints={len(DOCUMENTED_SMOKE_ENDPOINTS)} "
        "checked=health,landing,openapi,documented_endpoint_tables,tenant_headers,"
        "documented_endpoint_runtime_coverage,dashboard_counts,employee_filters,"
        "employees,leave_balances,leave_filters,leave_requests,workflow_transitions"
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
    health = _expect_json(
        await _request_documented(client, "get", "/health"),
        200,
        "GET /health",
    )
    _assert_equal(health["status"], "ok", "health status")
    _assert_equal(health["service"], "IK Platform API", "health service")

    landing = await _request_documented(client, "get", "/")
    _expect_status(landing, 200, "GET /")
    _assert_contains(landing.text, "Wealthy Falcon HR", "landing brand")

    openapi = _expect_json(
        await _request_documented(client, "get", "/openapi.json"),
        200,
        "GET /openapi.json",
    )
    _expect_documented_openapi_operations(openapi)


def _expect_documented_openapi_operations(openapi: dict[str, Any]) -> None:
    actual_operations = {
        (method, path)
        for path, path_item in openapi["paths"].items()
        for method in path_item
        if method in HTTP_METHODS
    }
    missing_operations = sorted(DOCUMENTED_OPENAPI_OPERATIONS - actual_operations)
    undocumented_operations = sorted(actual_operations - DOCUMENTED_OPENAPI_OPERATIONS)
    if missing_operations:
        raise AssertionError(
            "OpenAPI is missing documented operations: "
            f"{_format_operations(missing_operations)}"
        )
    if undocumented_operations:
        raise AssertionError(
            "OpenAPI has operations missing from backend smoke documentation: "
            f"{_format_operations(undocumented_operations)}"
        )


def _smoke_documented_endpoint_tables() -> None:
    for doc_path, heading in DOCUMENTED_ENDPOINT_TABLES.items():
        _expect_documented_endpoint_table(doc_path, heading)


def _expect_documented_endpoint_table(doc_path: Path, heading: str) -> None:
    section = _read_markdown_section(doc_path, heading)
    actual_endpoints = _parse_markdown_endpoint_table(section)
    missing_endpoints = sorted(DOCUMENTED_SMOKE_ENDPOINTS - actual_endpoints)
    extra_endpoints = sorted(actual_endpoints - DOCUMENTED_SMOKE_ENDPOINTS)
    if missing_endpoints:
        raise AssertionError(
            f"{doc_path} is missing smoke-documented endpoints under {heading}: "
            f"{_format_operations(missing_endpoints)}"
        )
    if extra_endpoints:
        raise AssertionError(
            f"{doc_path} lists endpoints missing from backend smoke coverage under {heading}: "
            f"{_format_operations(extra_endpoints)}"
        )


async def _request_documented(
    client: AsyncClient,
    method: str,
    path: str,
    *,
    documented_path: str | None = None,
    **kwargs: Any,
) -> Response:
    response = await client.request(method.upper(), path, **kwargs)
    _record_documented_endpoint(method, documented_path or path)
    return response


def _record_documented_endpoint(method: str, path: str) -> None:
    operation = (method.lower(), path)
    if operation not in DOCUMENTED_SMOKE_ENDPOINTS:
        raise AssertionError(
            "Smoke tried to record an endpoint outside documented coverage: "
            f"{_format_operations([operation])}"
        )
    EXECUTED_DOCUMENTED_ENDPOINTS.add(operation)


def _expect_executed_documented_endpoint_coverage() -> None:
    missing_endpoints = sorted(DOCUMENTED_SMOKE_ENDPOINTS - EXECUTED_DOCUMENTED_ENDPOINTS)
    if missing_endpoints:
        raise AssertionError(
            "Backend smoke did not execute documented endpoints: "
            f"{_format_operations(missing_endpoints)}"
        )


def _read_markdown_section(doc_path: Path, heading: str) -> list[str]:
    lines = doc_path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError as exc:
        raise AssertionError(f"{doc_path} is missing heading {heading!r}") from exc

    heading_level = len(heading) - len(heading.lstrip("#"))
    section: list[str] = []
    for line in lines[start:]:
        if line.startswith("#"):
            line_level = len(line) - len(line.lstrip("#"))
            if line_level <= heading_level:
                break
        section.append(line)
    return section


def _parse_markdown_endpoint_table(lines: list[str]) -> set[tuple[str, str]]:
    endpoints: set[tuple[str, str]] = set()
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        method = cells[0].lower()
        path = cells[1]
        if method in HTTP_METHODS and path.startswith("/"):
            endpoints.add((method, path))
    return endpoints


async def _smoke_tenant_header_errors(client: AsyncClient) -> None:
    _expect_error_code(
        await client.get(
            "/api/v1/dashboard/summary",
            headers={"X-Correlation-Id": "smoke-tenant-missing"},
        ),
        400,
        "tenant_header_missing",
        "GET /api/v1/dashboard/summary missing tenant header",
    )
    _expect_error_code(
        await client.get(
            "/api/v1/dashboard/summary",
            headers={
                "X-Tenant-Id": str(TENANT_ID).replace("-", ""),
                "X-Correlation-Id": "smoke-tenant-invalid",
            },
        ),
        400,
        "tenant_header_invalid",
        "GET /api/v1/dashboard/summary invalid tenant header",
    )
    _expect_error_code(
        await client.get(
            "/api/v1/dashboard/summary",
            headers=[
                ("X-Tenant-Id", str(TENANT_ID)),
                ("X-Tenant-Id", str(OTHER_TENANT_ID)),
                ("X-Correlation-Id", "smoke-tenant-repeated"),
            ],
        ),
        400,
        "tenant_header_invalid",
        "GET /api/v1/dashboard/summary repeated tenant header",
    )


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
        await _request_documented(
            client,
            "get",
            "/api/v1/employees",
            headers=TENANT_HEADERS,
        ),
        200,
        "GET /api/v1/employees",
    )
    _assert_equal(
        [employee["employee_number"] for employee in employees],
        ["WF-SMOKE-001", "WF-SMOKE-002"],
        "employee list tenant scope",
    )

    blank_filter_employees = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"department": "   ", "q": "   "},
        ),
        200,
        "GET /api/v1/employees blank filters",
    )
    _assert_equal(
        [employee["employee_number"] for employee in blank_filter_employees],
        ["WF-SMOKE-001", "WF-SMOKE-002"],
        "employee blank filters are ignored",
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
    partial_department_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"department": "peop"},
        ),
        200,
        "GET /api/v1/employees?department=peop",
    )
    _assert_equal(
        partial_department_filtered,
        [],
        "employee department filter requires exact match",
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
    trimmed_department_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"department": " People "},
        ),
        200,
        "GET /api/v1/employees?department=%20People%20",
    )
    _assert_equal(
        [employee["employee_number"] for employee in trimmed_department_filtered],
        ["WF-SMOKE-001"],
        "employee department filter trims whitespace",
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
    trimmed_search_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"q": " ADA.SMOKE "},
        ),
        200,
        "GET /api/v1/employees?q=%20ADA.SMOKE%20",
    )
    _assert_equal(
        [employee["employee_number"] for employee in trimmed_search_filtered],
        ["WF-SMOKE-001"],
        "employee q filter trims whitespace",
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

    wildcard_search_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"q": "%"},
        ),
        200,
        "GET /api/v1/employees?q=%25",
    )
    _assert_equal(
        wildcard_search_filtered,
        [],
        "employee q filter treats SQL wildcard as literal text",
    )
    name_search_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"q": "Yilmaz"},
        ),
        200,
        "GET /api/v1/employees?q=Yilmaz",
    )
    _assert_equal(
        name_search_filtered,
        [],
        "employee q filter does not search names",
    )

    detail = _expect_json(
        await _request_documented(
            client,
            "get",
            f"/api/v1/employees/{employee_id}",
            documented_path="/api/v1/employees/{employee_id}",
            headers=TENANT_HEADERS,
        ),
        200,
        "GET /api/v1/employees/{employee_id}",
    )
    _assert_equal(detail["employee_number"], "WF-SMOKE-001", "employee detail number")

    updated = _expect_json(
        await _request_documented(
            client,
            "patch",
            f"/api/v1/employees/{employee_id}",
            documented_path="/api/v1/employees/{employee_id}",
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
    _expect_error_code(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"status": "disabled"},
        ),
        422,
        "employee_validation_error",
        "GET /api/v1/employees?status=disabled",
    )
    for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
        _expect_error_code(
            await client.get(
                "/api/v1/employees",
                headers=TENANT_HEADERS,
                params=params,
            ),
            422,
            "employee_validation_error",
            "GET /api/v1/employees invalid pagination",
        )
    combined_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={
                "department": "people",
                "status": EmployeeStatus.ON_LEAVE.value,
                "q": "WF-SMOKE-001",
            },
        ),
        200,
        "GET /api/v1/employees combined filters",
    )
    _assert_equal(
        [employee["employee_number"] for employee in combined_filtered],
        ["WF-SMOKE-001"],
        "employee combined filters",
    )
    conflicting_combined_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={
                "department": "engineering",
                "status": EmployeeStatus.ON_LEAVE.value,
                "q": "WF-SMOKE-001",
            },
        ),
        200,
        "GET /api/v1/employees conflicting combined filters",
    )
    _assert_equal(
        conflicting_combined_filtered,
        [],
        "employee conflicting combined filters",
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
        await _request_documented(
            client,
            "delete",
            f"/api/v1/employees/{delete_candidate['id']}",
            documented_path="/api/v1/employees/{employee_id}",
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

    terminated = await _create_employee(
        client,
        {
            "employee_number": "WF-SMOKE-TERMINATED",
            "first_name": "Terminated",
            "last_name": "Employee",
            "department": "People",
            "position": "Former HR Specialist",
            "status": EmployeeStatus.TERMINATED.value,
            "employment_start_date": today,
            "employment_end_date": today,
        },
    )
    terminated_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"status": EmployeeStatus.TERMINATED.value},
        ),
        200,
        "GET /api/v1/employees?status=terminated",
    )
    _assert_equal(
        [employee["id"] for employee in terminated_filtered],
        [terminated["id"]],
        "employee terminated status filter",
    )

    return employee_id, secondary_employee_id, other_employee_id


async def _smoke_leave_balance_endpoint(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    employee_id: str,
    secondary_employee_id: str,
    other_employee_id: str,
) -> None:
    period_year = date.today().year
    balance_id = uuid4()
    other_balance_id = uuid4()
    async with session_factory() as session:
        session.add_all(
            [
                LeaveBalanceSummary(
                    id=balance_id,
                    tenant_id=TENANT_ID,
                    employee_id=UUID(employee_id),
                    leave_type="annual",
                    period_year=period_year,
                    opening_balance_days=20.0,
                    used_days=5.0,
                    planned_days=2.0,
                ),
                LeaveBalanceSummary(
                    id=other_balance_id,
                    tenant_id=OTHER_TENANT_ID,
                    employee_id=UUID(other_employee_id),
                    leave_type="annual",
                    period_year=period_year,
                    opening_balance_days=99.0,
                    used_days=0.0,
                    planned_days=0.0,
                ),
            ]
        )
        await session.commit()

    balances = _expect_json(
        await _request_documented(
            client,
            "get",
            f"/api/v1/employees/{employee_id}/leave-balances",
            documented_path="/api/v1/employees/{employee_id}/leave-balances",
            headers=TENANT_HEADERS,
            params={"period_year": period_year},
        ),
        200,
        "GET /api/v1/employees/{employee_id}/leave-balances",
    )
    _assert_equal(len(balances), 1, "leave balance summary count")
    _assert_equal(balances[0]["id"], str(balance_id), "leave balance summary id")
    _assert_equal(balances[0]["remaining_days"], 13.0, "leave balance remaining_days")
    _assert_equal(
        balances[0]["calculation_mode"],
        "manual_placeholder",
        "leave balance calculation_mode",
    )
    _assert_equal(
        balances[0]["external_integration_enabled"],
        False,
        "leave balance external integration flag",
    )
    if "tenant_id" in balances[0]:
        raise AssertionError("leave balance summary leaked tenant_id")

    synthetic_balances = _expect_json(
        await client.get(
            f"/api/v1/employees/{secondary_employee_id}/leave-balances",
            headers=TENANT_HEADERS,
            params={"period_year": period_year},
        ),
        200,
        "GET /api/v1/employees/{employee_id}/leave-balances with only leave requests",
    )
    _assert_equal(
        synthetic_balances,
        [],
        "leave balance does not synthesize rows from leave requests",
    )

    _expect_error_code(
        await client.get(
            f"/api/v1/employees/{other_employee_id}/leave-balances",
            headers=TENANT_HEADERS,
        ),
        404,
        "employee_not_found",
        "GET cross-tenant /api/v1/employees/{employee_id}/leave-balances",
    )


async def _smoke_leave_request_endpoints(
    client: AsyncClient,
    employee_id: str,
    secondary_employee_id: str,
    other_employee_id: str,
) -> dict[str, str]:
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

    decision_note = "W3B2 backend smoke decision"
    decision_payload = {
        "decided_by_user_id": str(APPROVER_USER_ID),
        "decision_note": decision_note,
    }
    approved = _expect_json(
        await _request_documented(
            client,
            "post",
            f"/api/v1/leave-requests/{approved_request['id']}/approve",
            documented_path="/api/v1/leave-requests/{leave_request_id}/approve",
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
        decision_note,
        "approved leave decision note",
    )

    rejected = _expect_json(
        await _request_documented(
            client,
            "post",
            f"/api/v1/leave-requests/{rejected_request['id']}/reject",
            documented_path="/api/v1/leave-requests/{leave_request_id}/reject",
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
    _assert_equal(
        rejected["decided_by_user_id"],
        str(APPROVER_USER_ID),
        "rejected leave decider",
    )
    _assert_equal(
        rejected["decision_note"],
        decision_note,
        "rejected leave decision note",
    )

    cancelled = _expect_json(
        await _request_documented(
            client,
            "post",
            f"/api/v1/leave-requests/{cancelled_request['id']}/cancel",
            documented_path="/api/v1/leave-requests/{leave_request_id}/cancel",
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
    _assert_equal(
        cancelled["decided_by_user_id"],
        str(APPROVER_USER_ID),
        "cancelled leave decider",
    )
    _assert_equal(
        cancelled["decision_note"],
        decision_note,
        "cancelled leave decision note",
    )

    await _expect_leave_request_transition_conflicts(
        client,
        decision_payload=decision_payload,
        request_ids_by_status={
            LeaveRequestStatus.APPROVED.value: approved_request["id"],
            LeaveRequestStatus.REJECTED.value: rejected_request["id"],
            LeaveRequestStatus.CANCELLED.value: cancelled_request["id"],
        },
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
        await _request_documented(
            client,
            "get",
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
        ),
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

    for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
        _expect_error_code(
            await client.get(
                "/api/v1/leave-requests",
                headers=TENANT_HEADERS,
                params=params,
            ),
            422,
            "leave_request_validation_error",
            "GET /api/v1/leave-requests invalid pagination",
        )

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
    for status_value, expected_id in (
        (LeaveRequestStatus.REJECTED.value, rejected_request["id"]),
        (LeaveRequestStatus.CANCELLED.value, cancelled_request["id"]),
    ):
        status_filtered = _expect_json(
            await client.get(
                "/api/v1/leave-requests",
                headers=TENANT_HEADERS,
                params={"status": status_value},
            ),
            200,
            f"GET /api/v1/leave-requests?status={status_value}",
        )
        _assert_equal(
            [leave_request["id"] for leave_request in status_filtered],
            [expected_id],
            f"leave request {status_value} status filter",
        )
    _expect_error_code(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"status": "archived"},
        ),
        422,
        "leave_request_validation_error",
        "GET /api/v1/leave-requests?status=archived",
    )
    _expect_error_code(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"employee_id": "not-a-uuid"},
        ),
        422,
        "leave_request_validation_error",
        "GET /api/v1/leave-requests?employee_id=not-a-uuid",
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
    employee_filtered_page = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"employee_id": employee_id, "limit": 1, "offset": 1},
        ),
        200,
        "GET /api/v1/leave-requests?employee_id=<employee_id>&limit=1&offset=1",
    )
    _assert_equal(len(employee_filtered_page), 1, "leave request filtered pagination size")
    employee_filter_ids = {
        approved_request["id"],
        rejected_request["id"],
        cancelled_request["id"],
    }
    if employee_filtered_page[0]["id"] not in employee_filter_ids:
        raise AssertionError("leave request filtered pagination returned wrong employee")
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
    combined_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={
                "status": LeaveRequestStatus.APPROVED.value,
                "employee_id": employee_id,
                "start_date": approved_request["start_date"],
                "end_date": approved_request["end_date"],
            },
        ),
        200,
        "GET /api/v1/leave-requests combined filters",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in combined_filtered],
        [approved_request["id"]],
        "leave request combined filters",
    )
    conflicting_combined_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={
                "status": LeaveRequestStatus.PENDING.value,
                "employee_id": employee_id,
                "start_date": approved_request["start_date"],
                "end_date": cancelled_request["end_date"],
            },
        ),
        200,
        "GET /api/v1/leave-requests conflicting combined filters",
    )
    _assert_equal(
        conflicting_combined_filtered,
        [],
        "leave request conflicting combined filters",
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
    start_only_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"start_date": cancelled_request["start_date"]},
        ),
        200,
        "GET /api/v1/leave-requests?start_date=<date>",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in start_only_filtered],
        [cancelled_request["id"]],
        "leave request start_date-only filter",
    )
    end_only_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"end_date": pending_request["end_date"]},
        ),
        200,
        "GET /api/v1/leave-requests?end_date=<date>",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in end_only_filtered],
        [pending_request["id"]],
        "leave request end_date-only filter",
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
    _expect_error_code(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={
                "start_date": rejected_request["end_date"],
                "end_date": rejected_request["start_date"],
            },
        ),
        422,
        "leave_request_invalid_date_range",
        "GET /api/v1/leave-requests invalid date range",
    )
    _expect_error_code(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"start_date": "2026-07-22T00:00:00"},
        ),
        422,
        "leave_request_validation_error",
        "GET /api/v1/leave-requests invalid date filter",
    )

    return {
        "pending": pending_request["id"],
        "approved": approved_request["id"],
        "rejected": rejected_request["id"],
        "cancelled": cancelled_request["id"],
        "other_tenant": other_tenant_request["id"],
    }


async def _expect_leave_request_transition_conflicts(
    client: AsyncClient,
    *,
    decision_payload: dict[str, str],
    request_ids_by_status: dict[str, str],
) -> None:
    for source_status, leave_request_id in request_ids_by_status.items():
        for action in ("approve", "reject", "cancel"):
            _expect_error_code(
                await client.post(
                    f"/api/v1/leave-requests/{leave_request_id}/{action}",
                    headers=TENANT_HEADERS,
                    json=decision_payload,
                ),
                409,
                "leave_request_transition_conflict",
                (
                    "POST "
                    f"{source_status} /api/v1/leave-requests/"
                    f"{{leave_request_id}}/{action}"
                ),
            )


async def _smoke_dashboard_endpoint(
    client: AsyncClient,
    *,
    other_employee_id: str,
    other_tenant_leave_request_id: str,
) -> None:
    summary = _expect_json(
        await _request_documented(
            client,
            "get",
            "/api/v1/dashboard/summary",
            headers=TENANT_HEADERS,
        ),
        200,
        "GET /api/v1/dashboard/summary",
    )
    _assert_equal(summary["active_employee_count"], 1, "dashboard active_employee_count")
    _assert_equal(summary["employee_count"], 2, "dashboard employee_count")
    _assert_equal(
        summary["employee_count"] - summary["active_employee_count"],
        1,
        "dashboard on-leave current employee count",
    )
    _assert_equal(summary["pending_leave_count"], 1, "dashboard pending_leave_count")
    _assert_equal(summary["pending_leave_requests"], 1, "dashboard pending_leave_requests")
    _assert_equal(
        summary["pending_leave_requests"],
        summary["pending_leave_count"],
        "dashboard pending leave compatibility count",
    )
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
    _assert_equal(len(summary["recent_activity"]), 5, "dashboard recent_activity count")
    supported_activity_types = {
        "employee.created",
        "leave.approved",
        "leave.cancelled",
        "leave.rejected",
        "leave.requested",
    }
    activity_types = {activity["activity_type"] for activity in summary["recent_activity"]}
    unsupported_activity_types = activity_types - supported_activity_types
    if unsupported_activity_types:
        raise AssertionError(
            f"dashboard recent_activity has unsupported types: {unsupported_activity_types}"
        )
    leaked_entity_ids = {other_employee_id, other_tenant_leave_request_id}
    if any(activity["entity_id"] in leaked_entity_ids for activity in summary["recent_activity"]):
        raise AssertionError("dashboard recent_activity leaked other tenant")

    other_summary = _expect_json(
        await client.get(
            "/api/v1/dashboard/summary",
            headers=OTHER_TENANT_HEADERS,
        ),
        200,
        "GET other tenant /api/v1/dashboard/summary",
    )
    _assert_equal(
        other_summary["active_employee_count"],
        1,
        "other dashboard active_employee_count",
    )
    _assert_equal(other_summary["employee_count"], 1, "other dashboard employee_count")
    _assert_equal(
        other_summary["employee_count"] - other_summary["active_employee_count"],
        0,
        "other dashboard on-leave current employee count",
    )
    _assert_equal(
        other_summary["pending_leave_count"],
        1,
        "other dashboard pending_leave_count",
    )
    _assert_equal(
        other_summary["pending_leave_requests"],
        1,
        "other dashboard pending_leave_requests",
    )
    _assert_equal(
        other_summary["pending_leave_requests"],
        other_summary["pending_leave_count"],
        "other dashboard pending leave compatibility count",
    )
    _assert_equal(
        other_summary["new_starters_this_month"],
        1,
        "other dashboard new_starters_this_month",
    )
    _assert_equal(
        other_summary["department_distribution"],
        [{"department": "People", "count": 1}],
        "other dashboard department_distribution",
    )
    _assert_equal(
        len(other_summary["recent_activity"]),
        2,
        "other dashboard recent_activity count",
    )
    _assert_equal(
        {activity["activity_type"] for activity in other_summary["recent_activity"]},
        {"employee.created", "leave.requested"},
        "other dashboard recent_activity types",
    )
    _assert_equal(
        {activity["entity_id"] for activity in other_summary["recent_activity"]},
        {other_employee_id, other_tenant_leave_request_id},
        "other dashboard recent_activity tenant scope",
    )


async def _create_employee(
    client: AsyncClient,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    return _expect_json(
        await _request_documented(
            client,
            "post",
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
        await _request_documented(
            client,
            "post",
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


def _format_operations(operations: list[tuple[str, str]]) -> list[str]:
    return [f"{method.upper()} {path}" for method, path in operations]


if __name__ == "__main__":
    asyncio.run(main())
