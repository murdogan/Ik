from datetime import date, datetime
from uuid import UUID

import pytest
from app.db.base import Base
from app.models.employee import Employee, EmployeeStatus
from app.models.tenant import Tenant, TenantStatus
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeListFilters,
    EmployeeListPagination,
    EmployeeUpdate,
)
from app.services.employee_service import (
    DuplicateEmployeeNumberError,
    EmployeeDateRangeError,
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
TERMINATED_EMPLOYEE_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")


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
            Employee(
                id=TERMINATED_EMPLOYEE_ID,
                tenant_id=TENANT_ID,
                employee_number="WF-003",
                first_name="Cem",
                last_name="Kaya",
                email="cem@wealthyfalcon.test",
                department="Engineering",
                position="Backend Engineer",
                status=EmployeeStatus.TERMINATED.value,
                employment_start_date=date(2026, 7, 1),
                employment_end_date=date(2026, 7, 31),
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


async def test_list_employees_accepts_constructed_raw_status_filter() -> None:
    session, engine = await _session_with_seed_data()
    try:
        filters = EmployeeListFilters.model_construct(status=EmployeeStatus.ON_LEAVE.value)

        employees = await EmployeeService(session).list_employees(TENANT_ID, filters=filters)

        assert [employee.employee_number for employee in employees] == ["WF-002"]
        assert {employee.tenant_id for employee in employees} == {TENANT_ID}
    finally:
        await session.close()
        await engine.dispose()


async def test_list_employees_paginates_after_tenant_scope() -> None:
    session, engine = await _session_with_seed_data()
    try:
        employees = await EmployeeService(session).list_employees(
            TENANT_ID,
            pagination=EmployeeListPagination(limit=1, offset=1),
        )

        assert [employee.employee_number for employee in employees] == ["WF-002"]
        assert {employee.tenant_id for employee in employees} == {TENANT_ID}
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


async def test_create_employee_rejects_duplicate_number_before_insert() -> None:
    session, engine = await _session_with_seed_data()
    try:
        existing_ids = set(
            await session.scalars(select(Employee.id).where(Employee.tenant_id == TENANT_ID))
        )

        with pytest.raises(DuplicateEmployeeNumberError):
            await EmployeeService(session).create_employee(
                TENANT_ID,
                EmployeeCreate(
                    employee_number="WF-001",
                    first_name="Duplicate",
                    last_name="Employee",
                    employment_start_date=date(2026, 7, 8),
                ),
            )

        current_ids = set(
            await session.scalars(select(Employee.id).where(Employee.tenant_id == TENANT_ID))
        )
        assert current_ids == existing_ids
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


async def test_update_employee_rejects_duplicate_number_without_mutation() -> None:
    session, engine = await _session_with_seed_data()
    try:
        payload = EmployeeUpdate(employee_number="WF-002", position="People Lead")

        with pytest.raises(DuplicateEmployeeNumberError):
            await EmployeeService(session).update_employee(TENANT_ID, EMPLOYEE_ID, payload)

        employee = await session.scalar(select(Employee).where(Employee.id == EMPLOYEE_ID))
        duplicate_owner = await session.scalar(
            select(Employee).where(Employee.id == SECOND_EMPLOYEE_ID)
        )
        assert employee is not None
        assert duplicate_owner is not None
        assert employee.employee_number == "WF-001"
        assert employee.position == "HR Specialist"
        assert duplicate_owner.employee_number == "WF-002"
    finally:
        await session.close()
        await engine.dispose()


async def test_update_employee_accepts_constructed_raw_status_when_lifecycle_is_complete() -> None:
    session, engine = await _session_with_seed_data()
    try:
        payload = EmployeeUpdate.model_construct(
            _fields_set={"status", "employment_end_date"},
            status=EmployeeStatus.TERMINATED.value,
            employment_end_date=date(2026, 7, 31),
        )

        employee = await EmployeeService(session).update_employee(TENANT_ID, EMPLOYEE_ID, payload)

        assert employee.status == EmployeeStatus.TERMINATED.value
        assert employee.employment_end_date == date(2026, 7, 31)
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


async def test_update_employee_rejects_constructed_null_start_date() -> None:
    session, engine = await _session_with_seed_data()
    try:
        payload = EmployeeUpdate.model_construct(
            _fields_set={"employment_start_date"},
            employment_start_date=None,
        )

        with pytest.raises(EmployeeDateRangeError, match="Employment start date is required"):
            await EmployeeService(session).update_employee(TENANT_ID, EMPLOYEE_ID, payload)
    finally:
        await session.close()
        await engine.dispose()


async def test_update_employee_rejects_constructed_end_date_for_active_without_mutation() -> None:
    session, engine = await _session_with_seed_data()
    try:
        payload = EmployeeUpdate.model_construct(
            _fields_set={"employment_end_date"},
            employment_end_date=date(2026, 7, 31),
        )

        with pytest.raises(EmployeeLifecycleError, match="only allowed"):
            await EmployeeService(session).update_employee(TENANT_ID, EMPLOYEE_ID, payload)

        employee = await session.scalar(select(Employee).where(Employee.id == EMPLOYEE_ID))
        assert employee is not None
        assert employee.status == EmployeeStatus.ACTIVE.value
        assert employee.employment_end_date is None
    finally:
        await session.close()
        await engine.dispose()


async def test_update_employee_rejects_constructed_datetime_start_date_without_mutation() -> None:
    session, engine = await _session_with_seed_data()
    try:
        payload = EmployeeUpdate.model_construct(
            _fields_set={"employment_start_date"},
            employment_start_date=datetime(2026, 7, 8),
        )

        with pytest.raises(EmployeeDateRangeError, match="date without time"):
            await EmployeeService(session).update_employee(TENANT_ID, EMPLOYEE_ID, payload)

        employee = await session.scalar(select(Employee).where(Employee.id == EMPLOYEE_ID))
        assert employee is not None
        assert employee.employment_start_date == date(2026, 7, 1)
    finally:
        await session.close()
        await engine.dispose()


async def test_update_employee_rejects_constructed_datetime_end_date_without_mutation() -> None:
    session, engine = await _session_with_seed_data()
    try:
        payload = EmployeeUpdate.model_construct(
            _fields_set={"employment_end_date"},
            employment_end_date=datetime(2026, 7, 31),
        )

        with pytest.raises(EmployeeDateRangeError, match="date without time"):
            await EmployeeService(session).update_employee(TENANT_ID, EMPLOYEE_ID, payload)

        employee = await session.scalar(select(Employee).where(Employee.id == EMPLOYEE_ID))
        assert employee is not None
        assert employee.employment_end_date is None
    finally:
        await session.close()
        await engine.dispose()


async def test_update_employee_rejects_start_after_existing_end_without_mutation() -> None:
    session, engine = await _session_with_seed_data()
    try:
        payload = EmployeeUpdate(employment_start_date=date(2026, 8, 1))

        with pytest.raises(EmployeeDateRangeError, match="on or after start date"):
            await EmployeeService(session).update_employee(
                TENANT_ID,
                TERMINATED_EMPLOYEE_ID,
                payload,
            )

        employee = await session.scalar(
            select(Employee).where(Employee.id == TERMINATED_EMPLOYEE_ID)
        )
        assert employee is not None
        assert employee.employment_start_date == date(2026, 7, 1)
        assert employee.employment_end_date == date(2026, 7, 31)
        assert employee.status == EmployeeStatus.TERMINATED.value
    finally:
        await session.close()
        await engine.dispose()


async def test_update_employee_allows_reactivation_when_end_date_is_cleared() -> None:
    session, engine = await _session_with_seed_data()
    try:
        employee = await EmployeeService(session).update_employee(
            TENANT_ID,
            TERMINATED_EMPLOYEE_ID,
            EmployeeUpdate(status=EmployeeStatus.ACTIVE, employment_end_date=None),
        )

        assert employee.status == EmployeeStatus.ACTIVE.value
        assert employee.employment_end_date is None
    finally:
        await session.close()
        await engine.dispose()


async def test_delete_employee_archives_idempotently_without_cross_tenant_mutation() -> None:
    session, engine = await _session_with_seed_data()
    try:
        with pytest.raises(EmployeeNotFoundError):
            await EmployeeService(session).delete_employee(TENANT_ID, OTHER_EMPLOYEE_ID)

        other_employee = await session.scalar(
            select(Employee).where(Employee.id == OTHER_EMPLOYEE_ID)
        )
        assert other_employee is not None
        assert other_employee.tenant_id == OTHER_TENANT_ID

        await EmployeeService(session).delete_employee(TENANT_ID, EMPLOYEE_ID)

        archived_employee = await session.scalar(
            select(Employee).where(Employee.id == EMPLOYEE_ID)
        )
        assert archived_employee is not None
        assert archived_employee.archived_at is not None
        archived_at = archived_employee.archived_at

        await EmployeeService(session).delete_employee(TENANT_ID, EMPLOYEE_ID)

        assert archived_employee.archived_at == archived_at
        with pytest.raises(EmployeeNotFoundError):
            await EmployeeService(session).get_employee(TENANT_ID, EMPLOYEE_ID)
        listed_ids = {
            employee.id
            for employee in await EmployeeService(session).list_employees(TENANT_ID)
        }
        assert EMPLOYEE_ID not in listed_ids
        with pytest.raises(DuplicateEmployeeNumberError):
            await EmployeeService(session).create_employee(
                TENANT_ID,
                EmployeeCreate(
                    employee_number="WF-001",
                    first_name="Replacement",
                    last_name="Employee",
                    employment_start_date=date(2026, 7, 10),
                ),
            )
    finally:
        await session.close()
        await engine.dispose()
