"""Focused Employee 360 reads and same-session profile mutations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.employee_profile import (
    EmployeeEmploymentProfile,
    EmployeePersonalProfile,
)
from app.schemas.employee import EmployeeUpdate
from app.schemas.employee_profile import (
    EMPLOYEE_PROFILE_HISTORY_LIMIT,
    EmployeeEmploymentProfileMutationRead,
    EmployeeEmploymentProfileRead,
    EmployeeEmploymentProfileUpdate,
    EmployeePersonalProfileMutationRead,
    EmployeePersonalProfileRead,
    EmployeePersonalProfileUpdate,
    EmployeeProfileCoreRead,
    EmployeeProfileOrganizationRead,
    EmployeeProfileRead,
)
from app.services.employee_assignment_service import (
    employee_assignment_profile_projection,
)
from app.services.employee_field_projection import (
    project_hr_core,
    project_hr_employment,
    project_hr_personal,
)
from app.services.employee_projection_contract import (
    enforce_hr_profile_contract,
    enforce_response_contract,
)
from app.services.employee_service import (
    EmployeeNotFoundError,
    EmployeeService,
    EmployeeVersionConflictError,
)

_PERSONAL_CORE_FIELDS = ("first_name", "last_name", "email")
_PERSONAL_SECTION_FIELDS = ("preferred_name", "birth_date", "phone")
_EMPLOYMENT_CORE_FIELDS = ("employment_start_date",)
_EMPLOYMENT_SECTION_FIELDS = ("contract_type", "work_type")


class EmployeeProfileNotFoundError(EmployeeNotFoundError):
    pass


class EmployeeProfileVersionConflictError(EmployeeVersionConflictError):
    pass


@dataclass(frozen=True, slots=True)
class PersonalProfileMutation:
    response: EmployeePersonalProfileMutationRead
    changed_fields: tuple[str, ...]
    before_values: dict[str, object]
    after_values: dict[str, object]


@dataclass(frozen=True, slots=True)
class EmploymentProfileMutation:
    response: EmployeeEmploymentProfileMutationRead
    changed_fields: tuple[str, ...]
    before_values: dict[str, object]
    after_values: dict[str, object]


class EmployeeProfileService:
    def __init__(self, session: AsyncSession, today: date | None = None) -> None:
        self.session = session
        self.today = today or date.today()

    async def get_employee_profile(
        self,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> EmployeeProfileRead:
        employee, personal, employment = await self._get_profile_row(
            tenant_id,
            employee_id,
        )
        organization = await employee_assignment_profile_projection(
            self.session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            effective_on=self.today,
            history_limit=EMPLOYEE_PROFILE_HISTORY_LIMIT,
        )
        return enforce_hr_profile_contract(
            EmployeeProfileRead(
                core=_core_read(employee),
                personal=_personal_read(personal),
                employment=_employment_read(employee, employment),
                organization=EmployeeProfileOrganizationRead(
                    current_assignment=organization.current_assignment,
                    history=organization.history,
                    history_limit=organization.history_limit,
                    history_truncated=organization.history_truncated,
                ),
            )
        )

    async def update_personal_profile(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeePersonalProfileUpdate,
    ) -> PersonalProfileMutation:
        employee, personal, _employment = await self._get_profile_row(
            tenant_id,
            employee_id,
        )
        if personal.version != payload.expected_version:
            raise EmployeeProfileVersionConflictError
        candidate_fields = tuple(
            field_name
            for field_name in (*_PERSONAL_CORE_FIELDS, *_PERSONAL_SECTION_FIELDS)
            if field_name in payload.model_fields_set
        )
        before_values = {
            field_name: _personal_field_value(employee, personal, field_name)
            for field_name in candidate_fields
        }

        core_values = {
            field_name: getattr(payload, field_name)
            for field_name in _PERSONAL_CORE_FIELDS
            if field_name in payload.model_fields_set
        }
        if core_values:
            if payload.expected_employee_version != employee.version:
                raise EmployeeVersionConflictError
            employee = await EmployeeService(
                self.session,
                today=self.today,
            ).update_employee(
                tenant_id,
                employee_id,
                EmployeeUpdate(
                    version=payload.expected_employee_version,
                    **core_values,
                ),
            )

        for field_name in _PERSONAL_SECTION_FIELDS:
            if field_name in payload.model_fields_set:
                setattr(personal, field_name, getattr(payload, field_name))
        if any(
            before_values[field_name] != _personal_field_value(employee, personal, field_name)
            for field_name in candidate_fields
        ):
            # The section token guards the whole personal command, including compatibility-owned
            # name/email changes. Setting it explicitly also makes a core-only command issue the
            # version-predicated profile UPDATE required by SQLAlchemy's optimistic lock.
            personal.version += 1
        await self.session.flush()
        await self.session.refresh(personal)

        after_values = {
            field_name: _personal_field_value(employee, personal, field_name)
            for field_name in candidate_fields
        }
        changed_fields = tuple(
            sorted(
                field_name
                for field_name in candidate_fields
                if before_values[field_name] != after_values[field_name]
            )
        )
        response = EmployeePersonalProfileMutationRead(
            core=_core_read(employee),
            personal=_personal_read(personal),
        )
        enforce_response_contract(response)
        return PersonalProfileMutation(
            response=response,
            changed_fields=changed_fields,
            before_values={field_name: before_values[field_name] for field_name in changed_fields},
            after_values={field_name: after_values[field_name] for field_name in changed_fields},
        )

    async def update_employment_profile(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeeEmploymentProfileUpdate,
    ) -> EmploymentProfileMutation:
        employee, _personal, employment = await self._get_profile_row(
            tenant_id,
            employee_id,
        )
        if employment.version != payload.expected_version:
            raise EmployeeProfileVersionConflictError
        candidate_fields = tuple(
            field_name
            for field_name in (*_EMPLOYMENT_CORE_FIELDS, *_EMPLOYMENT_SECTION_FIELDS)
            if field_name in payload.model_fields_set
        )
        before_values = {
            field_name: _employment_field_value(employee, employment, field_name)
            for field_name in candidate_fields
        }

        if "employment_start_date" in payload.model_fields_set:
            if payload.expected_employee_version != employee.version:
                raise EmployeeVersionConflictError
            employee = await EmployeeService(
                self.session,
                today=self.today,
            ).update_employee(
                tenant_id,
                employee_id,
                EmployeeUpdate(
                    version=payload.expected_employee_version,
                    employment_start_date=payload.employment_start_date,
                ),
            )

        for field_name in _EMPLOYMENT_SECTION_FIELDS:
            if field_name in payload.model_fields_set:
                value = getattr(payload, field_name)
                setattr(
                    employment,
                    field_name,
                    value.value if value is not None else None,
                )
        if any(
            before_values[field_name] != _employment_field_value(employee, employment, field_name)
            for field_name in candidate_fields
        ):
            # Employment start date remains core-owned, but a successful start-date-only command
            # must still consume the employment section token exactly once.
            employment.version += 1
        await self.session.flush()
        await self.session.refresh(employment)

        after_values = {
            field_name: _employment_field_value(employee, employment, field_name)
            for field_name in candidate_fields
        }
        changed_fields = tuple(
            sorted(
                field_name
                for field_name in candidate_fields
                if before_values[field_name] != after_values[field_name]
            )
        )
        response = EmployeeEmploymentProfileMutationRead(
            core=_core_read(employee),
            employment=_employment_read(employee, employment),
        )
        enforce_response_contract(response)
        return EmploymentProfileMutation(
            response=response,
            changed_fields=changed_fields,
            before_values={field_name: before_values[field_name] for field_name in changed_fields},
            after_values={field_name: after_values[field_name] for field_name in changed_fields},
        )

    async def _get_profile_row(
        self,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> tuple[Employee, EmployeePersonalProfile, EmployeeEmploymentProfile]:
        statement = (
            select(
                Employee,
                EmployeePersonalProfile,
                EmployeeEmploymentProfile,
            )
            .join(
                EmployeePersonalProfile,
                and_(
                    EmployeePersonalProfile.tenant_id == Employee.tenant_id,
                    EmployeePersonalProfile.employee_id == Employee.id,
                ),
            )
            .join(
                EmployeeEmploymentProfile,
                and_(
                    EmployeeEmploymentProfile.tenant_id == Employee.tenant_id,
                    EmployeeEmploymentProfile.employee_id == Employee.id,
                ),
            )
            .where(
                Employee.tenant_id == tenant_id,
                Employee.id == employee_id,
                Employee.archived_at.is_(None),
            )
        )
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            raise EmployeeProfileNotFoundError
        employee, personal, employment = row
        return employee, personal, employment


def _core_read(employee: Employee) -> EmployeeProfileCoreRead:
    return project_hr_core(employee)


def _personal_read(profile: EmployeePersonalProfile) -> EmployeePersonalProfileRead:
    return project_hr_personal(profile)


def _employment_read(
    employee: Employee,
    profile: EmployeeEmploymentProfile,
) -> EmployeeEmploymentProfileRead:
    return project_hr_employment(employee, profile)


def _personal_field_value(
    employee: Employee,
    profile: EmployeePersonalProfile,
    field_name: str,
) -> object:
    if field_name in _PERSONAL_CORE_FIELDS:
        return getattr(employee, field_name)
    return getattr(profile, field_name)


def _employment_field_value(
    employee: Employee,
    profile: EmployeeEmploymentProfile,
    field_name: str,
) -> object:
    if field_name in _EMPLOYMENT_CORE_FIELDS:
        return getattr(employee, field_name)
    return getattr(profile, field_name)


__all__ = [
    "EmployeeProfileNotFoundError",
    "EmployeeProfileService",
    "EmployeeProfileVersionConflictError",
    "EmploymentProfileMutation",
    "PersonalProfileMutation",
]
