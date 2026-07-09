from datetime import date
from uuid import UUID

import pytest
from app.db.base import Base
from app.models.employee import Employee, EmployeeStatus
from app.models.tenant import Tenant, TenantStatus
from app.schemas.employee import EmployeeListFilters, EmployeeUpdate
from app.services.employee_service import (
    EmployeeLifecycleError,
    EmployeeNotFoundError,
    EmployeeService,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

TENANT_ID = UUID("11111111-aaaa-4111-8111-111111111111")
OTHER_TENANT_ID = UUID("22222222-bbbb-4222-8222-222222222222")
EMPLOYEE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SECOND_EMPLOYEE_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
OTHER_EMPLOYEE_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


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
                department=" People ",
                position="People Partner",
                status=EmployeeStatus.ON_LEAVE.value,
                employment_start_date=date(2026, 7, 2),
            ),
            Employee(
                id=OTHER_EMPLOYEE_ID,
                tenant_id=OTHER_TENANT_ID,
                employee_number="OT-001",
                first_name="Other",
                last_name="Person",
                email="other@wealthyfalcon.test",
                department="People",
                status=EmployeeStatus.ACTIVE.value,
                employment_start_date=date(2026, 7, 1),
            ),
        ]
    )
    await session.commit()
    return session, engine


async def test_list_employees_department_filter_trims_stored_department() -> None:
    session, engine = await _session_with_seed_data()
    try:
        employees = await EmployeeService(session).list_employees(
            TENANT_ID,
            filters=EmployeeListFilters(department="people"),
        )

        assert [employee.employee_number for employee in employees] == ["WF-001", "WF-002"]
    finally:
        await session.close()
        await engine.dispose()


async def test_list_employees_treats_wildcard_search_as_literal_text() -> None:
    session, engine = await _session_with_seed_data()
    try:
        employees = await EmployeeService(session).list_employees(
            TENANT_ID,
            filters=EmployeeListFilters(q="%"),
        )

        assert employees == []
    finally:
        await session.close()
        await engine.dispose()


async def test_get_employee_is_tenant_scoped_at_service_boundary() -> None:
    session, engine = await _session_with_seed_data()
    try:
        with pytest.raises(EmployeeNotFoundError):
            await EmployeeService(session).get_employee(TENANT_ID, OTHER_EMPLOYEE_ID)
    finally:
        await session.close()
        await engine.dispose()


async def test_update_employee_can_keep_existing_employee_number() -> None:
    session, engine = await _session_with_seed_data()
    try:
        employee = await EmployeeService(session).update_employee(
            TENANT_ID,
            EMPLOYEE_ID,
            EmployeeUpdate(employee_number="WF-001", position="Senior HR Specialist"),
        )

        assert employee.employee_number == "WF-001"
        assert employee.position == "Senior HR Specialist"
    finally:
        await session.close()
        await engine.dispose()


async def test_update_employee_number_allows_match_in_different_tenant() -> None:
    session, engine = await _session_with_seed_data()
    try:
        employee = await EmployeeService(session).update_employee(
            TENANT_ID,
            EMPLOYEE_ID,
            EmployeeUpdate(employee_number="OT-001"),
        )

        other_employee = await session.scalar(
            select(Employee).where(Employee.id == OTHER_EMPLOYEE_ID)
        )
        assert employee.employee_number == "OT-001"
        assert other_employee is not None
        assert other_employee.employee_number == "OT-001"
        assert other_employee.tenant_id == OTHER_TENANT_ID
    finally:
        await session.close()
        await engine.dispose()


async def test_update_employee_rejects_constructed_null_status() -> None:
    session, engine = await _session_with_seed_data()
    try:
        payload = EmployeeUpdate.model_construct(_fields_set={"status"}, status=None)

        with pytest.raises(EmployeeLifecycleError, match="Employee status is required"):
            await EmployeeService(session).update_employee(TENANT_ID, EMPLOYEE_ID, payload)
    finally:
        await session.close()
        await engine.dispose()
