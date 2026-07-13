from collections.abc import AsyncIterator
from datetime import date
from types import SimpleNamespace
from typing import Annotated
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from app.api.auth_dependencies import require_authenticated_session
from app.api.dependencies import (
    get_authenticated_tenant_request_context,
    get_phase0_tenant_request_context,
)
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.employee import Employee, EmployeeStatus
from app.models.tenant import Tenant, TenantStatus
from app.platform.db import SqlAlchemyUnitOfWork
from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from app.services.employee_commands import EmployeeCommandHandler
from app.services.employee_service import EmployeeLifecycleError, EmployeeService
from fastapi import Depends
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
OTHER_EMPLOYEE_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")

EmployeeDatabase = tuple[AsyncEngine, async_sessionmaker[AsyncSession]]


@pytest.fixture
async def employee_database() -> AsyncIterator[EmployeeDatabase]:
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
                _employee(
                    employee_id=EMPLOYEE_ID,
                    tenant_id=TENANT_ID,
                    employee_number="WF-001",
                    first_name="Ada",
                ),
                _employee(
                    employee_id=OTHER_EMPLOYEE_ID,
                    tenant_id=OTHER_TENANT_ID,
                    employee_number="WF-001",
                    first_name="Other",
                ),
            ]
        )
        await session.commit()

    try:
        yield engine, session_factory
    finally:
        await engine.dispose()


async def test_employee_service_create_does_not_commit_and_can_be_rolled_back(
    employee_database: EmployeeDatabase,
) -> None:
    _, session_factory = employee_database
    async with session_factory() as session:
        commit = _forbid_service_commit(session)
        flush = _observe_service_flush(session)

        created = await EmployeeService(session).create_employee(
            TENANT_ID,
            _create_payload("WF-002"),
        )

        commit.assert_not_awaited()
        flush.assert_awaited_once_with()
        assert created.tenant_id == TENANT_ID
        assert created.employee_number == "WF-002"
        await session.rollback()

    async with session_factory() as verification_session:
        assert await _employee_by_number(verification_session, TENANT_ID, "WF-002") is None


async def test_employee_service_update_does_not_commit_and_can_be_rolled_back(
    employee_database: EmployeeDatabase,
) -> None:
    _, session_factory = employee_database
    async with session_factory() as session:
        commit = _forbid_service_commit(session)
        flush = _observe_service_flush(session)

        updated = await EmployeeService(session).update_employee(
            TENANT_ID,
            EMPLOYEE_ID,
            EmployeeUpdate(position="People Lead"),
        )

        commit.assert_not_awaited()
        flush.assert_awaited_once_with()
        assert updated.position == "People Lead"
        await session.rollback()

    async with session_factory() as verification_session:
        persisted = await verification_session.get(Employee, EMPLOYEE_ID)
        assert persisted is not None
        assert persisted.tenant_id == TENANT_ID
        assert persisted.position == "HR Specialist"


async def test_employee_service_archive_does_not_commit_and_can_be_rolled_back(
    employee_database: EmployeeDatabase,
) -> None:
    _, session_factory = employee_database
    async with session_factory() as session:
        commit = _forbid_service_commit(session)
        flush = _observe_service_flush(session)

        await EmployeeService(session).delete_employee(TENANT_ID, EMPLOYEE_ID)

        commit.assert_not_awaited()
        flush.assert_awaited_once_with()
        await session.rollback()

    async with session_factory() as verification_session:
        persisted = await verification_session.get(Employee, EMPLOYEE_ID)
        assert persisted is not None
        assert persisted.tenant_id == TENANT_ID
        assert persisted.archived_at is None


