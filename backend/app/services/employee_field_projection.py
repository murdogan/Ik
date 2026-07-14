"""Explicit employee response constructors backed by the central field policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import cast
from uuid import UUID

from app.models.employee import Employee
from app.models.employee_profile import EmployeeEmploymentProfile, EmployeePersonalProfile
from app.schemas.employee_account_link import (
    OwnCurrentAssignmentRead,
    OwnEmployeeEmploymentProfileRead,
    OwnEmployeeOrganizationRead,
    OwnEmployeePersonalProfileRead,
    OwnEmployeeProfileCoreRead,
    OwnEmployeeProfileRead,
    OwnEmployeeProfileStateRead,
    OwnManagerReferenceRead,
    OwnMaskedFieldRead,
    OwnOrganizationReferenceRead,
    OwnPositionReferenceRead,
)
from app.schemas.employee_assignment import (
    ManagerTeamAssignmentRead,
    ManagerTeamCurrentAssignmentRead,
    ManagerTeamEmployeeRead,
    ManagerTeamEmploymentRead,
    ManagerTeamManagerRead,
    ManagerTeamMemberProfileRead,
    ManagerTeamOrganizationRead,
    ManagerTeamOrganizationReferenceRead,
    ManagerTeamPositionReferenceRead,
)
from app.schemas.employee_profile import (
    EmployeeEmploymentProfileRead,
    EmployeePersonalProfileRead,
    EmployeeProfileCoreRead,
)
from app.services.employee_field_policy import EmployeeProjectionScope, project_field
from app.services.employee_projection_contract import enforce_response_contract


@dataclass(frozen=True, slots=True)
class WorkOrganizationSource:
    legal_entity_code: str
    legal_entity_name: str
    branch_code: str
    branch_name: str
    department_code: str
    department_name: str
    position_code: str
    position_title: str
    manager_full_name: str | None
    effective_from: date


def project_hr_core(employee: Employee) -> EmployeeProfileCoreRead:
    scope = EmployeeProjectionScope.HR_TENANT
    return EmployeeProfileCoreRead(
        id=project_field(scope, "employee.id", employee.id),
        employee_number=project_field(scope, "employee.employee_number", employee.employee_number),
        first_name=project_field(scope, "employee.first_name", employee.first_name),
        last_name=project_field(scope, "employee.last_name", employee.last_name),
        email=project_field(scope, "employee.email", employee.email),
        status=project_field(scope, "employee.status", employee.status),
        employee_version=project_field(scope, "employee.version", employee.version),
        archived_at=project_field(scope, "employee.archived_at", employee.archived_at),
    )


def project_hr_personal(profile: EmployeePersonalProfile) -> EmployeePersonalProfileRead:
    scope = EmployeeProjectionScope.HR_TENANT
    return EmployeePersonalProfileRead(
        preferred_name=project_field(scope, "personal.preferred_name", profile.preferred_name),
        birth_date=project_field(scope, "personal.birth_date", profile.birth_date),
        phone=project_field(scope, "personal.phone", profile.phone),
        version=project_field(scope, "personal.version", profile.version),
    )


def project_hr_employment(
    employee: Employee,
    profile: EmployeeEmploymentProfile,
) -> EmployeeEmploymentProfileRead:
    scope = EmployeeProjectionScope.HR_TENANT
    return EmployeeEmploymentProfileRead(
        employment_start_date=project_field(
            scope, "employee.employment_start_date", employee.employment_start_date
        ),
        employment_end_date=project_field(
            scope, "employee.employment_end_date", employee.employment_end_date
        ),
        termination_reason=project_field(
            scope, "employee.termination_reason", employee.termination_reason
        ),
        contract_type=project_field(scope, "employment.contract_type", profile.contract_type),
        work_type=project_field(scope, "employment.work_type", profile.work_type),
        version=project_field(scope, "employment.version", profile.version),
    )


def project_manager_employee(
    *,
    employee_id: UUID,
    employee_number: str,
    first_name: str,
    last_name: str,
    preferred_name: str | None,
    email: str | None,
    status: str,
) -> ManagerTeamEmployeeRead:
    scope = EmployeeProjectionScope.MANAGER_TEAM
    return ManagerTeamEmployeeRead(
        id=project_field(scope, "employee.id", employee_id),
        employee_number=project_field(scope, "employee.employee_number", employee_number),
        first_name=project_field(scope, "employee.first_name", first_name),
        last_name=project_field(scope, "employee.last_name", last_name),
        preferred_name=project_field(scope, "personal.preferred_name", preferred_name),
        email=project_field(scope, "employee.email", email),
        status=project_field(scope, "employee.status", status),
    )


def project_manager_assignment(source: WorkOrganizationSource) -> ManagerTeamAssignmentRead:
    scope = EmployeeProjectionScope.MANAGER_TEAM
    return ManagerTeamAssignmentRead(
        legal_entity=ManagerTeamOrganizationReferenceRead(
            code=project_field(scope, "organization.legal_entity.code", source.legal_entity_code),
            name=project_field(scope, "organization.legal_entity.name", source.legal_entity_name),
        ),
        branch=ManagerTeamOrganizationReferenceRead(
            code=project_field(scope, "organization.branch.code", source.branch_code),
            name=project_field(scope, "organization.branch.name", source.branch_name),
        ),
        department=ManagerTeamOrganizationReferenceRead(
            code=project_field(scope, "organization.department.code", source.department_code),
            name=project_field(scope, "organization.department.name", source.department_name),
        ),
        position=ManagerTeamPositionReferenceRead(
            code=project_field(scope, "organization.position.code", source.position_code),
            title=project_field(scope, "organization.position.title", source.position_title),
        ),
        effective_from=project_field(scope, "assignment.effective_from", source.effective_from),
    )


def project_manager_profile(
    *,
    core: ManagerTeamEmployeeRead,
    employment_start_date: date,
    contract_type: str | None,
    work_type: str | None,
    organization: WorkOrganizationSource,
) -> ManagerTeamMemberProfileRead:
    scope = EmployeeProjectionScope.MANAGER_TEAM
    assignment = project_manager_assignment(organization)
    result = ManagerTeamMemberProfileRead(
        core=core,
        employment=ManagerTeamEmploymentRead(
            employment_start_date=project_field(
                scope, "employee.employment_start_date", employment_start_date
            ),
            contract_type=project_field(scope, "employment.contract_type", contract_type),
            work_type=project_field(scope, "employment.work_type", work_type),
        ),
        organization=ManagerTeamOrganizationRead(
            current_assignment=ManagerTeamCurrentAssignmentRead(
                legal_entity=assignment.legal_entity,
                branch=assignment.branch,
                department=assignment.department,
                position=assignment.position,
                effective_from=assignment.effective_from,
                manager=(
                    ManagerTeamManagerRead(
                        full_name=project_field(
                            scope,
                            "organization.manager.full_name",
                            organization.manager_full_name,
                        )
                    )
                    if organization.manager_full_name is not None
                    else None
                ),
            )
        ),
    )
    enforce_response_contract(result)
    return result


def project_own_profile(
    *,
    authenticated_membership_id: UUID,
    employee: Employee,
    personal: EmployeePersonalProfile,
    employment: EmployeeEmploymentProfile,
    organization: WorkOrganizationSource | None,
) -> OwnEmployeeProfileStateRead:
    scope = EmployeeProjectionScope.EMPLOYEE_OWN
    current_assignment = None
    if organization is not None:
        current_assignment = OwnCurrentAssignmentRead(
            legal_entity=OwnOrganizationReferenceRead(
                code=project_field(
                    scope, "organization.legal_entity.code", organization.legal_entity_code
                ),
                name=project_field(
                    scope, "organization.legal_entity.name", organization.legal_entity_name
                ),
            ),
            branch=OwnOrganizationReferenceRead(
                code=project_field(scope, "organization.branch.code", organization.branch_code),
                name=project_field(scope, "organization.branch.name", organization.branch_name),
            ),
            department=OwnOrganizationReferenceRead(
                code=project_field(
                    scope, "organization.department.code", organization.department_code
                ),
                name=project_field(
                    scope, "organization.department.name", organization.department_name
                ),
            ),
            position=OwnPositionReferenceRead(
                code=project_field(scope, "organization.position.code", organization.position_code),
                title=project_field(
                    scope, "organization.position.title", organization.position_title
                ),
            ),
            manager=(
                OwnManagerReferenceRead(
                    full_name=project_field(
                        scope,
                        "organization.manager.full_name",
                        organization.manager_full_name,
                    )
                )
                if organization.manager_full_name is not None
                else None
            ),
        )
    result = OwnEmployeeProfileStateRead(
        availability="available",
        membership_id=project_field(
            scope,
            "projection.own_session_membership_id",
            authenticated_membership_id,
        ),
        employee_id=project_field(scope, "employee.id", employee.id),
        profile=OwnEmployeeProfileRead(
            core=OwnEmployeeProfileCoreRead(
                id=project_field(scope, "employee.id", employee.id),
                employee_number=project_field(
                    scope, "employee.employee_number", employee.employee_number
                ),
                first_name=project_field(scope, "employee.first_name", employee.first_name),
                last_name=project_field(scope, "employee.last_name", employee.last_name),
                email=project_field(scope, "employee.email", employee.email),
                status=project_field(scope, "employee.status", employee.status),
            ),
            personal=OwnEmployeePersonalProfileRead(
                preferred_name=project_field(
                    scope, "personal.preferred_name", personal.preferred_name
                ),
                birth_date=cast(
                    OwnMaskedFieldRead,
                    project_field(scope, "personal.birth_date", personal.birth_date),
                ),
                phone=cast(
                    OwnMaskedFieldRead,
                    project_field(scope, "personal.phone", personal.phone),
                ),
            ),
            employment=OwnEmployeeEmploymentProfileRead(
                employment_start_date=project_field(
                    scope,
                    "employee.employment_start_date",
                    employee.employment_start_date,
                ),
                contract_type=project_field(
                    scope, "employment.contract_type", employment.contract_type
                ),
                work_type=project_field(scope, "employment.work_type", employment.work_type),
            ),
            organization=OwnEmployeeOrganizationRead(current_assignment=current_assignment),
        ),
    )
    enforce_response_contract(result)
    return result


def unavailable_own_profile() -> OwnEmployeeProfileStateRead:
    result = OwnEmployeeProfileStateRead(
        availability="unavailable",
        membership_id=None,
        employee_id=None,
        profile=None,
    )
    enforce_response_contract(result)
    return result


__all__ = [
    "WorkOrganizationSource",
    "project_hr_core",
    "project_hr_employment",
    "project_hr_personal",
    "project_manager_assignment",
    "project_manager_employee",
    "project_manager_profile",
    "project_own_profile",
    "unavailable_own_profile",
]
