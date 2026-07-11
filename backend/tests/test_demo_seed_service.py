from uuid import UUID

import pytest
from app.db.base import Base
from app.models.employee import Employee
from app.models.leave_request import LeaveRequest
from app.models.tenant import Tenant, TenantSettings, TenantStatus
from app.models.user import User
from app.services.demo_seed_service import (
    DEMO_EMPLOYEES,
    DEMO_LEAVE_REQUESTS,
    DEMO_TENANTS,
    DEMO_USERS,
    DemoSeedConflictError,
    seed_demo_data,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool


async def _session_with_database() -> tuple[AsyncSession, AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        use_insertmanyvalues=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return AsyncSession(engine, expire_on_commit=False), engine


async def test_demo_seed_is_idempotent_and_tenant_scoped() -> None:
    session, engine = await _session_with_database()
    try:
        first_result = await seed_demo_data(session)

        employee_fixture = DEMO_EMPLOYEES[0]
        employee = await session.get(Employee, employee_fixture.id)
        assert employee is not None
        employee.department = "Changed"
        tenant_settings = await session.get(TenantSettings, DEMO_TENANTS[0].id)
        assert tenant_settings is not None
        tenant_settings.week_start_day = "sunday"
        await session.commit()

        second_result = await seed_demo_data(session)

        assert second_result == first_result
        assert await _count(session, Tenant) == len(DEMO_TENANTS)
        assert await _count(session, TenantSettings) == len(DEMO_TENANTS)
        assert await _count(session, User) == len(DEMO_USERS)
        assert await _count(session, Employee) == len(DEMO_EMPLOYEES)
        assert await _count(session, LeaveRequest) == len(DEMO_LEAVE_REQUESTS)
        assert set(second_result.tenant_ids) == {tenant.id for tenant in DEMO_TENANTS}

        updated_employee = await session.get(Employee, employee_fixture.id)
        assert updated_employee is not None
        assert updated_employee.department == employee_fixture.department
        preserved_settings = await session.get(TenantSettings, DEMO_TENANTS[0].id)
        assert preserved_settings is not None
        assert preserved_settings.week_start_day == "sunday"

        leave_requests = list(await session.scalars(select(LeaveRequest)))
        assert leave_requests
        for leave_request in leave_requests:
            employee = await session.get(Employee, leave_request.employee_id)
            requested_by_user = await session.get(User, leave_request.requested_by_user_id)
            decided_by_user = (
                await session.get(User, leave_request.decided_by_user_id)
                if leave_request.decided_by_user_id is not None
                else None
            )

            assert employee is not None
            assert requested_by_user is not None
            assert employee.tenant_id == leave_request.tenant_id
            assert requested_by_user.tenant_id == leave_request.tenant_id
            if decided_by_user is not None:
                assert decided_by_user.tenant_id == leave_request.tenant_id
    finally:
        await session.close()
        await engine.dispose()


async def test_demo_seed_service_flushes_without_completing_transaction() -> None:
    session, engine = await _session_with_database()
    try:
        await seed_demo_data(session)

        assert session.in_transaction() is True
        await session.rollback()

        async with AsyncSession(engine, expire_on_commit=False) as verification_session:
            assert await _count(verification_session, Tenant) == 0
            assert await _count(verification_session, TenantSettings) == 0
            assert await _count(verification_session, User) == 0
            assert await _count(verification_session, Employee) == 0
            assert await _count(verification_session, LeaveRequest) == 0
    finally:
        await session.close()
        await engine.dispose()


async def test_demo_seed_rejects_conflicting_existing_tenant_slug() -> None:
    session, engine = await _session_with_database()
    try:
        tenant_fixture = DEMO_TENANTS[0]
        session.add(
            Tenant(
                id=UUID("aaaaaaaa-9999-4999-8999-aaaaaaaaaaaa"),
                slug=tenant_fixture.slug,
                name="Conflicting Tenant",
                status=TenantStatus.ACTIVE.value,
                plan_code="core",
                data_region="tr-1",
                locale="en-US",
                timezone="Europe/Istanbul",
            )
        )
        await session.commit()

        with pytest.raises(DemoSeedConflictError):
            await seed_demo_data(session)
    finally:
        await session.close()
        await engine.dispose()


async def _count(session: AsyncSession, model: type[object]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)
