from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid5

from app.api.auth_dependencies import require_authenticated_session
from app.api.dependencies import get_authenticated_tenant_request_context
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_profile import (
    EmployeeEmploymentProfile,
    EmployeePersonalProfile,
)
from app.models.leave import LeaveBalanceLedger, LeavePolicy, LeaveType
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.tenancy import TenantContext
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
EMPTY_EMPLOYEE_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
OTHER_EMPLOYEE_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
REQUESTING_USER_ID = UUID("77777777-7777-4777-8777-777777777777")
OTHER_REQUESTING_USER_ID = UUID("88888888-8888-4888-8888-888888888888")
ANNUAL_2026_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
SICK_2026_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
ANNUAL_2025_ID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
OTHER_BALANCE_ID = UUID("99999999-9999-4999-8999-999999999999")
LEAVE_FIXTURE_NAMESPACE = UUID("a1000000-0000-4000-8000-000000000003")
LEAVE_LEDGER_CREATED_AT = datetime(2026, 7, 1, 8, tzinfo=UTC)
LEAVE_READ_PERMISSIONS = ("leave:read:tenant", "employee:update:tenant")


def _leave_configuration(
    tenant_id: UUID,
    *codes: str,
) -> list[LeaveType | LeavePolicy]:
    rows: list[LeaveType | LeavePolicy] = []
    for code in codes:
        leave_type_id = _leave_type_id(tenant_id, code)
        rows.extend(
            (
                LeaveType(
                    id=leave_type_id,
                    tenant_id=tenant_id,
                    code=code,
                    name=code.title(),
                    description=None,
                    is_active=True,
                    version=1,
                ),
                LeavePolicy(
                    id=_leave_policy_id(tenant_id, code),
                    tenant_id=tenant_id,
                    leave_type_id=leave_type_id,
                    version=1,
                    effective_from=date(1900, 1, 1),
                    paid=False,
                    document_required=False,
                    negative_balance_allowed=False,
                    accrual_enabled=False,
                    accrual_days_per_month=Decimal("0.00"),
                    carryover_enabled=False,
                    carryover_limit_days=None,
                    created_by_user_id=None,
                    created_at=datetime(2026, 7, 1, 8, tzinfo=UTC),
                ),
            )
        )
    return rows


def _leave_type_id(tenant_id: UUID, code: str) -> UUID:
    return uuid5(LEAVE_FIXTURE_NAMESPACE, f"leave-type:{tenant_id}:{code}")


def _leave_policy_id(tenant_id: UUID, code: str) -> UUID:
    return uuid5(LEAVE_FIXTURE_NAMESPACE, f"leave-policy:{tenant_id}:{code}:1")


def _leave_balance_id(
    tenant_id: UUID,
    employee_id: UUID,
    leave_type_code: str,
    period_year: int,
) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"wealthy-falcon:leave-balance:{tenant_id}:{employee_id}:"
        f"{_leave_type_id(tenant_id, leave_type_code)}:{period_year}",
    )


def _ledger_entry(
    *,
    entry_id: UUID,
    tenant_id: UUID,
    employee_id: UUID,
    leave_type_code: str,
    period_year: int,
    entry_type: str,
    amount_days: str,
) -> LeaveBalanceLedger:
    return LeaveBalanceLedger(
        id=entry_id,
        tenant_id=tenant_id,
        employee_id=employee_id,
        leave_type_id=_leave_type_id(tenant_id, leave_type_code),
        period_year=period_year,
        entry_type=entry_type,
        amount_days=Decimal(amount_days),
        effective_date=date(period_year, 1, 1),
        reason=None,
        request_id=None,
        source_type="test_fixture",
        source_id=entry_id,
        source_key=f"test-fixture:{entry_id}",
        reversal_of_entry_id=None,
        created_by_user_id=None,
        created_at=LEAVE_LEDGER_CREATED_AT,
    )


