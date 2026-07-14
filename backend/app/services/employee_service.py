from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, exists, func, or_, select
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
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_profile import (
    EmployeeEmploymentProfile,
    EmployeePersonalProfile,
)
from app.models.organization import Branch, LegalEntity
from app.models.position import Position
from app.platform.db import constraint_name_from_error
from app.platform.errors.application import ApplicationError
from app.platform.pagination import CursorPage
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeListCursor,
    EmployeeListFilters,
    EmployeeListPagination,
    EmployeeUpdate,
)

EMPLOYEE_NUMBER_UNIQUE_CONSTRAINT = "uq_employees_tenant_employee_number"
EMPLOYEE_NUMBER_NORMALIZED_UNIQUE_CONSTRAINT = (
    "uq_employees_tenant_employee_number_normalized"
)
EMPLOYEE_WORK_EMAIL_NORMALIZED_UNIQUE_CONSTRAINT = "uq_employees_tenant_email_normalized"
_SQLITE_EMPLOYEE_NUMBER_UNIQUE_SIGNATURE = (
    "UNIQUE constraint failed: employees.tenant_id, employees.employee_number"
)
_SQLITE_EMPLOYEE_NUMBER_NORMALIZED_UNIQUE_SIGNATURE = (
    "UNIQUE constraint failed: employees.tenant_id, employees.employee_number_normalized"
)
_SQLITE_EMPLOYEE_WORK_EMAIL_NORMALIZED_UNIQUE_SIGNATURE = (
    "UNIQUE constraint failed: employees.tenant_id, employees.email_normalized"
)


class EmployeeNotFoundError(ApplicationError):
    pass


class DuplicateEmployeeNumberError(ApplicationError):
    pass


class DuplicateWorkEmailError(ApplicationError):
    pass


class EmployeeDateRangeError(ApplicationError, ValueError):
    pass


class EmployeeLifecycleError(ApplicationError, ValueError):
    pass


class EmployeeVersionConflictError(ApplicationError):
    pass


@dataclass(frozen=True, slots=True)
class EmployeeReadProjection:
    """Legacy employee shape with structured current organization values when present."""

    id: UUID
    tenant_id: UUID
    employee_number: str
    first_name: str
    last_name: str
    email: str | None
    department: str | None
    position: str | None
    status: str
    employment_start_date: date
    employment_end_date: date | None
    version: int
    current_assignment: EmployeeCurrentAssignmentProjection | None


@dataclass(frozen=True, slots=True)
class EmployeeOrganizationReferenceProjection:
    id: UUID
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class EmployeePositionReferenceProjection:
    id: UUID
    code: str
    title: str


@dataclass(frozen=True, slots=True)
class EmployeeCurrentAssignmentProjection:
    id: UUID
    legal_entity: EmployeeOrganizationReferenceProjection
    branch: EmployeeOrganizationReferenceProjection
    department: EmployeeOrganizationReferenceProjection
    position: EmployeePositionReferenceProjection
    effective_from: date


