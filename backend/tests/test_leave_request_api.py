from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID, uuid4, uuid5

import pytest
from app.api.auth_dependencies import require_authenticated_session
from app.api.dependencies import get_authenticated_tenant_request_context
from app.api.leave import get_leave_command_handler, get_leave_service
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.command_idempotency import CommandIdempotency
from app.models.department import Department, DepartmentStatus
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_account_link import EmployeeAccountLink
from app.models.employee_assignment import EmployeeAssignment
from app.models.identity import (
    Identity,
    IdentityStatus,
    MembershipStatus,
    TenantMembership,
)
from app.models.leave import LeavePolicy, LeaveType
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.organization import Branch, BranchStatus, LegalEntity, LegalEntityStatus
from app.models.position import Position, PositionStatus
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.db import PersistenceConcurrencyError, PersistenceIntegrityError
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.tenancy import TenantContext
from app.schemas.leave import LEAVE_LIST_DEFAULT_LIMIT
from app.services.leave_service import LeaveNotFoundError, LeaveService
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select
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
LEAVE_FIXTURE_NAMESPACE = UUID("a1000000-0000-4000-8000-000000000004")
ACCOUNT_LINK_ID = UUID("a7000000-0000-4000-8000-000000000001")
BRANCH_ID = UUID("a7000000-0000-4000-8000-000000000002")
DEPARTMENT_ID = UUID("a7000000-0000-4000-8000-000000000003")
POSITION_ID = UUID("a7000000-0000-4000-8000-000000000004")
ASSIGNMENT_ID = UUID("a7000000-0000-4000-8000-000000000005")
LEAVE_PERMISSIONS = (
    "leave:read:tenant",
    "leave:manage:tenant",
    "leave:create:own",
    "leave:cancel:own",
)


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
                    created_at=NOW,
                ),
            )
        )
    return rows


def _leave_type_id(tenant_id: UUID, code: str) -> UUID:
    return uuid5(LEAVE_FIXTURE_NAMESPACE, f"leave-type:{tenant_id}:{code}")


def _leave_policy_id(tenant_id: UUID, code: str) -> UUID:
    return uuid5(LEAVE_FIXTURE_NAMESPACE, f"leave-policy:{tenant_id}:{code}:1")