def _authenticated_tenant_context() -> RequestContext:
    return RequestContext(
        request_id="leave-balance-test",
        trace_id="b4000000000040008000000000000001",
        tenant=TenantContext(
            tenant_id=TENANT_ID,
            slug="wealthy-falcon",
        ),
        actor_id=REQUESTING_USER_ID,
        membership_id=REQUESTING_USER_ID,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )


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
                User(
                    id=REQUESTING_USER_ID,
                    tenant_id=TENANT_ID,
                    email="requester@wealthyfalcon.test",
                    full_name="Requesting User",
                    status=UserStatus.ACTIVE.value,
                ),
                User(
                    id=OTHER_REQUESTING_USER_ID,
                    tenant_id=OTHER_TENANT_ID,
                    email="requester@other.test",
                    full_name="Other Requesting User",
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
                    status=EmployeeStatus.TERMINATED.value,
                    employment_start_date=date(2026, 1, 1),
                    employment_end_date=date(2026, 6, 30),
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
                EmployeePersonalProfile(
                    id=UUID("a5000000-0000-4000-8000-000000000001"),
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    preferred_name="Ada",
                    birth_date=None,
                    phone=None,
                ),
                EmployeeEmploymentProfile(
                    id=UUID("a5000000-0000-4000-8000-000000000002"),
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    contract_type=None,
                    work_type=None,
                ),
                *_leave_configuration(TENANT_ID, "annual", "sick"),
                *_leave_configuration(OTHER_TENANT_ID, "annual"),
                _ledger_entry(
                    entry_id=ANNUAL_2026_ID,
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type_code="annual",
                    period_year=2026,
                    entry_type="earned",
                    amount_days="20.00",
                ),
                _ledger_entry(
                    entry_id=UUID("d6000000-0000-4000-8000-000000000001"),
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type_code="annual",
                    period_year=2026,
                    entry_type="used",
                    amount_days="5.00",
                ),
                _ledger_entry(
                    entry_id=UUID("d6000000-0000-4000-8000-000000000002"),
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type_code="annual",
                    period_year=2026,
                    entry_type="planned",
                    amount_days="2.00",
                ),
                _ledger_entry(
                    entry_id=SICK_2026_ID,
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type_code="sick",
                    period_year=2026,
                    entry_type="earned",
                    amount_days="8.00",
                ),
                _ledger_entry(
                    entry_id=UUID("d6000000-0000-4000-8000-000000000003"),
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type_code="sick",
                    period_year=2026,
                    entry_type="used",
                    amount_days="1.50",
                ),
                _ledger_entry(
                    entry_id=UUID("d6000000-0000-4000-8000-000000000004"),
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type_code="sick",
                    period_year=2026,
                    entry_type="planned",
                    amount_days="0.50",
                ),
                _ledger_entry(
                    entry_id=ANNUAL_2025_ID,
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type_code="annual",
                    period_year=2025,
                    entry_type="earned",
                    amount_days="10.00",
                ),
                _ledger_entry(
                    entry_id=UUID("d6000000-0000-4000-8000-000000000005"),
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type_code="annual",
                    period_year=2025,
                    entry_type="used",
                    amount_days="4.00",
                ),
                _ledger_entry(
                    entry_id=OTHER_BALANCE_ID,
                    tenant_id=OTHER_TENANT_ID,
                    employee_id=OTHER_EMPLOYEE_ID,
                    leave_type_code="annual",
                    period_year=2026,
                    entry_type="earned",
                    amount_days="99.00",
                ),
                LeaveRequest(
                    id=UUID("12121212-1212-4121-8121-121212121212"),
                    tenant_id=TENANT_ID,
                    employee_id=EMPTY_EMPLOYEE_ID,
                    leave_type="annual",
                    leave_type_id=_leave_type_id(TENANT_ID, "annual"),
                    policy_id=_leave_policy_id(TENANT_ID, "annual"),
                    start_date=date(2026, 7, 20),
                    end_date=date(2026, 7, 22),
                    status=LeaveRequestStatus.APPROVED.value,
                    requested_by_user_id=REQUESTING_USER_ID,
                    decided_by_user_id=REQUESTING_USER_ID,
                    decided_at=datetime(2026, 7, 19, 12, 0, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_authenticated_tenant_request_context] = (
        _authenticated_tenant_context
    )
    app.dependency_overrides[require_authenticated_session] = lambda: SimpleNamespace(
        user=SimpleNamespace(permissions=LEAVE_READ_PERMISSIONS)
    )

    return (
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ),
        engine,
    )


def _tenant_headers() -> dict[str, str]:
    return {}


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


async def test_list_employee_leave_balances_returns_derived_ledger_balances() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/leave-balances",
            headers=_tenant_headers(),
        )

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body] == [
            str(_leave_balance_id(TENANT_ID, EMPLOYEE_ID, "annual", 2026)),
            str(_leave_balance_id(TENANT_ID, EMPLOYEE_ID, "sick", 2026)),
        ]
        annual = body[0]
        assert annual["employee_id"] == str(EMPLOYEE_ID)
        assert annual["leave_type_id"] == str(_leave_type_id(TENANT_ID, "annual"))
        assert annual["leave_type_code"] == "annual"
        assert annual["leave_type_name"] == "Annual"
        assert annual["leave_type"] == "annual"
        assert annual["period_year"] == 2026
        assert Decimal(str(annual["earned_days"])) == Decimal("20.00")
        assert Decimal(str(annual["adjusted_days"])) == Decimal("0.00")
        assert Decimal(str(annual["used_days"])) == Decimal("5.00")
        assert Decimal(str(annual["planned_days"])) == Decimal("2.00")
        assert Decimal(str(annual["available_days"])) == Decimal("13.00")
        assert Decimal(str(annual["opening_balance_days"])) == Decimal("20.00")
        assert Decimal(str(annual["remaining_days"])) == Decimal("13.00")
        assert annual["negative_balance_allowed"] is False
        assert annual["calculation_mode"] == "ledger"
        assert annual["external_integration_enabled"] is False
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
        assert [item["leave_type_code"] for item in body] == ["annual", "sick"]
        assert Decimal(str(body[0]["earned_days"])) == Decimal("10.00")
        assert Decimal(str(body[0]["used_days"])) == Decimal("4.00")
        assert Decimal(str(body[0]["available_days"])) == Decimal("6.00")
        assert Decimal(str(body[1]["available_days"])) == Decimal("0.00")
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employee_leave_balances_does_not_derive_usage_from_request_rows() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            f"/api/v1/employees/{EMPTY_EMPLOYEE_ID}/leave-balances",
            headers=_tenant_headers(),
        )

        assert response.status_code == 200
        body = response.json()
        assert [item["leave_type_code"] for item in body] == ["annual", "sick"]
        assert all(
            Decimal(str(item["earned_days"])) == Decimal("0.00")
            and Decimal(str(item["used_days"])) == Decimal("0.00")
            and Decimal(str(item["planned_days"])) == Decimal("0.00")
            and Decimal(str(item["available_days"])) == Decimal("0.00")
            for item in body
        )
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
            code="leave_not_found",
            message="The leave resource was not found",
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


