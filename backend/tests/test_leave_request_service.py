from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from app.db.base import Base
from app.models.employee import Employee, EmployeeStatus
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.db import SqlAlchemyUnitOfWork
from app.schemas.leave_request import (
    LeaveRequestCreate,
    LeaveRequestDecision,
    LeaveRequestListFilters,
    LeaveRequestListPagination,
)
from app.services.leave_request_commands import LeaveRequestCommandHandler
from app.services.leave_request_service import (
    LeaveRequestEmployeeNotFoundError,
    LeaveRequestNotFoundError,
    LeaveRequestService,
    LeaveRequestTransitionError,
    LeaveRequestUserNotFoundError,
)
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

TENANT_ID = UUID("11111111-aaaa-4111-8111-111111111111")
OTHER_TENANT_ID = UUID("22222222-bbbb-4222-8222-222222222222")
EMPLOYEE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SECOND_EMPLOYEE_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
OTHER_EMPLOYEE_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
REQUESTING_USER_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
APPROVER_USER_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
OTHER_USER_ID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
MISSING_EMPLOYEE_ID = UUID("99999999-9999-4999-8999-999999999999")
MISSING_USER_ID = UUID("88888888-8888-4888-8888-888888888888")
PENDING_REQUEST_ID = UUID("aaaaaaaa-1111-4aaa-8aaa-aaaaaaaa1111")
APPROVED_REQUEST_ID = UUID("bbbbbbbb-2222-4bbb-8bbb-bbbbbbbb2222")
BOUNDARY_REQUEST_ID = UUID("cccccccc-3333-4ccc-8ccc-cccccccc3333")
OTHER_REQUEST_ID = UUID("dddddddd-4444-4ddd-8ddd-dddddddd4444")
REJECTED_REQUEST_ID = UUID("eeeeeeee-5555-4eee-8eee-eeeeeeee5555")
CANCELLED_REQUEST_ID = UUID("ffffffff-6666-4fff-8fff-ffffffff6666")
ORDERED_FIRST_REQUEST_ID = UUID("abababab-7777-4aba-8aba-abababab7777")
ORDERED_SECOND_REQUEST_ID = UUID("bcbcbcbc-8888-4bcb-8bcb-bcbcbcbc8888")
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

    session = AsyncSession(engine, expire_on_commit=False)
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
                id=SECOND_EMPLOYEE_ID,
                tenant_id=TENANT_ID,
                employee_number="WF-002",
                first_name="Bora",
                last_name="Demir",
                email="bora@wealthyfalcon.test",
                department="Engineering",
                position="Backend Engineer",
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
            LeaveRequest(
                id=PENDING_REQUEST_ID,
                tenant_id=TENANT_ID,
                employee_id=EMPLOYEE_ID,
                leave_type="annual",
                start_date=date(2026, 7, 20),
                end_date=date(2026, 7, 22),
                status=LeaveRequestStatus.PENDING.value,
                requested_by_user_id=REQUESTING_USER_ID,
                created_at=NOW - timedelta(hours=2),
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
                created_at=NOW - timedelta(hours=3),
            ),
            LeaveRequest(
                id=BOUNDARY_REQUEST_ID,
                tenant_id=TENANT_ID,
                employee_id=SECOND_EMPLOYEE_ID,
                leave_type="annual",
                start_date=date(2026, 7, 22),
                end_date=date(2026, 7, 24),
                status=LeaveRequestStatus.PENDING.value,
                requested_by_user_id=REQUESTING_USER_ID,
                created_at=NOW - timedelta(hours=1),
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
    )
    await session.commit()
    return session, engine


async def test_create_leave_request_allows_single_day_request() -> None:
    session, engine = await _session_with_seed_data()
    try:
        leave_request = await LeaveRequestService(session).create_leave_request(
            TENANT_ID,
            LeaveRequestCreate(
                employee_id=EMPLOYEE_ID,
                leave_type="wellbeing",
                start_date=date(2026, 8, 3),
                end_date=date(2026, 8, 3),
                requested_by_user_id=REQUESTING_USER_ID,
            ),
        )

        persisted = await session.scalar(
            select(LeaveRequest).where(LeaveRequest.id == leave_request.id)
        )
        assert leave_request.status == LeaveRequestStatus.PENDING.value
        assert persisted is not None
        assert persisted.start_date == persisted.end_date == date(2026, 8, 3)
    finally:
        await session.close()
        await engine.dispose()