async def _client_with_database(
    extra_current_leave_request_count: int = 0,
    dependency_overrides: dict[
        Callable[..., object],
        Callable[..., object],
    ]
    | None = None,
) -> tuple[AsyncClient, AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        use_insertmanyvalues=False,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def register_sqlite_now(dbapi_connection, _connection_record) -> None:
        dbapi_connection.create_function(
            "now",
            0,
            lambda: NOW.isoformat(),
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
            Identity(
                id=REQUESTING_USER_ID,
                email="requester@wealthyfalcon.test",
                status=IdentityStatus.ACTIVE.value,
                password_hash="test-password-hash",
                platform_permission_version=1,
            ),
            TenantMembership(
                id=REQUESTING_USER_ID,
                tenant_id=TENANT_ID,
                identity_id=REQUESTING_USER_ID,
                legacy_user_id=REQUESTING_USER_ID,
                full_name="Requesting User",
                status=MembershipStatus.ACTIVE.value,
                permission_version=1,
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
            EmployeeAccountLink(
                id=ACCOUNT_LINK_ID,
                tenant_id=TENANT_ID,
                employee_id=EMPLOYEE_ID,
                membership_id=REQUESTING_USER_ID,
                version=1,
            ),
            LegalEntity(
                id=TENANT_ID,
                tenant_id=TENANT_ID,
                code="DEFAULT",
                name="Wealthy Falcon HR",
                registered_name="Wealthy Falcon HR",
                country_code=None,
                tax_number=None,
                timezone="Europe/Istanbul",
                status=LegalEntityStatus.ACTIVE.value,
                is_default=True,
            ),
            Branch(
                id=BRANCH_ID,
                tenant_id=TENANT_ID,
                legal_entity_id=TENANT_ID,
                code="HQ",
                name="Headquarters",
                timezone="Europe/Istanbul",
                country_code=None,
                city=None,
                address=None,
                status=BranchStatus.ACTIVE.value,
                archived_at=None,
            ),
            Department(
                id=DEPARTMENT_ID,
                tenant_id=TENANT_ID,
                parent_id=None,
                code="PEOPLE",
                name="People",
                status=DepartmentStatus.ACTIVE.value,
                archived_at=None,
            ),
            Position(
                id=POSITION_ID,
                tenant_id=TENANT_ID,
                code="HR",
                title="HR Specialist",
                status=PositionStatus.ACTIVE.value,
                archived_at=None,
            ),
            EmployeeAssignment(
                id=ASSIGNMENT_ID,
                tenant_id=TENANT_ID,
                employee_id=EMPLOYEE_ID,
                legal_entity_id=TENANT_ID,
                branch_id=BRANCH_ID,
                department_id=DEPARTMENT_ID,
                position_id=POSITION_ID,
                manager_user_id=APPROVER_USER_ID,
                supersedes_assignment_id=None,
                effective_from=date(2026, 7, 1),
                effective_to=None,
                change_reason="Leave API fixture assignment",
                created_by_user_id=None,
            ),
            *_leave_configuration(TENANT_ID, "annual", "sick"),
            *_leave_configuration(OTHER_TENANT_ID, "annual"),
            LeaveRequest(
                id=PENDING_REQUEST_ID,
                tenant_id=TENANT_ID,
                employee_id=EMPLOYEE_ID,
                leave_type="annual",
                leave_type_id=_leave_type_id(TENANT_ID, "annual"),
                policy_id=_leave_policy_id(TENANT_ID, "annual"),
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
                leave_type_id=_leave_type_id(TENANT_ID, "sick"),
                policy_id=_leave_policy_id(TENANT_ID, "sick"),
                start_date=date(2026, 7, 10),
                end_date=date(2026, 7, 10),
                status=LeaveRequestStatus.APPROVED.value,
                requested_by_user_id=REQUESTING_USER_ID,
                decided_by_user_id=APPROVER_USER_ID,
                decided_at=NOW - timedelta(hours=1, minutes=30),
                created_at=NOW - timedelta(hours=2),
            ),
            LeaveRequest(
                id=REJECTED_REQUEST_ID,
                tenant_id=TENANT_ID,
                employee_id=SECOND_EMPLOYEE_ID,
                leave_type="annual",
                leave_type_id=_leave_type_id(TENANT_ID, "annual"),
                policy_id=_leave_policy_id(TENANT_ID, "annual"),
                start_date=date(2026, 7, 25),
                end_date=date(2026, 7, 26),
                status=LeaveRequestStatus.REJECTED.value,
                requested_by_user_id=REQUESTING_USER_ID,
                decided_by_user_id=APPROVER_USER_ID,
                decision_note="Coverage conflict",
                decided_at=NOW - timedelta(minutes=15),
                created_at=NOW - timedelta(minutes=30),
            ),
            LeaveRequest(
                id=OTHER_REQUEST_ID,
                tenant_id=OTHER_TENANT_ID,
                employee_id=OTHER_EMPLOYEE_ID,
                leave_type="annual",
                leave_type_id=_leave_type_id(OTHER_TENANT_ID, "annual"),
                policy_id=_leave_policy_id(OTHER_TENANT_ID, "annual"),
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
                leave_type_id=_leave_type_id(TENANT_ID, "annual"),
                policy_id=_leave_policy_id(TENANT_ID, "annual"),
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
    app.dependency_overrides[get_authenticated_tenant_request_context] = (
        _authenticated_tenant_context
    )
    app.dependency_overrides[require_authenticated_session] = lambda: SimpleNamespace(
        user=SimpleNamespace(permissions=LEAVE_PERMISSIONS)
    )
    app.dependency_overrides.update(dependency_overrides or {})

    return (
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ),
        engine,
    )


def _authenticated_tenant_context() -> RequestContext:
    return RequestContext(
        request_id="leave-request-api-test",
        trace_id="c4000000000040008000000000000001",
        tenant=TenantContext(
            tenant_id=TENANT_ID,
            slug="wealthy-falcon",
        ),
        actor_id=REQUESTING_USER_ID,
        membership_id=REQUESTING_USER_ID,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
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


def _create_payload() -> dict[str, str]:
    return {
        "leave_type_id": str(_leave_type_id(TENANT_ID, "annual")),
        "start_date": "2026-08-03",
        "end_date": "2026-08-07",
        "employee_note": "Family trip",
    }


def _decision_payload() -> dict[str, object]:
    return {
        "expected_version": 1,
        "decision_note": "Coverage is planned",
    }


class _FailAfterFlushedApprovalService(LeaveService):
    async def decide_request(self, *args, **kwargs):
        await super().decide_request(*args, **kwargs)
        raise LeaveNotFoundError


class _LeaveRequestNotFoundCommandHandler:
    async def create_request(self, *args, **kwargs):
        raise LeaveNotFoundError


class _FailingPersistenceCommandHandler:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def create_request(self, *args, **kwargs):
        raise self.error


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


async def test_leave_routes_validate_payload_with_authenticated_tenant_context() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/leave-requests",
            headers={"X-Correlation-Id": "w4a6-leave-tenant-first"},
            json={},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_request_validation_error",
            message="Leave request validation failed",
            correlation_id="w4a6-leave-tenant-first",
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


async def test_create_leave_request_rejects_numeric_leave_date() -> None:
    client, engine = await _client_with_database()
    try:
        payload = _create_payload()
        payload["start_date"] = 0

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


async def test_create_leave_request_rejects_client_controlled_employee() -> None:
    client, engine = await _client_with_database()
    try:
        payload = _create_payload()
        payload["employee_id"] = str(OTHER_EMPLOYEE_ID)
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


async def test_create_leave_request_rejects_client_controlled_requesting_user() -> None:
    client, engine = await _client_with_database()
    try:
        payload = _create_payload()
        payload["requested_by_user_id"] = str(OTHER_USER_ID)
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


async def test_list_leave_requests_exposes_deterministic_cursor_with_array_body() -> None:
    client, engine = await _client_with_database()
    try:
        seen_ids: list[str] = []
        cursor: str | None = None

        while True:
            params = {"limit": 1}
            if cursor is not None:
                params["cursor"] = cursor
            response = await client.get(
                "/api/v1/leave-requests",
                headers=_tenant_headers(),
                params=params,
            )

            assert response.status_code == 200
            assert len(response.json()) == 1
            seen_ids.append(response.json()[0]["id"])
            cursor = response.headers.get("X-Next-Cursor")
            if cursor is None:
                break

        assert seen_ids == [
            str(REJECTED_REQUEST_ID),
            str(PENDING_REQUEST_ID),
            str(APPROVED_REQUEST_ID),
        ]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_leave_requests_rejects_invalid_cursor_and_cursor_offset_mix() -> None:
    client, engine = await _client_with_database()
    try:
        invalid_response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={"cursor": "not-a-cursor"},
        )
        first_response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={"limit": 1},
        )
        mixed_response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={
                "cursor": first_response.headers["X-Next-Cursor"],
                "offset": 1,
            },
        )

        _assert_error_response(
            invalid_response,
            status_code=422,
            code="leave_validation_error",
            message="The leave request cursor is invalid",
        )
        _assert_error_response(
            mixed_response,
            status_code=422,
            code="leave_validation_error",
            message="Cursor pagination requires offset=0",
        )
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
        assert len(response.json()) == LEAVE_LIST_DEFAULT_LIMIT
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


async def test_list_leave_requests_rejects_invalid_employee_id_filter_envelope() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/leave-requests",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": "w4a6-leave-filter-validation",
            },
            params={"employee_id": "not-a-uuid"},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_request_validation_error",
            message="Leave request validation failed",
            correlation_id="w4a6-leave-filter-validation",
        )
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


