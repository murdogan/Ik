from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, exists, func, or_, select, update
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
from app.models.auth import RefreshSessionFamily, UserActivationToken
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_account_link import EmployeeAccountLink
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_profile import (
    EmployeeEmploymentProfile,
    EmployeePersonalProfile,
)
from app.models.employee_profile_change_request import (
    EmployeeProfileChangeRequest,
    EmployeeProfileChangeRequestStatus,
)
from app.models.identity import MembershipStatus, TenantMembership
from app.models.organization import Branch, LegalEntity
from app.models.position import Position
from app.models.user import User, UserStatus
from app.platform.db import constraint_name_from_error
from app.platform.errors.application import ApplicationError
from app.platform.pagination import CursorPage
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeLifecycleTransition,
    EmployeeListCursor,
    EmployeeListFilters,
    EmployeeListPagination,
    EmployeeUpdate,
)
from app.services.identity_projection_service import sync_existing_membership_projection

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


class EmployeeLifecycleConflictError(ApplicationError):
    pass


class EmployeeOpenProcessConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "Resolve the submitted employee profile-change request before termination or archive"
        )


@dataclass(frozen=True, slots=True)
class EmployeeLifecycleMutation:
    employee: Employee
    changed_fields: tuple[str, ...]
    before_status: str
    assignment_closed: bool = False
    membership_deactivated: bool = False
    sessions_revoked: int = 0
    membership_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class EmployeeArchiveMutation:
    employee: Employee
    archived: bool


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

    async def transition_employee_lifecycle(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeeLifecycleTransition,
    ) -> EmployeeLifecycleMutation:
        target_status = payload.target_status.value
        initially_open_assignment = None
        if payload.target_status == EmployeeStatus.TERMINATED:
            # Assignment changes serialize on the open row before they lock the employee.
            initially_open_assignment = await self._lock_open_assignment(
                tenant_id,
                employee_id,
            )

        # P4E submission serializes on the personal profile. Taking the same lock before the
        # employee prevents a request from being submitted between the blocker check and commit.
        await self._lock_profile_section(
            EmployeePersonalProfile,
            tenant_id,
            employee_id,
        )
        employee = await self._get_employee_or_none(
            tenant_id,
            employee_id,
            include_archived=True,
            lock=True,
        )
        if employee is None:
            raise EmployeeNotFoundError
        if employee.archived_at is not None:
            raise EmployeeLifecycleConflictError(
                "Archived employees are read-only"
            )

        before_status = employee.status
        if before_status == target_status:
            if target_status == EmployeeStatus.TERMINATED.value:
                if await self._has_submitted_profile_change_request(tenant_id, employee_id):
                    raise EmployeeOpenProcessConflictError
                expected_reason = (
                    payload.termination_reason.value
                    if payload.termination_reason is not None
                    else None
                )
                if (
                    employee.employment_end_date != payload.effective_date
                    or employee.termination_reason != expected_reason
                    or initially_open_assignment is not None
                ):
                    raise EmployeeLifecycleConflictError(
                        "The employee is already terminated with different effective data"
                    )
            return EmployeeLifecycleMutation(
                employee=employee,
                changed_fields=(),
                before_status=before_status,
            )

        if employee.version != payload.expected_version:
            raise EmployeeVersionConflictError
        if before_status == EmployeeStatus.TERMINATED.value:
            raise EmployeeLifecycleConflictError(
                "Termination is terminal; reactivation is not available"
            )
        allowed_targets = {
            EmployeeStatus.ACTIVE.value: {
                EmployeeStatus.ON_LEAVE.value,
                EmployeeStatus.TERMINATED.value,
            },
            EmployeeStatus.ON_LEAVE.value: {
                EmployeeStatus.ACTIVE.value,
                EmployeeStatus.TERMINATED.value,
            },
        }
        if target_status not in allowed_targets.get(before_status, set()):
            raise EmployeeLifecycleConflictError(
                f"The lifecycle transition from {before_status} to {target_status} is not allowed"
            )

        before_values = {
            "status": employee.status,
            "employment_end_date": employee.employment_end_date,
            "termination_reason": employee.termination_reason,
        }
        assignment_closed = False
        membership_deactivated = False
        sessions_revoked = 0
        membership_id = None

        if target_status == EmployeeStatus.TERMINATED.value:
            assert payload.effective_date is not None
            assert payload.termination_reason is not None
            _validate_date_order(employee.employment_start_date, payload.effective_date)
            if await self._has_submitted_profile_change_request(tenant_id, employee_id):
                raise EmployeeOpenProcessConflictError

            # A fresh query catches an assignment created while this command waited for the
            # employee lock; the unique open-row index keeps the result bounded to one row.
            open_assignment = await self._lock_open_assignment(tenant_id, employee_id)
            if open_assignment is None:
                open_assignment = initially_open_assignment
            if open_assignment is not None:
                if payload.effective_date < open_assignment.effective_from:
                    raise EmployeeLifecycleConflictError(
                        "Termination cannot precede the open assignment's effective date"
                    )
                open_assignment.effective_to = payload.effective_date
                assignment_closed = True

            employee.status = target_status
            employee.employment_end_date = payload.effective_date
            employee.termination_reason = payload.termination_reason.value
            (
                membership_id,
                sessions_revoked,
                membership_deactivated,
            ) = await self._deactivate_linked_membership(tenant_id, employee_id)
        else:
            employee.status = target_status
            employee.employment_end_date = None
            employee.termination_reason = None

        await self.session.flush()
        await self.session.refresh(employee)
        changed_fields = tuple(
            sorted(
                field_name
                for field_name, before_value in before_values.items()
                if getattr(employee, field_name) != before_value
            )
        )
        return EmployeeLifecycleMutation(
            employee=employee,
            changed_fields=changed_fields,
            before_status=before_status,
            assignment_closed=assignment_closed,
            membership_deactivated=membership_deactivated,
            sessions_revoked=sessions_revoked,
            membership_id=membership_id,
        )

    async def archive_employee(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        *,
        expected_version: int | None = None,
    ) -> EmployeeArchiveMutation:
        # Archive makes the entire Employee 360 record read-only, so it serializes with both
        # profile section writers before locking the employee row.
        await self._lock_profile_section(
            EmployeePersonalProfile,
            tenant_id,
            employee_id,
        )
        await self._lock_profile_section(
            EmployeeEmploymentProfile,
            tenant_id,
            employee_id,
        )
        employee = await self._get_employee_or_none(
            tenant_id,
            employee_id,
            include_archived=True,
            lock=True,
        )
        if employee is None:
            raise EmployeeNotFoundError
        if await self._has_submitted_profile_change_request(tenant_id, employee_id):
            raise EmployeeOpenProcessConflictError
        if employee.status != EmployeeStatus.TERMINATED.value:
            raise EmployeeLifecycleConflictError(
                "Only terminated employees can be archived"
            )
        if employee.archived_at is not None:
            return EmployeeArchiveMutation(employee=employee, archived=False)
        if expected_version is not None and employee.version != expected_version:
            raise EmployeeVersionConflictError
        employee.archived_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(employee)
        return EmployeeArchiveMutation(employee=employee, archived=True)

    async def delete_employee(self, tenant_id: UUID, employee_id: UUID) -> bool:
        mutation = await self.archive_employee(tenant_id, employee_id)
        return mutation.archived

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
        lock: bool = False,
    ) -> Employee | None:
        statement = (
            select(Employee)
            .where(Employee.tenant_id == tenant_id)
            .where(Employee.id == employee_id)
        )
        if not include_archived:
            statement = statement.where(Employee.archived_at.is_(None))
        if lock:
            statement = statement.with_for_update(of=Employee)
        return await self.session.scalar(statement)

    async def _lock_profile_section(
        self,
        model: type[EmployeePersonalProfile] | type[EmployeeEmploymentProfile],
        tenant_id: UUID,
        employee_id: UUID,
    ) -> None:
        profile_id = await self.session.scalar(
            select(model.id)
            .where(
                model.tenant_id == tenant_id,
                model.employee_id == employee_id,
            )
            .with_for_update(of=model)
        )
        if profile_id is None:
            employee_exists = await self.session.scalar(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id,
                    Employee.id == employee_id,
                )
            )
            if employee_exists is None:
                raise EmployeeNotFoundError
            raise RuntimeError("Employee profile persistence is incomplete")

    async def _lock_open_assignment(
        self,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> EmployeeAssignment | None:
        return await self.session.scalar(
            select(EmployeeAssignment)
            .where(
                EmployeeAssignment.tenant_id == tenant_id,
                EmployeeAssignment.employee_id == employee_id,
                EmployeeAssignment.effective_to.is_(None),
            )
            .with_for_update(of=EmployeeAssignment)
        )

    async def _has_submitted_profile_change_request(
        self,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> bool:
        return (
            await self.session.scalar(
                select(EmployeeProfileChangeRequest.id)
                .where(
                    EmployeeProfileChangeRequest.tenant_id == tenant_id,
                    EmployeeProfileChangeRequest.employee_id == employee_id,
                    EmployeeProfileChangeRequest.status
                    == EmployeeProfileChangeRequestStatus.SUBMITTED.value,
                )
                .limit(1)
            )
            is not None
        )

    async def _deactivate_linked_membership(
        self,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> tuple[UUID | None, int, bool]:
        row = (
            await self.session.execute(
                select(EmployeeAccountLink, TenantMembership, User)
                .join(
                    TenantMembership,
                    and_(
                        TenantMembership.tenant_id == EmployeeAccountLink.tenant_id,
                        TenantMembership.id == EmployeeAccountLink.membership_id,
                    ),
                )
                .join(
                    User,
                    and_(
                        User.tenant_id == TenantMembership.tenant_id,
                        User.id == TenantMembership.legacy_user_id,
                    ),
                )
                .where(
                    EmployeeAccountLink.tenant_id == tenant_id,
                    EmployeeAccountLink.employee_id == employee_id,
                )
                .with_for_update(of=(EmployeeAccountLink, User))
            )
        ).one_or_none()
        if row is None:
            return None, 0, False

        _link, membership, user = row
        now = datetime.now(UTC)
        deactivated = (
            membership.status != MembershipStatus.DISABLED.value
            or user.status != UserStatus.DISABLED.value
        )
        if user.status != UserStatus.DISABLED.value:
            user.status = UserStatus.DISABLED.value
            user.updated_at = now
        await self.session.flush()
        # PostgreSQL uses the existing narrow tenant projection function; SQLite uses the same
        # compatibility projection in-process. Neither path changes the global identity.
        await sync_existing_membership_projection(self.session, user)

        await self.session.execute(
            update(UserActivationToken)
            .where(
                UserActivationToken.tenant_id == tenant_id,
                UserActivationToken.user_id == user.id,
                UserActivationToken.consumed_at.is_(None),
                UserActivationToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        revoked = await self.session.execute(
            update(RefreshSessionFamily)
            .where(
                RefreshSessionFamily.tenant_id == tenant_id,
                RefreshSessionFamily.membership_id == membership.id,
                RefreshSessionFamily.revoked_at.is_(None),
                RefreshSessionFamily.expires_at > now,
            )
            .values(revoked_at=now)
        )
        return membership.id, max(revoked.rowcount or 0, 0), deactivated

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
