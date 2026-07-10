from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID

import pytest
from app.db.base import Base
from app.models.command_idempotency import CommandIdempotency
from app.models.employee import Employee, EmployeeStatus
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.db import SqlAlchemyUnitOfWork
from app.platform.idempotency import IdempotencyKeyMismatchError
from app.schemas.employee import EmployeeCreate, EmployeeRead
from app.schemas.leave_request import (
    LeaveRequestCreate,
    LeaveRequestDecision,
    LeaveRequestRead,
)
from app.services.command_idempotency import CommandIdempotencyService
from app.services.employee_commands import EmployeeCommandHandler
from app.services.employee_service import EmployeeService
from app.services.leave_request_commands import LeaveRequestCommandHandler
from app.services.leave_request_service import (
    LeaveRequestEmployeeNotFoundError,
    LeaveRequestService,
)
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

TENANT_ID = UUID("11111111-aaaa-4111-8111-111111111111")
OTHER_TENANT_ID = UUID("22222222-bbbb-4222-8222-222222222222")
EMPLOYEE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
OTHER_EMPLOYEE_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
RECOVERABLE_EMPLOYEE_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
REQUESTING_USER_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
APPROVER_USER_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
OTHER_USER_ID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
PENDING_REQUEST_ID = UUID("aaaaaaaa-1111-4aaa-8aaa-aaaaaaaa1111")


@pytest.fixture
async def idempotency_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        use_insertmanyvalues=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory.begin() as session:
        session.add_all(
            [
                _tenant(TENANT_ID, "wealthy-falcon"),
                _tenant(OTHER_TENANT_ID, "other-tenant"),
                _user(
                    REQUESTING_USER_ID,
                    TENANT_ID,
                    "requester@wealthyfalcon.test",
                ),
                _user(
                    APPROVER_USER_ID,
                    TENANT_ID,
                    "approver@wealthyfalcon.test",
                ),
                _user(
                    OTHER_USER_ID,
                    OTHER_TENANT_ID,
                    "requester@other.test",
                ),
                _employee(
                    EMPLOYEE_ID,
                    TENANT_ID,
                    "WF-SEED",
                ),
                _employee(
                    OTHER_EMPLOYEE_ID,
                    OTHER_TENANT_ID,
                    "OT-SEED",
                ),
                LeaveRequest(
                    id=PENDING_REQUEST_ID,
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type="annual",
                    start_date=date(2026, 8, 10),
                    end_date=date(2026, 8, 12),
                    status=LeaveRequestStatus.PENDING.value,
                    requested_by_user_id=REQUESTING_USER_ID,
                ),
            ]
        )

    try:
        yield session_factory
    finally:
        await engine.dispose()


async def test_employee_create_retry_replays_same_snapshot_and_single_write(
    idempotency_sessions: async_sessionmaker[AsyncSession],
) -> None:
    first_payload = EmployeeCreate(
        employee_number=" IDEMP-001 ",
        first_name=" Ada ",
        last_name=" Lovelace ",
        email=" ada.idempotent@wealthyfalcon.test ",
        employment_start_date=date(2026, 7, 10),
    )
    retry_payload = EmployeeCreate(
        employee_number="IDEMP-001",
        first_name="Ada",
        last_name="Lovelace",
        email="ada.idempotent@wealthyfalcon.test",
        department=None,
        position=None,
        status=EmployeeStatus.ACTIVE,
        employment_start_date=date(2026, 7, 10),
        employment_end_date=None,
    )
    assert first_payload.model_dump(mode="json") == retry_payload.model_dump(mode="json")

    first = await _create_employee(
        idempotency_sessions,
        TENANT_ID,
        first_payload,
        idempotency_key="employee-create-retry",
    )
    async with idempotency_sessions.begin() as session:
        await session.execute(
            update(Employee)
            .where(Employee.id == first.id)
            .values(first_name="Changed after create")
        )
    replay = await _create_employee(
        idempotency_sessions,
        TENANT_ID,
        retry_payload,
        idempotency_key="employee-create-retry",
    )

    assert replay == first
    assert replay.id == first.id
    async with idempotency_sessions() as session:
        assert await _count_rows(
            session,
            Employee,
            Employee.tenant_id == TENANT_ID,
            Employee.employee_number == "IDEMP-001",
        ) == 1
        assert await _count_rows(
            session,
            CommandIdempotency,
            CommandIdempotency.tenant_id == TENANT_ID,
            CommandIdempotency.idempotency_key == "employee-create-retry",
        ) == 1