async def test_create_leave_request_flushes_without_commit_and_can_be_rolled_back() -> None:
    session, engine = await _session_with_seed_data()
    try:
        leave_request = await LeaveRequestService(session).create_leave_request(
            TENANT_ID,
            LeaveRequestCreate(
                employee_id=EMPLOYEE_ID,
                leave_type="annual",
                start_date=date(2026, 8, 10),
                end_date=date(2026, 8, 12),
                requested_by_user_id=REQUESTING_USER_ID,
            ),
        )
        leave_request_id = leave_request.id

        assert inspect(leave_request).persistent

        await session.rollback()

        async with AsyncSession(engine, expire_on_commit=False) as verification_session:
            persisted = await verification_session.get(LeaveRequest, leave_request_id)
        assert persisted is None
    finally:
        await session.close()
        await engine.dispose()


async def test_create_leave_request_command_commits_the_service_flush() -> None:
    session, engine = await _session_with_seed_data()
    try:
        handler = LeaveRequestCommandHandler(
            service=LeaveRequestService(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
        )

        leave_request = await handler.create_leave_request(
            TENANT_ID,
            LeaveRequestCreate(
                employee_id=EMPLOYEE_ID,
                leave_type="wellbeing",
                start_date=date(2026, 8, 17),
                end_date=date(2026, 8, 17),
                requested_by_user_id=REQUESTING_USER_ID,
            ),
        )
        leave_request_id = leave_request.id

        assert not session.in_transaction()
        async with AsyncSession(engine, expire_on_commit=False) as verification_session:
            persisted = await verification_session.get(LeaveRequest, leave_request_id)
        assert persisted is not None
        assert persisted.status == LeaveRequestStatus.PENDING.value
    finally:
        await session.close()
        await engine.dispose()


async def test_create_leave_request_checks_employee_before_requesting_user() -> None:
    session, engine = await _session_with_seed_data()
    try:
        with pytest.raises(LeaveRequestEmployeeNotFoundError):
            await LeaveRequestService(session).create_leave_request(
                TENANT_ID,
                LeaveRequestCreate(
                    employee_id=MISSING_EMPLOYEE_ID,
                    leave_type="annual",
                    start_date=date(2026, 8, 3),
                    end_date=date(2026, 8, 7),
                    requested_by_user_id=MISSING_USER_ID,
                ),
            )
    finally:
        await session.close()
        await engine.dispose()


async def test_create_leave_request_rejects_missing_requesting_user() -> None:
    session, engine = await _session_with_seed_data()
    try:
        with pytest.raises(LeaveRequestUserNotFoundError):
            await LeaveRequestService(session).create_leave_request(
                TENANT_ID,
                LeaveRequestCreate(
                    employee_id=EMPLOYEE_ID,
                    leave_type="annual",
                    start_date=date(2026, 8, 3),
                    end_date=date(2026, 8, 7),
                    requested_by_user_id=MISSING_USER_ID,
                ),
            )
    finally:
        await session.close()
        await engine.dispose()


async def test_create_leave_request_rejects_cross_tenant_requesting_user_without_insert() -> None:
    session, engine = await _session_with_seed_data()
    try:
        existing_ids = set(await session.scalars(select(LeaveRequest.id)))

        with pytest.raises(LeaveRequestUserNotFoundError):
            await LeaveRequestService(session).create_leave_request(
                TENANT_ID,
                LeaveRequestCreate(
                    employee_id=EMPLOYEE_ID,
                    leave_type="annual",
                    start_date=date(2026, 8, 3),
                    end_date=date(2026, 8, 7),
                    requested_by_user_id=OTHER_USER_ID,
                ),
            )

        current_ids = set(await session.scalars(select(LeaveRequest.id)))
        assert current_ids == existing_ids
    finally:
        await session.close()
        await engine.dispose()


async def test_create_leave_request_rejects_cross_tenant_employee_without_insert() -> None:
    session, engine = await _session_with_seed_data()
    try:
        existing_ids = set(await session.scalars(select(LeaveRequest.id)))

        with pytest.raises(LeaveRequestEmployeeNotFoundError):
            await LeaveRequestService(session).create_leave_request(
                TENANT_ID,
                LeaveRequestCreate(
                    employee_id=OTHER_EMPLOYEE_ID,
                    leave_type="annual",
                    start_date=date(2026, 8, 3),
                    end_date=date(2026, 8, 7),
                    requested_by_user_id=REQUESTING_USER_ID,
                ),
            )

        current_ids = set(await session.scalars(select(LeaveRequest.id)))
        assert current_ids == existing_ids
    finally:
        await session.close()
        await engine.dispose()


async def test_list_leave_requests_uses_inclusive_overlap_boundaries() -> None:
    session, engine = await _session_with_seed_data()
    try:
        leave_requests = await LeaveRequestService(session).list_leave_requests(
            TENANT_ID,
            filters=LeaveRequestListFilters(
                start_date=date(2026, 7, 22),
                end_date=date(2026, 7, 22),
            ),
        )

        assert {leave_request.id for leave_request in leave_requests} == {
            PENDING_REQUEST_ID,
            BOUNDARY_REQUEST_ID,
        }
    finally:
        await session.close()
        await engine.dispose()


async def test_list_leave_requests_combines_status_employee_and_date_filters() -> None:
    session, engine = await _session_with_seed_data()
    try:
        leave_requests = await LeaveRequestService(session).list_leave_requests(
            TENANT_ID,
            filters=LeaveRequestListFilters(
                status=LeaveRequestStatus.PENDING,
                employee_id=EMPLOYEE_ID,
                start_date=date(2026, 7, 21),
                end_date=date(2026, 7, 21),
            ),
        )
        cross_tenant_employee_requests = await LeaveRequestService(session).list_leave_requests(
            TENANT_ID,
            filters=LeaveRequestListFilters(
                status=LeaveRequestStatus.PENDING,
                employee_id=OTHER_EMPLOYEE_ID,
                start_date=date(2026, 7, 21),
                end_date=date(2026, 7, 21),
            ),
        )

        assert [leave_request.id for leave_request in leave_requests] == [PENDING_REQUEST_ID]
        assert cross_tenant_employee_requests == []
    finally:
        await session.close()
        await engine.dispose()


async def test_list_leave_requests_accepts_constructed_raw_status_filter() -> None:
    session, engine = await _session_with_seed_data()
    try:
        filters = LeaveRequestListFilters.model_construct(
            status=LeaveRequestStatus.APPROVED.value
        )

        leave_requests = await LeaveRequestService(session).list_leave_requests(
            TENANT_ID,
            filters=filters,
        )

        assert [leave_request.id for leave_request in leave_requests] == [APPROVED_REQUEST_ID]
        assert {leave_request.tenant_id for leave_request in leave_requests} == {TENANT_ID}
    finally:
        await session.close()
        await engine.dispose()


async def test_list_leave_requests_paginates_after_tenant_scope() -> None:
    session, engine = await _session_with_seed_data()
    try:
        leave_requests = await LeaveRequestService(session).list_leave_requests(
            TENANT_ID,
            pagination=LeaveRequestListPagination(limit=1, offset=1),
        )

        assert [leave_request.id for leave_request in leave_requests] == [PENDING_REQUEST_ID]
        assert {leave_request.tenant_id for leave_request in leave_requests} == {TENANT_ID}
    finally:
        await session.close()
        await engine.dispose()


async def test_list_leave_requests_supports_single_sided_date_filters() -> None:
    session, engine = await _session_with_seed_data()
    try:
        ending_on_or_after = await LeaveRequestService(session).list_leave_requests(
            TENANT_ID,
            filters=LeaveRequestListFilters(start_date=date(2026, 7, 22)),
        )
        starting_on_or_before = await LeaveRequestService(session).list_leave_requests(
            TENANT_ID,
            filters=LeaveRequestListFilters(end_date=date(2026, 7, 20)),
        )

        assert {leave_request.id for leave_request in ending_on_or_after} == {
            PENDING_REQUEST_ID,
            BOUNDARY_REQUEST_ID,
        }
        assert {leave_request.id for leave_request in starting_on_or_before} == {
            PENDING_REQUEST_ID,
            APPROVED_REQUEST_ID,
        }
    finally:
        await session.close()
        await engine.dispose()


async def test_list_leave_requests_orders_created_at_ties_by_start_date_then_id() -> None:
    session, engine = await _session_with_seed_data()
    try:
        session.add_all(
            [
                LeaveRequest(
                    id=ORDERED_SECOND_REQUEST_ID,
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type="annual",
                    start_date=date(2026, 9, 10),
                    end_date=date(2026, 9, 10),
                    status=LeaveRequestStatus.PENDING.value,
                    requested_by_user_id=REQUESTING_USER_ID,
                    created_at=NOW + timedelta(hours=1),
                ),
                LeaveRequest(
                    id=ORDERED_FIRST_REQUEST_ID,
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type="annual",
                    start_date=date(2026, 9, 1),
                    end_date=date(2026, 9, 1),
                    status=LeaveRequestStatus.PENDING.value,
                    requested_by_user_id=REQUESTING_USER_ID,
                    created_at=NOW + timedelta(hours=1),
                ),
            ]
        )
        await session.commit()

        leave_requests = await LeaveRequestService(session).list_leave_requests(
            TENANT_ID,
            filters=LeaveRequestListFilters(
                status=LeaveRequestStatus.PENDING,
                employee_id=EMPLOYEE_ID,
            ),
            pagination=LeaveRequestListPagination(limit=2),
        )

        assert [leave_request.id for leave_request in leave_requests] == [
            ORDERED_FIRST_REQUEST_ID,
            ORDERED_SECOND_REQUEST_ID,
        ]
    finally:
        await session.close()
        await engine.dispose()


async def test_create_leave_request_rejects_null_requesting_user_without_insert() -> None:
    session, engine = await _session_with_seed_data()
    try:
        existing_ids = set(await session.scalars(select(LeaveRequest.id)))
        payload = LeaveRequestCreate.model_construct(
            employee_id=EMPLOYEE_ID,
            leave_type="annual",
            start_date=date(2026, 8, 3),
            end_date=date(2026, 8, 7),
            requested_by_user_id=None,
        )

        with pytest.raises(LeaveRequestUserNotFoundError):
            await LeaveRequestService(session).create_leave_request(TENANT_ID, payload)

        current_ids = set(await session.scalars(select(LeaveRequest.id)))
        assert current_ids == existing_ids
    finally:
        await session.close()
        await engine.dispose()


async def test_decide_leave_request_checks_transition_before_decider_tenant() -> None:
    session, engine = await _session_with_seed_data()
    try:
        with pytest.raises(LeaveRequestTransitionError):
            await LeaveRequestService(session).approve_leave_request(
                TENANT_ID,
                APPROVED_REQUEST_ID,
                LeaveRequestDecision(decided_by_user_id=OTHER_USER_ID),
            )

        leave_request = await session.scalar(
            select(LeaveRequest).where(LeaveRequest.id == APPROVED_REQUEST_ID)
        )
        assert leave_request is not None
        assert leave_request.status == LeaveRequestStatus.APPROVED.value
        assert leave_request.decided_by_user_id == APPROVER_USER_ID
    finally:
        await session.close()
        await engine.dispose()


async def test_approve_leave_request_allows_empty_decision_note() -> None:
    session, engine = await _session_with_seed_data()
    try:
        leave_request = await LeaveRequestService(session).approve_leave_request(
            TENANT_ID,
            PENDING_REQUEST_ID,
            LeaveRequestDecision(decided_by_user_id=APPROVER_USER_ID),
        )

        assert leave_request.status == LeaveRequestStatus.APPROVED.value
        assert leave_request.decided_by_user_id == APPROVER_USER_ID
        assert leave_request.decision_note is None
    finally:
        await session.close()
        await engine.dispose()


async def test_decide_leave_request_flushes_without_commit_and_can_be_rolled_back() -> None:
    session, engine = await _session_with_seed_data()
    try:
        leave_request = await LeaveRequestService(session).approve_leave_request(
            TENANT_ID,
            PENDING_REQUEST_ID,
            LeaveRequestDecision(
                decided_by_user_id=APPROVER_USER_ID,
                decision_note="Approved before outer rollback",
            ),
        )

        assert leave_request.status == LeaveRequestStatus.APPROVED.value
        assert not session.is_modified(leave_request, include_collections=False)

        await session.rollback()

        async with AsyncSession(engine, expire_on_commit=False) as verification_session:
            persisted = await verification_session.get(LeaveRequest, PENDING_REQUEST_ID)
        assert persisted is not None
        assert persisted.status == LeaveRequestStatus.PENDING.value
        assert persisted.decided_by_user_id is None
        assert persisted.decision_note is None
    finally:
        await session.close()
        await engine.dispose()


async def test_decide_leave_request_rejects_cross_tenant_decider_without_mutation() -> None:
    session, engine = await _session_with_seed_data()
    try:
        with pytest.raises(LeaveRequestUserNotFoundError):
            await LeaveRequestService(session).approve_leave_request(
                TENANT_ID,
                PENDING_REQUEST_ID,
                LeaveRequestDecision(decided_by_user_id=OTHER_USER_ID),
            )

        leave_request = await session.scalar(
            select(LeaveRequest).where(LeaveRequest.id == PENDING_REQUEST_ID)
        )
        assert leave_request is not None
        assert leave_request.status == LeaveRequestStatus.PENDING.value
        assert leave_request.decided_by_user_id is None
        assert leave_request.decision_note is None
    finally:
        await session.close()
        await engine.dispose()


async def test_decide_leave_request_rejects_constructed_null_decider_without_mutation() -> None:
    session, engine = await _session_with_seed_data()
    try:
        payload = LeaveRequestDecision.model_construct(
            decided_by_user_id=None,
            decision_note="Approved outside schema validation",
        )

        with pytest.raises(LeaveRequestUserNotFoundError):
            await LeaveRequestService(session).approve_leave_request(
                TENANT_ID,
                PENDING_REQUEST_ID,
                payload,
            )

        leave_request = await session.scalar(
            select(LeaveRequest).where(LeaveRequest.id == PENDING_REQUEST_ID)
        )
        assert leave_request is not None
        assert leave_request.status == LeaveRequestStatus.PENDING.value
        assert leave_request.decided_by_user_id is None
        assert leave_request.decision_note is None
    finally:
        await session.close()
        await engine.dispose()


async def test_reject_leave_request_sets_decider_and_note() -> None:
    session, engine = await _session_with_seed_data()
    try:
        leave_request = await LeaveRequestService(session).reject_leave_request(
            TENANT_ID,
            PENDING_REQUEST_ID,
            LeaveRequestDecision(
                decided_by_user_id=APPROVER_USER_ID,
                decision_note="Coverage conflict",
            ),
        )

        assert leave_request.status == LeaveRequestStatus.REJECTED.value
        assert leave_request.decided_by_user_id == APPROVER_USER_ID
        assert leave_request.decision_note == "Coverage conflict"
    finally:
        await session.close()
        await engine.dispose()


async def test_cancel_leave_request_sets_decider_and_note() -> None:
    session, engine = await _session_with_seed_data()
    try:
        leave_request = await LeaveRequestService(session).cancel_leave_request(
            TENANT_ID,
            PENDING_REQUEST_ID,
            LeaveRequestDecision(
                decided_by_user_id=APPROVER_USER_ID,
                decision_note="Employee withdrew the request",
            ),
        )

        assert leave_request.status == LeaveRequestStatus.CANCELLED.value
        assert leave_request.decided_by_user_id == APPROVER_USER_ID
        assert leave_request.decision_note == "Employee withdrew the request"
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.parametrize(
    ("request_id", "status"),
    [
        (REJECTED_REQUEST_ID, LeaveRequestStatus.REJECTED),
        (CANCELLED_REQUEST_ID, LeaveRequestStatus.CANCELLED),
    ],
)
async def test_decide_leave_request_rejects_terminal_status_without_mutation(
    request_id: UUID,
    status: LeaveRequestStatus,
) -> None:
    session, engine = await _session_with_seed_data()
    try:
        session.add(
            LeaveRequest(
                id=request_id,
                tenant_id=TENANT_ID,
                employee_id=EMPLOYEE_ID,
                leave_type="annual",
                start_date=date(2026, 8, 10),
                end_date=date(2026, 8, 10),
                status=status.value,
                requested_by_user_id=REQUESTING_USER_ID,
                decided_by_user_id=APPROVER_USER_ID,
                decision_note="Already decided",
                created_at=NOW + timedelta(minutes=1),
            )
        )
        await session.commit()

        with pytest.raises(LeaveRequestTransitionError):
            await LeaveRequestService(session).approve_leave_request(
                TENANT_ID,
                request_id,
                LeaveRequestDecision(
                    decided_by_user_id=APPROVER_USER_ID,
                    decision_note="New decision",
                ),
            )

        leave_request = await session.scalar(
            select(LeaveRequest).where(LeaveRequest.id == request_id)
        )
        assert leave_request is not None
        assert leave_request.status == status.value
        assert leave_request.decided_by_user_id == APPROVER_USER_ID
        assert leave_request.decision_note == "Already decided"
    finally:
        await session.close()
        await engine.dispose()


async def test_decision_is_tenant_scoped_at_service_boundary() -> None:
    session, engine = await _session_with_seed_data()
    try:
        with pytest.raises(LeaveRequestNotFoundError):
            await LeaveRequestService(session).approve_leave_request(
                TENANT_ID,
                OTHER_REQUEST_ID,
                LeaveRequestDecision(decided_by_user_id=APPROVER_USER_ID),
            )
    finally:
        await session.close()
        await engine.dispose()
