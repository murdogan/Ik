from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_messages import (
    EMPLOYEE_END_DATE_MUST_BE_DATE_MESSAGE,
    EMPLOYEE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE,
    EMPLOYEE_END_DATE_ONLY_FOR_TERMINATED_MESSAGE,
    EMPLOYEE_START_DATE_MUST_BE_DATE_MESSAGE,
    EMPLOYEE_START_DATE_REQUIRED_MESSAGE,
    EMPLOYEE_STATUS_REQUIRED_MESSAGE,
    EMPLOYEE_TERMINATED_REQUIRES_END_DATE_MESSAGE,
)
from app.models.employee import Employee, EmployeeStatus
from app.platform.db import constraint_name_from_error
from app.platform.errors.application import ApplicationError
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeListFilters,
    EmployeeListPagination,
    EmployeeUpdate,
)

EMPLOYEE_NUMBER_UNIQUE_CONSTRAINT = "uq_employees_tenant_employee_number"
_SQLITE_EMPLOYEE_NUMBER_UNIQUE_SIGNATURE = (
    "UNIQUE constraint failed: employees.tenant_id, employees.employee_number"
)


class EmployeeNotFoundError(ApplicationError):
    pass


class DuplicateEmployeeNumberError(ApplicationError):
    pass


class EmployeeDateRangeError(ApplicationError, ValueError):
    pass


class EmployeeLifecycleError(ApplicationError, ValueError):
    pass


class EmployeeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_employees(
        self,
        tenant_id: UUID,
        filters: EmployeeListFilters | None = None,
        pagination: EmployeeListPagination | None = None,
    ) -> list[Employee]:
        filters = filters or EmployeeListFilters()
        pagination = pagination or EmployeeListPagination()
        statement = select(Employee).where(Employee.tenant_id == tenant_id)

        if filters.department is not None:
            statement = statement.where(
                func.lower(func.trim(Employee.department)) == filters.department.casefold()
            )
        if filters.status is not None:
            statement = statement.where(Employee.status == _status_value(filters.status))
        if filters.q is not None:
            search_term = filters.q.casefold()
            statement = statement.where(
                or_(
                    func.lower(Employee.employee_number).contains(search_term, autoescape=True),
                    func.lower(Employee.email).contains(search_term, autoescape=True),
                )
            )

        statement = (
            statement.order_by(Employee.employee_number.asc())
            .offset(pagination.offset)
            .limit(pagination.limit)
        )
        return list(await self.session.scalars(statement))

    async def get_employee(self, tenant_id: UUID, employee_id: UUID) -> Employee:
        employee = await self._get_employee_or_none(tenant_id, employee_id)
        if employee is None:
            raise EmployeeNotFoundError
        return employee

    async def create_employee(self, tenant_id: UUID, payload: EmployeeCreate) -> Employee:
        _validate_employment_lifecycle(
            status=payload.status,
            start_date=payload.employment_start_date,
            end_date=payload.employment_end_date,
        )
        await self._ensure_employee_number_available(
            tenant_id=tenant_id,
            employee_number=payload.employee_number,
        )
        employee = Employee(
            id=uuid4(),
            tenant_id=tenant_id,
            **_employee_create_values(payload),
        )
        self.session.add(employee)
        await self._flush_employee_write()
        await self.session.refresh(employee)
        return employee

    async def update_employee(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeeUpdate,
    ) -> Employee:
        employee = await self.get_employee(tenant_id, employee_id)
        values = _employee_update_values(payload)

        if "employee_number" in values and values["employee_number"] != employee.employee_number:
            await self._ensure_employee_number_available(
                tenant_id=tenant_id,
                employee_number=values["employee_number"],
                exclude_employee_id=employee_id,
            )

        next_status = values.get("status", employee.status)
        next_start_date = values.get("employment_start_date", employee.employment_start_date)
        next_end_date = values.get("employment_end_date", employee.employment_end_date)
        _validate_employment_lifecycle(
            status=next_status,
            start_date=next_start_date,
            end_date=next_end_date,
        )

        for field_name, value in values.items():
            setattr(employee, field_name, value)

        await self._flush_employee_write()
        await self.session.refresh(employee)
        return employee

    async def delete_employee(self, tenant_id: UUID, employee_id: UUID) -> None:
        employee = await self.get_employee(tenant_id, employee_id)
        await self.session.delete(employee)
        await self.session.flush()

    async def _flush_employee_write(self) -> None:
        try:
            await self.session.flush()
        except IntegrityError as exc:
            if _is_employee_number_unique_violation(exc):
                raise DuplicateEmployeeNumberError from exc
            raise

    async def _get_employee_or_none(self, tenant_id: UUID, employee_id: UUID) -> Employee | None:
        statement = (
            select(Employee)
            .where(Employee.tenant_id == tenant_id)
            .where(Employee.id == employee_id)
        )
        return await self.session.scalar(statement)

    async def _ensure_employee_number_available(
        self,
        tenant_id: UUID,
        employee_number: str,
        exclude_employee_id: UUID | None = None,
    ) -> None:
        statement = (
            select(Employee.id)
            .where(Employee.tenant_id == tenant_id)
            .where(Employee.employee_number == employee_number)
        )
        if exclude_employee_id is not None:
            statement = statement.where(Employee.id != exclude_employee_id)

        if await self.session.scalar(statement) is not None:
            raise DuplicateEmployeeNumberError