class EmployeeService:
    def __init__(self, session: AsyncSession, today: date | None = None) -> None:
        self.session = session
        self.today = today or date.today()

    async def list_employees(
        self,
        tenant_id: UUID,
        filters: EmployeeListFilters | None = None,
        pagination: EmployeeListPagination | None = None,
    ) -> list[EmployeeReadProjection]:
        page = await self.list_employee_page(tenant_id, filters, pagination)
        return page.items

    async def list_employee_page(
        self,
        tenant_id: UUID,
        filters: EmployeeListFilters | None = None,
        pagination: EmployeeListPagination | None = None,
    ) -> CursorPage[EmployeeReadProjection]:
        filters = filters or EmployeeListFilters()
        pagination = pagination or EmployeeListPagination()
        statement = _employee_list_statement(
            tenant_id,
            filters,
            pagination,
            effective_on=self.today,
        )
        rows = list(await self.session.scalars(statement))
        employees = rows[: pagination.limit]
        items = await _employee_read_projections(
            self.session,
            tenant_id=tenant_id,
            employees=employees,
            effective_on=self.today,
        )
        next_cursor = None
        if len(rows) > pagination.limit:
            last_item = employees[-1]
            next_cursor = EmployeeListCursor(id=last_item.id).to_token()
        return CursorPage(items=items, next_cursor=next_cursor)

    async def get_employee_read(
        self,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> EmployeeReadProjection:
        employee = await self.get_employee(tenant_id, employee_id)
        projections = await _employee_read_projections(
            self.session,
            tenant_id=tenant_id,
            employees=[employee],
            effective_on=self.today,
        )
        return projections[0]

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
        if payload.email is not None:
            await self._ensure_work_email_available(
                tenant_id=tenant_id,
                work_email=payload.email,
            )
        employee = Employee(
            id=uuid4(),
            tenant_id=tenant_id,
            **_employee_create_values(payload),
        )
        self.session.add(employee)
        self.session.add_all(
            [
                EmployeePersonalProfile(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    employee_id=employee.id,
                ),
                EmployeeEmploymentProfile(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    employee_id=employee.id,
                ),
            ]
        )
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
        if "version" in payload.model_fields_set and payload.version != employee.version:
            raise EmployeeVersionConflictError
        values = _employee_update_values(payload)

        if "employee_number" in values and values["employee_number"] != employee.employee_number:
            await self._ensure_employee_number_available(
                tenant_id=tenant_id,
                employee_number=values["employee_number"],
                exclude_employee_id=employee_id,
            )
        if "email" in values and values["email"] is not None:
            await self._ensure_work_email_available(
                tenant_id=tenant_id,
                work_email=values["email"],
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

    async def delete_employee(self, tenant_id: UUID, employee_id: UUID) -> bool:
        employee = await self._get_employee_or_none(
            tenant_id,
            employee_id,
            include_archived=True,
        )
        if employee is None:
            raise EmployeeNotFoundError
        if employee.archived_at is not None:
            return False
        employee.archived_at = datetime.now(UTC)
        await self.session.flush()
        return True

    async def _flush_employee_write(self) -> None:
        try:
            await self.session.flush()
        except IntegrityError as exc:
            if _is_employee_number_unique_violation(exc):
                raise DuplicateEmployeeNumberError from exc
            if _is_employee_work_email_unique_violation(exc):
                raise DuplicateWorkEmailError from exc
            raise

    async def _get_employee_or_none(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        *,
        include_archived: bool = False,
    ) -> Employee | None:
        statement = (
            select(Employee)
            .where(Employee.tenant_id == tenant_id)
            .where(Employee.id == employee_id)
        )
        if not include_archived:
            statement = statement.where(Employee.archived_at.is_(None))
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
            .where(
                Employee.employee_number_normalized
                == _normalize_uniqueness_text(employee_number)
            )
        )
        if exclude_employee_id is not None:
            statement = statement.where(Employee.id != exclude_employee_id)

        if await self.session.scalar(statement) is not None:
            raise DuplicateEmployeeNumberError

    async def _ensure_work_email_available(
        self,
        tenant_id: UUID,
        work_email: str,
        exclude_employee_id: UUID | None = None,
    ) -> None:
        statement = (
            select(Employee.id)
            .where(Employee.tenant_id == tenant_id)
            .where(Employee.email_normalized == _normalize_uniqueness_text(work_email))
        )
        if exclude_employee_id is not None:
            statement = statement.where(Employee.id != exclude_employee_id)

        if await self.session.scalar(statement) is not None:
            raise DuplicateWorkEmailError


def _normalize_uniqueness_text(value: str) -> str:
    return value.strip().lower()


async def _employee_read_projections(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    employees: list[Employee],
    effective_on: date | None = None,
) -> list[EmployeeReadProjection]:
    """Batch-resolve structured current names, falling back to preserved legacy strings."""

    if not employees:
        return []
    employee_ids = tuple(employee.id for employee in employees)
    effective_on = effective_on or date.today()
    rows = (
        await session.execute(
            select(
                EmployeeAssignment.employee_id.label("employee_id"),
                EmployeeAssignment.id.label("assignment_id"),
                EmployeeAssignment.effective_from.label("effective_from"),
                LegalEntity.id.label("legal_entity_id"),
                LegalEntity.code.label("legal_entity_code"),
                LegalEntity.name.label("legal_entity_name"),
                Branch.id.label("branch_id"),
                Branch.code.label("branch_code"),
                Branch.name.label("branch_name"),
                Department.id.label("department_id"),
                Department.code.label("department_code"),
                Department.name.label("department_name"),
                Position.id.label("position_id"),
                Position.code.label("position_code"),
                Position.title.label("position_title"),
            )
            .join(
                LegalEntity,
                and_(
                    LegalEntity.tenant_id == EmployeeAssignment.tenant_id,
                    LegalEntity.id == EmployeeAssignment.legal_entity_id,
                ),
            )
            .join(
                Branch,
                and_(
                    Branch.tenant_id == EmployeeAssignment.tenant_id,
                    Branch.id == EmployeeAssignment.branch_id,
                ),
            )
            .join(
                Department,
                and_(
                    Department.tenant_id == EmployeeAssignment.tenant_id,
                    Department.id == EmployeeAssignment.department_id,
                ),
            )
            .join(
                Position,
                and_(
                    Position.tenant_id == EmployeeAssignment.tenant_id,
                    Position.id == EmployeeAssignment.position_id,
                ),
            )
            .where(
                EmployeeAssignment.tenant_id == tenant_id,
                EmployeeAssignment.employee_id.in_(employee_ids),
                EmployeeAssignment.effective_from <= effective_on,
                or_(
                    EmployeeAssignment.effective_to.is_(None),
                    EmployeeAssignment.effective_to > effective_on,
                ),
            )
        )
    ).all()
    structured = {
        row.employee_id: EmployeeCurrentAssignmentProjection(
            id=row.assignment_id,
            effective_from=row.effective_from,
            legal_entity=EmployeeOrganizationReferenceProjection(
                id=row.legal_entity_id,
                code=row.legal_entity_code,
                name=row.legal_entity_name,
            ),
            branch=EmployeeOrganizationReferenceProjection(
                id=row.branch_id,
                code=row.branch_code,
                name=row.branch_name,
            ),
            department=EmployeeOrganizationReferenceProjection(
                id=row.department_id,
                code=row.department_code,
                name=row.department_name,
            ),
            position=EmployeePositionReferenceProjection(
                id=row.position_id,
                code=row.position_code,
                title=row.position_title,
            ),
        )
        for row in rows
    }
    return [
        EmployeeReadProjection(
            id=employee.id,
            tenant_id=employee.tenant_id,
            employee_number=employee.employee_number,
            first_name=employee.first_name,
            last_name=employee.last_name,
            email=employee.email,
            department=(
                structured[employee.id].department.name
                if employee.id in structured
                else employee.department
            ),
            position=(
                structured[employee.id].position.title
                if employee.id in structured
                else employee.position
            ),
            status=employee.status,
            employment_start_date=employee.employment_start_date,
            employment_end_date=employee.employment_end_date,
            version=employee.version,
            current_assignment=structured.get(employee.id),
        )
        for employee in employees
    ]


def _employee_create_values(payload: EmployeeCreate) -> dict[str, object]:
    values = payload.model_dump()
    values["status"] = _status_value(values["status"])
    return values


def _employee_update_values(payload: EmployeeUpdate) -> dict[str, object]:
    values = {
        field_name: getattr(payload, field_name)
        for field_name in EmployeeUpdate.model_fields
        if field_name in payload.model_fields_set and field_name != "version"
    }
    if "status" in values:
        values["status"] = _status_value(values["status"])
    return values


def _status_value(status: EmployeeStatus | str | None) -> str | None:
    if isinstance(status, EmployeeStatus):
        return status.value
    return status


def _employee_list_statement(
    tenant_id: UUID,
    filters: EmployeeListFilters,
    pagination: EmployeeListPagination,
    *,
    effective_on: date | None = None,
):
    statement = (
        select(Employee)
        .where(Employee.tenant_id == tenant_id)
        .where(Employee.archived_at.is_(None))
    )

    if filters.department is not None:
        effective_on = effective_on or date.today()
        current_department_normalized = (
            select(func.lower(func.trim(Department.name)))
            .select_from(EmployeeAssignment)
            .join(
                Department,
                and_(
                    Department.tenant_id == EmployeeAssignment.tenant_id,
                    Department.id == EmployeeAssignment.department_id,
                ),
            )
            .where(
                EmployeeAssignment.tenant_id == tenant_id,
                EmployeeAssignment.employee_id == Employee.id,
                EmployeeAssignment.effective_from <= effective_on,
                or_(
                    EmployeeAssignment.effective_to.is_(None),
                    EmployeeAssignment.effective_to > effective_on,
                ),
            )
            .order_by(
                EmployeeAssignment.effective_from.desc(),
                EmployeeAssignment.id.desc(),
            )
            .limit(1)
            .correlate(Employee)
            .scalar_subquery()
        )
        statement = statement.where(
            # Department names are non-null on a valid assignment, so COALESCE reaches the
            # legacy projection only when no assignment is effective on this date.
            func.coalesce(
                current_department_normalized,
                Employee.department_normalized,
            )
            == filters.department.lower()
        )
    if filters.status is not None:
        statement = statement.where(Employee.status == _status_value(filters.status))
    structured_filter_values = {
        EmployeeAssignment.legal_entity_id: filters.legal_entity_id,
        EmployeeAssignment.branch_id: filters.branch_id,
        EmployeeAssignment.department_id: filters.department_id,
        EmployeeAssignment.position_id: filters.position_id,
    }
    if any(value is not None for value in structured_filter_values.values()):
        effective_on = effective_on or date.today()
        assignment_predicates = [
            EmployeeAssignment.tenant_id == tenant_id,
            EmployeeAssignment.employee_id == Employee.id,
            EmployeeAssignment.effective_from <= effective_on,
            or_(
                EmployeeAssignment.effective_to.is_(None),
                EmployeeAssignment.effective_to > effective_on,
            ),
        ]
        assignment_predicates.extend(
            column == value
            for column, value in structured_filter_values.items()
            if value is not None
        )
        statement = statement.where(
            exists(select(EmployeeAssignment.id).where(*assignment_predicates))
        )
    if filters.q is not None:
        search_pattern = _escaped_contains_pattern(filters.q.lower())
        statement = statement.where(
            or_(
                Employee.employee_number.ilike(search_pattern, escape="\\"),
                Employee.email.ilike(search_pattern, escape="\\"),
                Employee.full_name_normalized.like(search_pattern, escape="\\"),
            )
        )

    cursor = pagination.cursor
    if cursor is not None:
        statement = statement.where(Employee.id > cursor.id)
    else:
        statement = statement.offset(pagination.offset)

    return statement.order_by(Employee.id.asc()).limit(pagination.limit + 1)


def _escaped_contains_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _is_employee_number_unique_violation(exc: IntegrityError) -> bool:
    if constraint_name_from_error(exc) in {
        EMPLOYEE_NUMBER_UNIQUE_CONSTRAINT,
        EMPLOYEE_NUMBER_NORMALIZED_UNIQUE_CONSTRAINT,
    }:
        return True
    message = str(exc.orig)
    return any(
        signature in message
        for signature in (
            _SQLITE_EMPLOYEE_NUMBER_UNIQUE_SIGNATURE,
            _SQLITE_EMPLOYEE_NUMBER_NORMALIZED_UNIQUE_SIGNATURE,
        )
    )


def _is_employee_work_email_unique_violation(exc: IntegrityError) -> bool:
    if constraint_name_from_error(exc) == EMPLOYEE_WORK_EMAIL_NORMALIZED_UNIQUE_CONSTRAINT:
        return True
    return _SQLITE_EMPLOYEE_WORK_EMAIL_NORMALIZED_UNIQUE_SIGNATURE in str(exc.orig)


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