async def test_list_leave_requests_supports_single_sided_date_filters_within_tenant() -> None:
    client, engine = await _client_with_database()
    try:
        open_start_response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={"start_date": "2026-07-22"},
        )
        open_end_response = await client.get(
            "/api/v1/leave-requests",
            headers=_tenant_headers(),
            params={"end_date": "2026-07-20"},
        )

        assert open_start_response.status_code == 200
        assert [item["id"] for item in open_start_response.json()] == [
            str(REJECTED_REQUEST_ID),
            str(PENDING_REQUEST_ID),
        ]
        assert str(OTHER_REQUEST_ID) not in {item["id"] for item in open_start_response.json()}
        assert open_end_response.status_code == 200
        assert [item["id"] for item in open_end_response.json()] == [
            str(PENDING_REQUEST_ID),
            str(APPROVED_REQUEST_ID),
        ]
        assert str(OTHER_REQUEST_ID) not in {item["id"] for item in open_end_response.json()}
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
            code="leave_validation_error",
            message="The leave request filters are invalid",
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
        assert body["decided_by_user_id"] == str(REQUESTING_USER_ID)
        assert body["decision_note"] == "Coverage is planned"

        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            persisted = await session.get(LeaveRequest, PENDING_REQUEST_ID)
        assert persisted is not None
        assert persisted.status == LeaveRequestStatus.APPROVED.value
        assert persisted.decided_by_user_id == REQUESTING_USER_ID
        assert persisted.decision_note == "Coverage is planned"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_decision_idempotency_replays_and_rejects_action_reuse() -> None:
    client, engine = await _client_with_database()
    headers = {
        **_tenant_headers(),
        "X-Idempotency-Key": "leave-decision-retry-001",
        "X-Correlation-Id": "p0e-leave-decision-idempotency",
    }
    payload = {"expected_version": 1, "decision_note": "Stable decision"}
    try:
        first_response = await client.post(
            f"/api/v1/leave-requests/{PENDING_REQUEST_ID}/approve",
            headers=headers,
            json=payload,
        )
        replay_response = await client.post(
            f"/api/v1/leave-requests/{PENDING_REQUEST_ID}/approve",
            headers=headers,
            json=payload,
        )
        mismatch_response = await client.post(
            f"/api/v1/leave-requests/{PENDING_REQUEST_ID}/reject",
            headers=headers,
            json=payload,
        )

        assert first_response.status_code == 200
        assert replay_response.status_code == 200
        assert replay_response.json() == first_response.json()
        _assert_error_response(
            mismatch_response,
            status_code=409,
            code="idempotency_key_mismatch",
            message=("X-Idempotency-Key was already used for a different request in this tenant"),
            correlation_id="p0e-leave-decision-idempotency",
        )

        async with AsyncSession(engine, expire_on_commit=False) as session:
            persisted = await session.get(LeaveRequest, PENDING_REQUEST_ID)
            receipt_count = await session.scalar(
                select(func.count())
                .select_from(CommandIdempotency)
                .where(CommandIdempotency.tenant_id == TENANT_ID)
                .where(CommandIdempotency.idempotency_key == "leave-decision-retry-001")
            )
        assert persisted is not None
        assert persisted.status == LeaveRequestStatus.APPROVED.value
        assert persisted.decision_note == "Stable decision"
        assert receipt_count == 1
    finally:
        await client.aclose()
        await engine.dispose()


