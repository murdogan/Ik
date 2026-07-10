from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.core.error_messages import LEAVE_REQUEST_ONLY_PENDING_CAN_BE_DECIDED_MESSAGE
from app.models.command_idempotency import CommandIdempotency
from app.models.employee import Employee
from app.models.leave_balance_summary import LeaveBalanceSummary
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.tenant import Tenant
from app.platform.db import (
    PersistenceConcurrencyError,
    SqlAlchemyUnitOfWork,
    constraint_name_from_error,
    sqlstate_from_error,
)
from app.schemas.leave_request import (
    LeaveRequestCreate,
    LeaveRequestDecision,
    LeaveRequestRead,
)
from app.services.command_idempotency import CommandIdempotencyService
from app.services.employee_commands import EmployeeCommandHandler
from app.services.employee_service import EmployeeNotFoundError, EmployeeService
from app.services.leave_request_commands import LeaveRequestCommandHandler
from app.services.leave_request_service import (
    LeaveRequestService,
    LeaveRequestTransitionError,
)
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"
_EMPLOYEE_HISTORY_CONSTRAINTS = {
    "fk_leave_requests_tenant_employee_id_employees",
    "fk_leave_balance_summaries_tenant_employee_id_employees",
}


@pytest.fixture
def p0e_migrated_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


def test_concurrent_approve_and_reject_have_one_persisted_winner(
    p0e_migrated_postgres_database: URL,
) -> None:
    asyncio.run(_assert_concurrent_decision_winner(p0e_migrated_postgres_database))


def test_concurrent_same_key_leave_create_replays_one_resource(
    p0e_migrated_postgres_database: URL,
) -> None:
    asyncio.run(_assert_concurrent_idempotent_leave_create(p0e_migrated_postgres_database))


def test_employee_archive_preserves_history_and_restricts_hard_delete(
    p0e_migrated_postgres_database: URL,
) -> None:
    asyncio.run(_assert_employee_archive_retention(p0e_migrated_postgres_database))


def test_p0e_downgrade_refuses_to_discard_retained_state(
    p0e_migrated_postgres_database: URL,
) -> None:
    seed = _tenant_seed()
    asyncio.run(_seed_p0e_downgrade_blockers(p0e_migrated_postgres_database, seed))
    config = _alembic_config(p0e_migrated_postgres_database)

    with pytest.raises(RuntimeError, match="P0E downgrade preflight failed"):
        alembic_command.downgrade(
            config,
            "0010_contract_tenant_relational_integrity",
        )

    assert asyncio.run(_current_revision(p0e_migrated_postgres_database)) == (
        "0011_p0e_concurrency_idempotency_archive"
    )
    asyncio.run(_remediate_p0e_downgrade_blockers(p0e_migrated_postgres_database))
    alembic_command.downgrade(
        config,
        "0010_contract_tenant_relational_integrity",
    )
    assert asyncio.run(_current_revision(p0e_migrated_postgres_database)) == (
        "0010_contract_tenant_relational_integrity"
    )
    alembic_command.upgrade(config, "head")


async def _assert_concurrent_decision_winner(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    seed = _tenant_seed()
    barrier = _AsyncBarrier(parties=2)
    try:
        await _seed_tenant_graph(engine, seed, include_balance=False)
        await _assert_decision_lock_is_acquired_during_read(session_factory, seed)

        async def decide(*, approve: bool):
            async with session_factory() as session:
                handler = LeaveRequestCommandHandler(
                    service=_DecisionBarrierLeaveRequestService(session, barrier),
                    unit_of_work=SqlAlchemyUnitOfWork(session),
                )
                if approve:
                    return await handler.approve_leave_request(
                        seed.tenant_id,
                        seed.leave_request_id,
                        LeaveRequestDecision(
                            decided_by_user_id=seed.approver_user_id,
                            decision_note="Approved concurrently",
                        ),
                    )
                return await handler.reject_leave_request(
                    seed.tenant_id,
                    seed.leave_request_id,
                    LeaveRequestDecision(
                        decided_by_user_id=seed.rejecter_user_id,
                        decision_note="Rejected concurrently",
                    ),
                )

        outcomes = await asyncio.wait_for(
            asyncio.gather(
                decide(approve=True),
                decide(approve=False),
                return_exceptions=True,
            ),
            timeout=10,
        )

        success_indexes = [
            index
            for index, outcome in enumerate(outcomes)
            if not isinstance(outcome, BaseException)
        ]
        failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        assert len(success_indexes) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], LeaveRequestTransitionError)
        assert str(failures[0]) == LEAVE_REQUEST_ONLY_PENDING_CAN_BE_DECIDED_MESSAGE

        winner_index = success_indexes[0]
        winner = LeaveRequestRead.model_validate(outcomes[winner_index])
        expected_status, expected_user_id, expected_note = (
            (
                LeaveRequestStatus.APPROVED,
                seed.approver_user_id,
                "Approved concurrently",
            )
            if winner_index == 0
            else (
                LeaveRequestStatus.REJECTED,
                seed.rejecter_user_id,
                "Rejected concurrently",
            )
        )
        assert winner.status == expected_status
        assert winner.decided_by_user_id == expected_user_id
        assert winner.decision_note == expected_note

        async with session_factory() as verification_session:
            persisted = await verification_session.get(LeaveRequest, seed.leave_request_id)
            assert persisted is not None
            assert persisted.tenant_id == seed.tenant_id
            assert persisted.status == expected_status.value
            assert persisted.decided_by_user_id == expected_user_id
            assert persisted.decision_note == expected_note
    finally:
        await engine.dispose()