def _employee_create_values(payload: EmployeeCreate) -> dict[str, object]:
    values = payload.model_dump()
    values["status"] = _status_value(values["status"])
    return values


def _employee_update_values(payload: EmployeeUpdate) -> dict[str, object]:
    values = {
        field_name: getattr(payload, field_name)
        for field_name in EmployeeUpdate.model_fields
        if field_name in payload.model_fields_set
    }
    if "status" in values:
        values["status"] = _status_value(values["status"])
    return values


def _status_value(status: EmployeeStatus | str | None) -> str | None:
    if isinstance(status, EmployeeStatus):
        return status.value
    return status


def _is_employee_number_unique_violation(exc: IntegrityError) -> bool:
    if constraint_name_from_error(exc) == EMPLOYEE_NUMBER_UNIQUE_CONSTRAINT:
        return True
    return _SQLITE_EMPLOYEE_NUMBER_UNIQUE_SIGNATURE in str(exc.orig)


def _validate_date_order(start_date: date, end_date: date | None) -> None:
    if end_date is not None and end_date < start_date:
        raise EmployeeDateRangeError(EMPLOYEE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE)


def _validate_employment_lifecycle(
    *,
    status: EmployeeStatus | str | None,
    start_date: object,
    end_date: object,
) -> None:
    start_date = _required_employment_date(
        start_date,
        missing_message=EMPLOYEE_START_DATE_REQUIRED_MESSAGE,
        invalid_message=EMPLOYEE_START_DATE_MUST_BE_DATE_MESSAGE,
    )
    end_date = _optional_employment_date(
        end_date,
        invalid_message=EMPLOYEE_END_DATE_MUST_BE_DATE_MESSAGE,
    )
    _validate_date_order(start_date, end_date)

    status_value = _status_value(status)
    if status_value is None:
        raise EmployeeLifecycleError(EMPLOYEE_STATUS_REQUIRED_MESSAGE)
    if status_value == EmployeeStatus.TERMINATED.value:
        if end_date is None:
            raise EmployeeLifecycleError(EMPLOYEE_TERMINATED_REQUIRES_END_DATE_MESSAGE)
        return
    if end_date is not None:
        raise EmployeeLifecycleError(EMPLOYEE_END_DATE_ONLY_FOR_TERMINATED_MESSAGE)


def _required_employment_date(
    value: object,
    *,
    missing_message: str,
    invalid_message: str,
) -> date:
    if value is None:
        raise EmployeeDateRangeError(missing_message)
    if isinstance(value, datetime) or not isinstance(value, date):
        raise EmployeeDateRangeError(invalid_message)
    return value


def _optional_employment_date(
    value: object,
    *,
    invalid_message: str,
) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise EmployeeDateRangeError(invalid_message)
    return value