async def test_decision_command_rolls_back_flushed_mutation_after_typed_error() -> None:
    def override_service(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> LeaveService:
        return _FailAfterFlushedApprovalService(session)

    client, engine = await _client_with_database(
        dependency_overrides={get_leave_service: override_service}
    )
    try:
        response = await client.post(
            f"/api/v1/leave-requests/{PENDING_REQUEST_ID}/approve",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": "p0c-leave-rollback",
            },
            json=_decision_payload(),
        )

        _assert_error_response(
            response,
            status_code=404,
            code="leave_not_found",
            message="The leave resource was not found",
            correlation_id="p0c-leave-rollback",
        )
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            persisted = await session.get(LeaveRequest, PENDING_REQUEST_ID)
        assert persisted is not None
        assert persisted.status == LeaveRequestStatus.PENDING.value
        assert persisted.decided_by_user_id is None
        assert persisted.decision_note is None
    finally:
        await client.aclose()
        await engine.dispose()


async def test_central_error_mapper_handles_typed_command_error_for_any_write_route() -> None:
    handler = _LeaveRequestNotFoundCommandHandler()
    client, engine = await _client_with_database(
        dependency_overrides={get_leave_command_handler: lambda: handler}
    )
    try:
        response = await client.post(
            "/api/v1/leave-requests",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": "p0c-leave-central-mapper",
            },
            json=_create_payload(),
        )

        _assert_error_response(
            response,
            status_code=404,
            code="leave_not_found",
            message="The leave resource was not found",
            correlation_id="p0c-leave-central-mapper",
        )
    finally:
        await client.aclose()
        await engine.dispose()


@pytest.mark.parametrize(
    ("error", "code", "message"),
    [
        (
            PersistenceIntegrityError(constraint_name="safe_test_constraint"),
            "data_integrity_conflict",
            "The request conflicts with persisted data",
        ),
        (
            PersistenceConcurrencyError(sqlstate="40001"),
            "concurrent_write_conflict",
            "The request conflicted with another write; retry the request",
        ),
    ],
)
async def test_central_error_mapper_safely_maps_persistence_command_errors(
    error: Exception,
    code: str,
    message: str,
) -> None:
    handler = _FailingPersistenceCommandHandler(error)
    client, engine = await _client_with_database(
        dependency_overrides={get_leave_command_handler: lambda: handler}
    )
    try:
        response = await client.post(
            "/api/v1/leave-requests",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": "p0c-persistence-conflict",
            },
            json=_create_payload(),
        )

        _assert_error_response(
            response,
            status_code=409,
            code=code,
            message=message,
            correlation_id="p0c-persistence-conflict",
        )
        assert "safe_test_constraint" not in response.text
        assert "40001" not in response.text
    finally:
        await client.aclose()
        await engine.dispose()