async def _assert_decision_lock_is_acquired_during_read(
    session_factory: async_sessionmaker[AsyncSession],
    seed: _TenantSeed,
) -> None:
    async with session_factory() as locking_session:
        async with locking_session.begin():
            await locking_session.execute(
                select(LeaveRequest)
                .where(LeaveRequest.tenant_id == seed.tenant_id)
                .where(LeaveRequest.id == seed.leave_request_id)
                .with_for_update()
            )

            async with session_factory() as competing_session:
                service = _LockTimeoutLeaveRequestService(competing_session)
                handler = LeaveRequestCommandHandler(
                    service=service,
                    unit_of_work=SqlAlchemyUnitOfWork(competing_session),
                )
                with pytest.raises(PersistenceConcurrencyError):
                    await handler.reject_leave_request(
                        seed.tenant_id,
                        seed.leave_request_id,
                        LeaveRequestDecision(
                            decided_by_user_id=seed.rejecter_user_id,
                            decision_note="Lock probe",
                        ),
                    )

                assert service.read_returned is False


async def _assert_concurrent_idempotent_leave_create(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    seed = _tenant_seed()
    idempotency_key = f"p0e-leave-create-{uuid4().hex}"
    barrier = _AsyncBarrier(parties=2)
    payload = LeaveRequestCreate(
        employee_id=seed.employee_id,
        leave_type="annual",
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 12),
        requested_by_user_id=seed.requester_user_id,
    )
    try:
        await _seed_tenant_graph(
            engine,
            seed,
            include_leave_request=False,
            include_balance=False,
        )

        async def create_leave_request():
            async with session_factory() as session:
                handler = LeaveRequestCommandHandler(
                    service=LeaveRequestService(session),
                    unit_of_work=SqlAlchemyUnitOfWork(session),
                    idempotency=_ClaimBarrierIdempotencyService(session, barrier),
                )
                return await handler.create_leave_request(
                    seed.tenant_id,
                    payload,
                    idempotency_key=idempotency_key,
                )

        outcomes = await asyncio.wait_for(
            asyncio.gather(
                create_leave_request(),
                create_leave_request(),
            ),
            timeout=10,
        )
        responses = [LeaveRequestRead.model_validate(outcome) for outcome in outcomes]
        assert responses[0] == responses[1]
        assert responses[0].status == LeaveRequestStatus.PENDING

        async with session_factory() as verification_session:
            resource_count = await verification_session.scalar(
                select(func.count())
                .select_from(LeaveRequest)
                .where(LeaveRequest.tenant_id == seed.tenant_id)
            )
            receipts = list(
                await verification_session.scalars(
                    select(CommandIdempotency).where(
                        CommandIdempotency.tenant_id == seed.tenant_id
                    )
                )
            )

        assert resource_count == 1
        assert len(receipts) == 1
        receipt = receipts[0]
        assert receipt.idempotency_key == idempotency_key
        assert receipt.command_name == "leave_requests.create"
        assert receipt.resource_id == responses[0].id
        assert receipt.completed_at is not None
        assert receipt.response_payload == responses[0].model_dump(mode="json")
    finally:
        await engine.dispose()