async def test_reused_key_rejects_changed_payload_or_command_without_second_write(
    idempotency_sessions: async_sessionmaker[AsyncSession],
) -> None:
    idempotency_key = "tenant-command-key"
    original_payload = _employee_create_payload("IDEMP-ORIGINAL", first_name="Original")
    original = await _create_employee(
        idempotency_sessions,
        TENANT_ID,
        original_payload,
        idempotency_key=idempotency_key,
    )

    async with idempotency_sessions() as session:
        with pytest.raises(IdempotencyKeyMismatchError):
            await _employee_handler(session).create_employee(
                TENANT_ID,
                _employee_create_payload("IDEMP-CHANGED", first_name="Changed"),
                idempotency_key,
            )

    async with idempotency_sessions() as session:
        with pytest.raises(IdempotencyKeyMismatchError):
            await _leave_handler(session).create_leave_request(
                TENANT_ID,
                _leave_create_payload(leave_type="wellbeing"),
                idempotency_key,
            )

    async with idempotency_sessions() as session:
        employees = list(
            await session.scalars(
                select(Employee)
                .where(Employee.tenant_id == TENANT_ID)
                .where(Employee.employee_number.in_(["IDEMP-ORIGINAL", "IDEMP-CHANGED"]))
            )
        )
        assert [(employee.id, employee.employee_number) for employee in employees] == [
            (original.id, "IDEMP-ORIGINAL")
        ]
        assert await _count_rows(
            session,
            LeaveRequest,
            LeaveRequest.tenant_id == TENANT_ID,
            LeaveRequest.leave_type == "wellbeing",
        ) == 0
        assert await _count_rows(
            session,
            CommandIdempotency,
            CommandIdempotency.tenant_id == TENANT_ID,
            CommandIdempotency.idempotency_key == idempotency_key,
        ) == 1


async def test_same_key_is_independent_across_tenants(
    idempotency_sessions: async_sessionmaker[AsyncSession],
) -> None:
    idempotency_key = "shared-cross-tenant-key"
    payload = _employee_create_payload("SHARED-001", first_name="Shared")

    current_tenant = await _create_employee(
        idempotency_sessions,
        TENANT_ID,
        payload,
        idempotency_key=idempotency_key,
    )
    other_tenant = await _create_employee(
        idempotency_sessions,
        OTHER_TENANT_ID,
        payload,
        idempotency_key=idempotency_key,
    )

    assert current_tenant.id != other_tenant.id
    async with idempotency_sessions() as session:
        assert await _count_rows(
            session,
            Employee,
            Employee.employee_number == "SHARED-001",
        ) == 2
        assert await _count_rows(
            session,
            CommandIdempotency,
            CommandIdempotency.idempotency_key == idempotency_key,
        ) == 2
        receipt_tenants = set(
            await session.scalars(
                select(CommandIdempotency.tenant_id).where(
                    CommandIdempotency.idempotency_key == idempotency_key
                )
            )
        )
        assert receipt_tenants == {TENANT_ID, OTHER_TENANT_ID}


async def test_keyed_leave_create_retry_writes_one_request(
    idempotency_sessions: async_sessionmaker[AsyncSession],
) -> None:
    payload = _leave_create_payload(leave_type="wellbeing")
    idempotency_key = "leave-create-retry"

    first = await _create_leave_request(
        idempotency_sessions,
        TENANT_ID,
        payload,
        idempotency_key=idempotency_key,
    )
    replay = await _create_leave_request(
        idempotency_sessions,
        TENANT_ID,
        payload,
        idempotency_key=idempotency_key,
    )

    assert replay == first
    assert replay.id == first.id
    async with idempotency_sessions() as session:
        assert await _count_rows(
            session,
            LeaveRequest,
            LeaveRequest.tenant_id == TENANT_ID,
            LeaveRequest.leave_type == "wellbeing",
        ) == 1
        assert await _count_rows(
            session,
            CommandIdempotency,
            CommandIdempotency.tenant_id == TENANT_ID,
            CommandIdempotency.idempotency_key == idempotency_key,
        ) == 1


async def test_keyed_decision_retry_replays_successful_terminal_result(
    idempotency_sessions: async_sessionmaker[AsyncSession],
) -> None:
    payload = LeaveRequestDecision(
        decided_by_user_id=APPROVER_USER_ID,
        decision_note="Approved with idempotent retry",
    )
    idempotency_key = "leave-approval-retry"

    first = await _approve_leave_request(
        idempotency_sessions,
        payload,
        idempotency_key=idempotency_key,
    )
    replay = await _approve_leave_request(
        idempotency_sessions,
        payload,
        idempotency_key=idempotency_key,
    )

    assert replay == first
    assert replay.id == PENDING_REQUEST_ID
    assert replay.status == LeaveRequestStatus.APPROVED
    async with idempotency_sessions() as session:
        persisted = await session.get(LeaveRequest, PENDING_REQUEST_ID)
        assert persisted is not None
        assert persisted.status == LeaveRequestStatus.APPROVED.value
        assert persisted.decided_by_user_id == APPROVER_USER_ID
        assert persisted.decision_note == "Approved with idempotent retry"
        assert await _count_rows(
            session,
            CommandIdempotency,
            CommandIdempotency.tenant_id == TENANT_ID,
            CommandIdempotency.idempotency_key == idempotency_key,
        ) == 1