async def test_employee_command_handler_commits_a_successful_write(
    employee_database: EmployeeDatabase,
) -> None:
    _, session_factory = employee_database
    async with session_factory() as session:
        handler = EmployeeCommandHandler(
            service=EmployeeService(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
        )

        created = await handler.create_employee(TENANT_ID, _create_payload("WF-002"))
        created_id = created.id

    async with session_factory() as verification_session:
        persisted = await verification_session.get(Employee, created_id)
        assert persisted is not None
        assert persisted.tenant_id == TENANT_ID
        assert persisted.employee_number == "WF-002"


async def test_employee_command_handler_rolls_back_when_service_fails_after_flush(
    employee_database: EmployeeDatabase,
) -> None:
    _, session_factory = employee_database
    async with session_factory() as session:
        flush = _observe_service_flush(session)
        handler = EmployeeCommandHandler(
            service=_FailingAfterCreateFlushEmployeeService(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
        )

        with pytest.raises(EmployeeLifecycleError, match="downstream employee write failed"):
            await handler.create_employee(TENANT_ID, _create_payload("WF-ROLLBACK"))
        flush.assert_awaited_once_with()

    async with session_factory() as verification_session:
        assert await _employee_by_number(
            verification_session,
            TENANT_ID,
            "WF-ROLLBACK",
        ) is None
        assert await _employee_count(verification_session, OTHER_TENANT_ID) == 1


async def test_employee_unique_constraint_failure_maps_to_stable_conflict_envelope(
    employee_database: EmployeeDatabase,
) -> None:
    from app.api.employees import get_employee_command_handler

    _, session_factory = employee_database

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    def override_command_handler(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> EmployeeCommandHandler:
        return EmployeeCommandHandler(
            service=_StaleEmployeeNumberCheckService(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
        )

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_employee_command_handler] = override_command_handler
    app.dependency_overrides[get_authenticated_tenant_request_context] = (
        get_phase0_tenant_request_context
    )
    app.dependency_overrides[require_authenticated_session] = lambda: SimpleNamespace(
        user=SimpleNamespace(permissions=("employee:update:tenant",))
    )
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )
    try:
        response = await client.post(
            "/api/v1/employees",
            headers={
                "X-Tenant-Id": str(TENANT_ID),
                "X-Correlation-Id": "p0c-employee-unique-conflict",
            },
            json={
                "employee_number": "WF-001",
                "first_name": "Duplicate",
                "last_name": "Employee",
                "employment_start_date": "2026-07-10",
            },
        )

        assert response.status_code == 409
        assert response.json() == {
            "error": {
                "code": "employee_number_conflict",
                "message": "Employee number already exists for this tenant",
                "details": None,
                "correlation_id": "p0c-employee-unique-conflict",
            }
        }

        async with session_factory() as verification_session:
            assert await _employee_count(verification_session, TENANT_ID) == 1
            assert await _employee_count(verification_session, OTHER_TENANT_ID) == 1
            persisted = await _employee_by_number(verification_session, TENANT_ID, "WF-001")
            assert persisted is not None
            assert persisted.id == EMPLOYEE_ID
    finally:
        await client.aclose()


class _FailingAfterCreateFlushEmployeeService(EmployeeService):
    async def create_employee(self, tenant_id: UUID, payload: EmployeeCreate) -> Employee:
        await super().create_employee(tenant_id, payload)
        raise EmployeeLifecycleError("downstream employee write failed")


class _StaleEmployeeNumberCheckService(EmployeeService):
    async def _ensure_employee_number_available(
        self,
        tenant_id: UUID,
        employee_number: str,
        exclude_employee_id: UUID | None = None,
    ) -> None:
        # Simulate two requests having both passed the advisory availability query. The database
        # constraint remains authoritative, and the command/API boundary must map its failure.
        return None


def _forbid_service_commit(session: AsyncSession) -> AsyncMock:
    commit = AsyncMock(side_effect=AssertionError("EmployeeService must not commit"))
    session.commit = commit
    return commit


def _observe_service_flush(session: AsyncSession) -> AsyncMock:
    flush = AsyncMock(wraps=session.flush)
    session.flush = flush
    return flush


def _create_payload(employee_number: str) -> EmployeeCreate:
    return EmployeeCreate(
        employee_number=employee_number,
        first_name="New",
        last_name="Employee",
        employment_start_date=date(2026, 7, 10),
    )


def _employee(
    *,
    employee_id: UUID,
    tenant_id: UUID,
    employee_number: str,
    first_name: str,
) -> Employee:
    return Employee(
        id=employee_id,
        tenant_id=tenant_id,
        employee_number=employee_number,
        first_name=first_name,
        last_name="Employee",
        email=f"{first_name.casefold()}@example.test",
        department="People",
        position="HR Specialist",
        status=EmployeeStatus.ACTIVE.value,
        employment_start_date=date(2026, 7, 1),
    )


async def _employee_by_number(
    session: AsyncSession,
    tenant_id: UUID,
    employee_number: str,
) -> Employee | None:
    return await session.scalar(
        select(Employee)
        .where(Employee.tenant_id == tenant_id)
        .where(Employee.employee_number == employee_number)
    )


async def _employee_count(session: AsyncSession, tenant_id: UUID) -> int:
    count = await session.scalar(
        select(func.count()).select_from(Employee).where(Employee.tenant_id == tenant_id)
    )
    assert count is not None
    return count