async def _assert_employee_archive_retention(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    seed = _tenant_seed()
    other_seed = _tenant_seed()
    try:
        await _seed_tenant_graph(engine, seed)
        await _seed_tenant_graph(
            engine,
            other_seed,
            include_leave_request=False,
            include_balance=False,
        )

        async with session_factory() as wrong_tenant_session:
            wrong_tenant_handler = EmployeeCommandHandler(
                service=EmployeeService(wrong_tenant_session),
                unit_of_work=SqlAlchemyUnitOfWork(wrong_tenant_session),
            )
            with pytest.raises(EmployeeNotFoundError):
                await wrong_tenant_handler.delete_employee(
                    seed.tenant_id,
                    other_seed.employee_id,
                )

        async with session_factory() as archive_session:
            archive_handler = EmployeeCommandHandler(
                service=EmployeeService(archive_session),
                unit_of_work=SqlAlchemyUnitOfWork(archive_session),
            )
            await archive_handler.delete_employee(seed.tenant_id, seed.employee_id)

        async with session_factory() as verification_session:
            archived_employee = await verification_session.get(Employee, seed.employee_id)
            leave_request = await verification_session.get(
                LeaveRequest,
                seed.leave_request_id,
            )
            leave_balance = await verification_session.get(
                LeaveBalanceSummary,
                seed.leave_balance_id,
            )
            other_employee = await verification_session.get(Employee, other_seed.employee_id)

            assert archived_employee is not None
            assert archived_employee.tenant_id == seed.tenant_id
            assert archived_employee.archived_at is not None
            assert leave_request is not None
            assert leave_request.tenant_id == seed.tenant_id
            assert leave_request.employee_id == seed.employee_id
            assert leave_request.status == LeaveRequestStatus.PENDING.value
            assert leave_request.decided_by_user_id is None
            assert leave_request.decision_note is None
            assert leave_balance is not None
            assert leave_balance.tenant_id == seed.tenant_id
            assert leave_balance.employee_id == seed.employee_id
            assert leave_balance.opening_balance_days == 20
            assert leave_balance.used_days == 4
            assert leave_balance.planned_days == 2
            assert other_employee is not None
            assert other_employee.tenant_id == other_seed.tenant_id
            assert other_employee.archived_at is None

        async with session_factory() as hard_delete_session:
            with pytest.raises(IntegrityError) as error:
                async with hard_delete_session.begin():
                    await hard_delete_session.execute(
                        delete(Employee).where(Employee.id == seed.employee_id)
                    )

        assert sqlstate_from_error(error.value) == "23503"
        assert constraint_name_from_error(error.value) in _EMPLOYEE_HISTORY_CONSTRAINTS

        async with session_factory() as final_session:
            assert await final_session.get(Employee, seed.employee_id) is not None
            assert await final_session.get(LeaveRequest, seed.leave_request_id) is not None
            assert await final_session.get(LeaveBalanceSummary, seed.leave_balance_id) is not None
            other_employee = await final_session.get(Employee, other_seed.employee_id)
            assert other_employee is not None
            assert other_employee.archived_at is None

        async with session_factory() as retention_session:
            async with retention_session.begin():
                await retention_session.execute(
                    delete(Tenant).where(Tenant.id == seed.tenant_id)
                )

        async with session_factory() as retention_verification_session:
            assert (
                await retention_verification_session.get(Employee, seed.employee_id)
                is None
            )
            assert (
                await retention_verification_session.get(
                    LeaveRequest,
                    seed.leave_request_id,
                )
                is None
            )
            assert (
                await retention_verification_session.get(
                    LeaveBalanceSummary,
                    seed.leave_balance_id,
                )
                is None
            )
            other_employee = await retention_verification_session.get(
                Employee,
                other_seed.employee_id,
            )
            assert other_employee is not None
            assert other_employee.tenant_id == other_seed.tenant_id
    finally:
        await engine.dispose()


async def _seed_p0e_downgrade_blockers(
    database_url: URL,
    seed: _TenantSeed,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        await _seed_tenant_graph(
            engine,
            seed,
            include_leave_request=False,
            include_balance=False,
        )
        async with engine.begin() as connection:
            await connection.execute(
                text("update employees set archived_at = now() where id = :employee_id"),
                {"employee_id": seed.employee_id},
            )
            await connection.execute(
                text(
                    "insert into command_idempotency ("
                    "id, tenant_id, idempotency_key, command_name, request_fingerprint"
                    ") values ("
                    ":id, :tenant_id, :key, 'employees.create', :fingerprint"
                    ")"
                ),
                {
                    "id": uuid4(),
                    "tenant_id": seed.tenant_id,
                    "key": f"p0e-downgrade-{uuid4().hex}",
                    "fingerprint": "0" * 64,
                },
            )
    finally:
        await engine.dispose()


async def _remediate_p0e_downgrade_blockers(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("delete from command_idempotency"))
            await connection.execute(text("update employees set archived_at = null"))
    finally:
        await engine.dispose()


async def _current_revision(database_url: URL) -> str | None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("select version_num from alembic_version"))
    finally:
        await engine.dispose()


@dataclass(frozen=True, slots=True)
class _TenantSeed:
    tenant_id: UUID
    requester_user_id: UUID
    approver_user_id: UUID
    rejecter_user_id: UUID
    employee_id: UUID
    leave_request_id: UUID
    leave_balance_id: UUID


def _tenant_seed() -> _TenantSeed:
    return _TenantSeed(
        tenant_id=uuid4(),
        requester_user_id=uuid4(),
        approver_user_id=uuid4(),
        rejecter_user_id=uuid4(),
        employee_id=uuid4(),
        leave_request_id=uuid4(),
        leave_balance_id=uuid4(),
    )


async def _seed_tenant_graph(
    engine,
    seed: _TenantSeed,
    *,
    include_leave_request: bool = True,
    include_balance: bool = True,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into tenants ("
                "id, slug, name, status, plan_code, data_region, locale, timezone"
                ") values ("
                ":id, :slug, 'P0E tenant', 'active', 'core', 'tr-1', "
                "'tr-TR', 'Europe/Istanbul'"
                ")"
            ),
            {"id": seed.tenant_id, "slug": f"p0e-{uuid4().hex}"},
        )
        await connection.execute(
            text(
                "insert into users (id, tenant_id, email, full_name, status) values "
                "(:requester_id, :tenant_id, :requester_email, 'P0E Requester', 'active'), "
                "(:approver_id, :tenant_id, :approver_email, 'P0E Approver', 'active'), "
                "(:rejecter_id, :tenant_id, :rejecter_email, 'P0E Rejecter', 'active')"
            ),
            {
                "tenant_id": seed.tenant_id,
                "requester_id": seed.requester_user_id,
                "requester_email": f"requester-{uuid4().hex}@p0e.test",
                "approver_id": seed.approver_user_id,
                "approver_email": f"approver-{uuid4().hex}@p0e.test",
                "rejecter_id": seed.rejecter_user_id,
                "rejecter_email": f"rejecter-{uuid4().hex}@p0e.test",
            },
        )
        await connection.execute(
            text(
                "insert into employees ("
                "id, tenant_id, employee_number, first_name, last_name, status, "
                "employment_start_date"
                ") values ("
                ":id, :tenant_id, :employee_number, 'P0E', 'Employee', 'active', :start_date"
                ")"
            ),
            {
                "id": seed.employee_id,
                "tenant_id": seed.tenant_id,
                "employee_number": f"P0E-{uuid4().hex}",
                "start_date": date(2026, 7, 1),
            },
        )
        if include_leave_request:
            await connection.execute(
                text(
                    "insert into leave_requests ("
                    "id, tenant_id, employee_id, leave_type, start_date, end_date, status, "
                    "requested_by_user_id"
                    ") values ("
                    ":id, :tenant_id, :employee_id, 'annual', :start_date, :end_date, "
                    "'pending', :requester_id"
                    ")"
                ),
                {
                    "id": seed.leave_request_id,
                    "tenant_id": seed.tenant_id,
                    "employee_id": seed.employee_id,
                    "start_date": date(2026, 8, 1),
                    "end_date": date(2026, 8, 2),
                    "requester_id": seed.requester_user_id,
                },
            )
        if include_balance:
            await connection.execute(
                text(
                    "insert into leave_balance_summaries ("
                    "id, tenant_id, employee_id, leave_type, period_year, "
                    "opening_balance_days, used_days, planned_days"
                    ") values ("
                    ":id, :tenant_id, :employee_id, 'annual', 2026, 20, 4, 2"
                    ")"
                ),
                {
                    "id": seed.leave_balance_id,
                    "tenant_id": seed.tenant_id,
                    "employee_id": seed.employee_id,
                },
            )


@dataclass(slots=True)
class _AsyncBarrier:
    parties: int
    arrivals: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    ready: asyncio.Event = field(default_factory=asyncio.Event)

    async def wait(self) -> None:
        async with self.lock:
            self.arrivals += 1
            if self.arrivals == self.parties:
                self.ready.set()
        await asyncio.wait_for(self.ready.wait(), timeout=5)


class _DecisionBarrierLeaveRequestService(LeaveRequestService):
    def __init__(self, session: AsyncSession, barrier: _AsyncBarrier) -> None:
        super().__init__(session)
        self.barrier = barrier

    async def _get_leave_request(
        self,
        tenant_id: UUID,
        leave_request_id: UUID,
    ) -> LeaveRequest:
        await self.barrier.wait()
        return await super()._get_leave_request(tenant_id, leave_request_id)


class _LockTimeoutLeaveRequestService(LeaveRequestService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.read_returned = False

    async def _get_leave_request(
        self,
        tenant_id: UUID,
        leave_request_id: UUID,
    ) -> LeaveRequest:
        await self.session.execute(text("set local lock_timeout = '100ms'"))
        leave_request = await super()._get_leave_request(tenant_id, leave_request_id)
        self.read_returned = True
        return leave_request


class _ClaimBarrierIdempotencyService(CommandIdempotencyService):
    def __init__(self, session: AsyncSession, barrier: _AsyncBarrier) -> None:
        super().__init__(session)
        self.barrier = barrier

    async def _find(
        self,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> CommandIdempotency | None:
        receipt = await super()._find(tenant_id, idempotency_key)
        if receipt is None:
            await self.barrier.wait()
        return receipt


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config