async def test_failed_keyed_command_rolls_back_receipt_and_can_be_retried(
    idempotency_sessions: async_sessionmaker[AsyncSession],
) -> None:
    idempotency_key = "recoverable-leave-create"
    payload = LeaveRequestCreate(
        employee_id=RECOVERABLE_EMPLOYEE_ID,
        leave_type="annual",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 2),
        requested_by_user_id=REQUESTING_USER_ID,
    )

    async with idempotency_sessions() as session:
        with pytest.raises(LeaveRequestEmployeeNotFoundError):
            await _leave_handler(session).create_leave_request(
                TENANT_ID,
                payload,
                idempotency_key,
            )

    async with idempotency_sessions() as session:
        assert await _count_rows(
            session,
            CommandIdempotency,
            CommandIdempotency.tenant_id == TENANT_ID,
            CommandIdempotency.idempotency_key == idempotency_key,
        ) == 0
        assert await _count_rows(
            session,
            LeaveRequest,
            LeaveRequest.tenant_id == TENANT_ID,
            LeaveRequest.employee_id == RECOVERABLE_EMPLOYEE_ID,
        ) == 0

    async with idempotency_sessions.begin() as session:
        session.add(
            _employee(
                RECOVERABLE_EMPLOYEE_ID,
                TENANT_ID,
                "WF-RECOVERED",
            )
        )

    recovered = await _create_leave_request(
        idempotency_sessions,
        TENANT_ID,
        payload,
        idempotency_key=idempotency_key,
    )

    async with idempotency_sessions() as session:
        assert await _count_rows(
            session,
            CommandIdempotency,
            CommandIdempotency.tenant_id == TENANT_ID,
            CommandIdempotency.idempotency_key == idempotency_key,
        ) == 1
        persisted = await session.get(LeaveRequest, recovered.id)
        assert persisted is not None
        assert persisted.employee_id == RECOVERABLE_EMPLOYEE_ID


def _employee_handler(session: AsyncSession) -> EmployeeCommandHandler:
    return EmployeeCommandHandler(
        service=EmployeeService(session),
        unit_of_work=SqlAlchemyUnitOfWork(session),
        idempotency=CommandIdempotencyService(session),
    )


def _leave_handler(session: AsyncSession) -> LeaveRequestCommandHandler:
    return LeaveRequestCommandHandler(
        service=LeaveRequestService(session),
        unit_of_work=SqlAlchemyUnitOfWork(session),
        idempotency=CommandIdempotencyService(session),
    )


async def _create_employee(
    sessions: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    payload: EmployeeCreate,
    *,
    idempotency_key: str,
) -> EmployeeRead:
    async with sessions() as session:
        result = await _employee_handler(session).create_employee(
            tenant_id,
            payload,
            idempotency_key,
        )
        return EmployeeRead.model_validate(result)


async def _create_leave_request(
    sessions: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    payload: LeaveRequestCreate,
    *,
    idempotency_key: str,
) -> LeaveRequestRead:
    async with sessions() as session:
        result = await _leave_handler(session).create_leave_request(
            tenant_id,
            payload,
            idempotency_key,
        )
        return LeaveRequestRead.model_validate(result)


async def _approve_leave_request(
    sessions: async_sessionmaker[AsyncSession],
    payload: LeaveRequestDecision,
    *,
    idempotency_key: str,
) -> LeaveRequestRead:
    async with sessions() as session:
        result = await _leave_handler(session).approve_leave_request(
            TENANT_ID,
            PENDING_REQUEST_ID,
            payload,
            idempotency_key,
        )
        return LeaveRequestRead.model_validate(result)


async def _count_rows(
    session: AsyncSession,
    model: type,
    *criteria,
) -> int:
    row_count = await session.scalar(
        select(func.count()).select_from(model).where(*criteria)
    )
    assert row_count is not None
    return row_count


def _employee_create_payload(
    employee_number: str,
    *,
    first_name: str,
) -> EmployeeCreate:
    return EmployeeCreate(
        employee_number=employee_number,
        first_name=first_name,
        last_name="Idempotent",
        employment_start_date=date(2026, 7, 10),
    )


def _leave_create_payload(*, leave_type: str) -> LeaveRequestCreate:
    return LeaveRequestCreate(
        employee_id=EMPLOYEE_ID,
        leave_type=leave_type,
        start_date=date(2026, 8, 20),
        end_date=date(2026, 8, 21),
        requested_by_user_id=REQUESTING_USER_ID,
    )


def _tenant(tenant_id: UUID, slug: str) -> Tenant:
    return Tenant(
        id=tenant_id,
        slug=slug,
        name=slug.replace("-", " ").title(),
        status=TenantStatus.ACTIVE.value,
        plan_code="core",
        data_region="tr-1",
        locale="tr-TR",
        timezone="Europe/Istanbul",
    )


def _user(user_id: UUID, tenant_id: UUID, email: str) -> User:
    return User(
        id=user_id,
        tenant_id=tenant_id,
        email=email,
        full_name="Idempotency User",
        status=UserStatus.ACTIVE.value,
    )


def _employee(employee_id: UUID, tenant_id: UUID, employee_number: str) -> Employee:
    return Employee(
        id=employee_id,
        tenant_id=tenant_id,
        employee_number=employee_number,
        first_name="Seed",
        last_name="Employee",
        status=EmployeeStatus.ACTIVE.value,
        employment_start_date=date(2026, 7, 1),
    )