async def test_leave_request_path_validation_uses_standard_error_envelope() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/leave-requests/not-a-uuid/approve",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": "w3a6-leave-path-validation",
            },
            json=_decision_payload(),
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_request_validation_error",
            message="Leave request validation failed",
            correlation_id="w3a6-leave-path-validation",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_leave_request_decision_validation_uses_standard_error_envelope() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            f"/api/v1/leave-requests/{PENDING_REQUEST_ID}/approve",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": "w3a6-leave-decision-validation",
            },
            json={"expected_version": 1, "decision_note": "   "},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_request_validation_error",
            message="Leave request validation failed",
            correlation_id="w3a6-leave-decision-validation",
        )
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
            code="leave_conflict",
            message="Only pending leave requests can be approved or rejected",
        )
    finally:
        await client.aclose()
        await engine.dispose()


@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_approval_routes_return_consistent_transition_conflict(action: str) -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            f"/api/v1/leave-requests/{APPROVED_REQUEST_ID}/{action}",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": f"w4a6-leave-{action}-conflict",
            },
            json=_decision_payload(),
        )

        _assert_error_response(
            response,
            status_code=409,
            code="leave_conflict",
            message="Only pending leave requests can be approved or rejected",
            correlation_id=f"w4a6-leave-{action}-conflict",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_cancel_route_rejects_terminal_rejected_request() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            f"/api/v1/leave-requests/{REJECTED_REQUEST_ID}/cancel",
            headers={
                **_tenant_headers(),
                "X-Correlation-Id": "w4a6-leave-cancel-conflict",
            },
            json=_decision_payload(),
        )

        _assert_error_response(
            response,
            status_code=409,
            code="leave_conflict",
            message="Only pending or approved leave requests can be cancelled",
            correlation_id="w4a6-leave-cancel-conflict",
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
            code="leave_not_found",
            message="The leave resource was not found",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_decision_routes_reject_client_controlled_decider() -> None:
    client, engine = await _client_with_database()
    try:
        payload = _decision_payload()
        payload["decided_by_user_id"] = str(OTHER_USER_ID)
        response = await client.post(
            f"/api/v1/leave-requests/{PENDING_REQUEST_ID}/approve",
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


async def test_leave_request_routes_use_authenticated_tenant_without_header() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get("/api/v1/leave-requests")

        assert response.status_code == 200
        assert {item["id"] for item in response.json()} == {
            str(PENDING_REQUEST_ID),
            str(APPROVED_REQUEST_ID),
            str(REJECTED_REQUEST_ID),
        }
    finally:
        await client.aclose()
        await engine.dispose()


async def test_leave_request_routes_ignore_spoofed_tenant_header_on_validation() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/leave-requests",
            headers={
                "X-Tenant-Id": str(TENANT_ID).upper(),
                "X-Correlation-Id": "w4b4-leave-tenant-invalid",
            },
            json={},
        )

        _assert_error_response(
            response,
            status_code=422,
            code="leave_request_validation_error",
            message="Leave request validation failed",
            correlation_id="w4b4-leave-tenant-invalid",
        )
    finally:
        await client.aclose()
        await engine.dispose()


async def test_leave_request_routes_ignore_repeated_spoofed_tenant_headers() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            "/api/v1/leave-requests",
            headers=[
                ("X-Tenant-Id", str(TENANT_ID)),
                ("X-Tenant-Id", str(OTHER_TENANT_ID)),
                ("X-Correlation-Id", "w4b4-leave-tenant-repeated"),
            ],
        )

        assert response.status_code == 200
        assert {item["id"] for item in response.json()} == {
            str(PENDING_REQUEST_ID),
            str(APPROVED_REQUEST_ID),
            str(REJECTED_REQUEST_ID),
        }
        assert response.headers["X-Correlation-Id"] == "w4b4-leave-tenant-repeated"
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
            parameter["name"] for parameter in paths["/api/v1/leave-requests"]["get"]["parameters"]
        }
        assert {"status", "employee_id", "start_date", "end_date", "limit", "offset"}.issubset(
            query_params
        )
        assert "/api/v1/leave-requests/{request_id}/approve" in paths
        assert "/api/v1/leave-requests/{request_id}/reject" in paths
        assert "/api/v1/leave-requests/{request_id}/cancel" in paths
    finally:
        await client.aclose()
        await engine.dispose()