async def test_leave_balance_routes_use_authenticated_tenant_without_header() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/leave-balances",
            headers={"X-Correlation-Id": "w4a6-leave-balance-tenant"},
            params={"period_year": 2026},
        )

        assert response.status_code == 200
        assert [item["leave_type_code"] for item in response.json()] == [
            "annual",
            "sick",
        ]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_leave_balance_routes_ignore_spoofed_tenant_header() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/leave-balances",
            headers={
                "X-Tenant-Id": str(OTHER_TENANT_ID),
                "X-Correlation-Id": "w4b4-leave-balance-tenant-invalid",
            },
            params={"period_year": 2026},
        )

        assert response.status_code == 200
        assert all(item["employee_id"] == str(EMPLOYEE_ID) for item in response.json())
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


async def test_employee_archive_preserves_leave_balance_and_ledger_history() -> None:
    client, engine = await _client_with_database()
    try:
        archive_response = await client.delete(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
        )
        balance_response = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/leave-balances",
            headers=_tenant_headers(),
        )

        assert archive_response.status_code == 204
        assert balance_response.status_code == 200
        assert [item["leave_type_code"] for item in balance_response.json()] == [
            "annual",
            "sick",
        ]

        async with AsyncSession(engine, expire_on_commit=False) as session:
            employee = await session.get(Employee, EMPLOYEE_ID)
            balance_count = await session.scalar(
                select(func.count())
                .select_from(LeaveBalanceLedger)
                .where(LeaveBalanceLedger.tenant_id == TENANT_ID)
                .where(LeaveBalanceLedger.employee_id == EMPLOYEE_ID)
            )
        assert employee is not None
        assert employee.archived_at is not None
        assert balance_count == 8
    finally:
        await client.aclose()
        await engine.dispose()
