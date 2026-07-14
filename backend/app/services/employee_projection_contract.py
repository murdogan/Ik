"""Exact response and ORM coverage for employee field projections."""

from __future__ import annotations

from types import MappingProxyType
from typing import get_args, get_origin

from pydantic import BaseModel

from app.models.employee import Employee
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_profile import EmployeeEmploymentProfile, EmployeePersonalProfile
from app.schemas.employee import EmployeeRead
from app.schemas.employee_account_link import OwnEmployeeProfileStateRead
from app.schemas.employee_assignment import ManagerTeamMemberProfileRead, TeamMemberRead
from app.schemas.employee_profile import (
    EmployeeEmploymentProfileMutationRead,
    EmployeePersonalProfileMutationRead,
    EmployeeProfileRead,
)
from app.services.employee_field_policy import (
    EMPLOYEE_FIELD_POLICIES,
    EXCLUDED,
    EmployeeFieldExcludedError,
    EmployeeProjectionScope,
    UnclassifiedEmployeeFieldError,
    field_policy,
)


def _hr_assignment_fields(prefix: str) -> dict[str, str]:
    return {
        f"{prefix}.id": "assignment.id",
        f"{prefix}.employee.id": "employee.id",
        f"{prefix}.employee.employee_number": "employee.employee_number",
        f"{prefix}.employee.first_name": "employee.first_name",
        f"{prefix}.employee.last_name": "employee.last_name",
        f"{prefix}.employee.email": "employee.email",
        f"{prefix}.employee.status": "employee.status",
        f"{prefix}.legal_entity.id": "organization.legal_entity.id",
        f"{prefix}.legal_entity.code": "organization.legal_entity.code",
        f"{prefix}.legal_entity.name": "organization.legal_entity.name",
        f"{prefix}.legal_entity.status": "organization.legal_entity.status",
        f"{prefix}.branch.id": "organization.branch.id",
        f"{prefix}.branch.code": "organization.branch.code",
        f"{prefix}.branch.name": "organization.branch.name",
        f"{prefix}.branch.status": "organization.branch.status",
        f"{prefix}.department.id": "organization.department.id",
        f"{prefix}.department.code": "organization.department.code",
        f"{prefix}.department.name": "organization.department.name",
        f"{prefix}.department.status": "organization.department.status",
        f"{prefix}.position.id": "organization.position.id",
        f"{prefix}.position.code": "organization.position.code",
        f"{prefix}.position.title": "organization.position.title",
        f"{prefix}.position.status": "organization.position.status",
        f"{prefix}.manager.id": "organization.manager.id",
        f"{prefix}.manager.full_name": "organization.manager.full_name",
        f"{prefix}.manager.email": "organization.manager.email",
        f"{prefix}.manager.status": "organization.manager.status",
        f"{prefix}.effective_from": "assignment.effective_from",
        f"{prefix}.effective_to": "assignment.effective_to",
        f"{prefix}.supersedes_assignment_id": "assignment.supersedes_assignment_id",
        f"{prefix}.change_reason": "assignment.change_reason",
        f"{prefix}.is_current": "assignment.is_current",
        f"{prefix}.created_at": "assignment.created_at",
        f"{prefix}.updated_at": "assignment.updated_at",
    }


_HR_PROFILE_FIELDS = {
    "core.id": "employee.id",
    "core.employee_number": "employee.employee_number",
    "core.first_name": "employee.first_name",
    "core.last_name": "employee.last_name",
    "core.email": "employee.email",
    "core.status": "employee.status",
    "core.employee_version": "employee.version",
    "personal.preferred_name": "personal.preferred_name",
    "personal.birth_date": "personal.birth_date",
    "personal.phone": "personal.phone",
    "personal.version": "personal.version",
    "employment.employment_start_date": "employee.employment_start_date",
    "employment.contract_type": "employment.contract_type",
    "employment.work_type": "employment.work_type",
    "employment.version": "employment.version",
    "organization.history_limit": "organization.history_limit",
    "organization.history_truncated": "organization.history_truncated",
    **_hr_assignment_fields("organization.current_assignment"),
    **_hr_assignment_fields("organization.history"),
}

_MANAGER_EMPLOYEE_FIELDS = {
    "id": "employee.id",
    "employee_number": "employee.employee_number",
    "first_name": "employee.first_name",
    "last_name": "employee.last_name",
    "preferred_name": "personal.preferred_name",
    "email": "employee.email",
    "status": "employee.status",
}
_MANAGER_ASSIGNMENT_FIELDS = {
    "legal_entity.code": "organization.legal_entity.code",
    "legal_entity.name": "organization.legal_entity.name",
    "branch.code": "organization.branch.code",
    "branch.name": "organization.branch.name",
    "department.code": "organization.department.code",
    "department.name": "organization.department.name",
    "position.code": "organization.position.code",
    "position.title": "organization.position.title",
    "effective_from": "assignment.effective_from",
}

_LEGACY_EMPLOYEE_FIELDS = {
    "id": "employee.id",
    "employee_number": "employee.employee_number",
    "first_name": "employee.first_name",
    "last_name": "employee.last_name",
    "email": "employee.email",
    "department": "employee.department",
    "position": "employee.position",
    "status": "employee.status",
    "employment_start_date": "employee.employment_start_date",
    "employment_end_date": "employee.employment_end_date",
    "version": "employee.version",
    "current_assignment.id": "assignment.id",
    "current_assignment.legal_entity.id": "organization.legal_entity.id",
    "current_assignment.legal_entity.code": "organization.legal_entity.code",
    "current_assignment.legal_entity.name": "organization.legal_entity.name",
    "current_assignment.branch.id": "organization.branch.id",
    "current_assignment.branch.code": "organization.branch.code",
    "current_assignment.branch.name": "organization.branch.name",
    "current_assignment.department.id": "organization.department.id",
    "current_assignment.department.code": "organization.department.code",
    "current_assignment.department.name": "organization.department.name",
    "current_assignment.position.id": "organization.position.id",
    "current_assignment.position.code": "organization.position.code",
    "current_assignment.position.title": "organization.position.title",
    "current_assignment.effective_from": "assignment.effective_from",
}

_RESPONSE_CONTRACTS: dict[type[BaseModel], tuple[EmployeeProjectionScope, dict[str, str]]] = {
    EmployeeRead: (EmployeeProjectionScope.HR_TENANT, _LEGACY_EMPLOYEE_FIELDS),
    EmployeeProfileRead: (EmployeeProjectionScope.HR_TENANT, _HR_PROFILE_FIELDS),
    EmployeePersonalProfileMutationRead: (
        EmployeeProjectionScope.HR_TENANT,
        {
            field_name: policy_name
            for field_name, policy_name in _HR_PROFILE_FIELDS.items()
            if field_name.startswith(("core.", "personal."))
        },
    ),
    EmployeeEmploymentProfileMutationRead: (
        EmployeeProjectionScope.HR_TENANT,
        {
            field_name: policy_name
            for field_name, policy_name in _HR_PROFILE_FIELDS.items()
            if field_name.startswith(("core.", "employment."))
        },
    ),
    TeamMemberRead: (
        EmployeeProjectionScope.MANAGER_TEAM,
        {
            **{f"employee.{key}": value for key, value in _MANAGER_EMPLOYEE_FIELDS.items()},
            **{f"assignment.{key}": value for key, value in _MANAGER_ASSIGNMENT_FIELDS.items()},
        },
    ),
    ManagerTeamMemberProfileRead: (
        EmployeeProjectionScope.MANAGER_TEAM,
        {
            **{f"core.{key}": value for key, value in _MANAGER_EMPLOYEE_FIELDS.items()},
            "employment.employment_start_date": "employee.employment_start_date",
            "employment.contract_type": "employment.contract_type",
            "employment.work_type": "employment.work_type",
            **{
                f"organization.current_assignment.{key}": value
                for key, value in _MANAGER_ASSIGNMENT_FIELDS.items()
            },
            "organization.current_assignment.manager.full_name": ("organization.manager.full_name"),
        },
    ),
    OwnEmployeeProfileStateRead: (
        EmployeeProjectionScope.EMPLOYEE_OWN,
        {
            "availability": "projection.availability",
            "employee_id": "employee.id",
            "profile.core.id": "employee.id",
            "profile.core.employee_number": "employee.employee_number",
            "profile.core.first_name": "employee.first_name",
            "profile.core.last_name": "employee.last_name",
            "profile.core.email": "employee.email",
            "profile.core.status": "employee.status",
            "profile.personal.preferred_name": "personal.preferred_name",
            "profile.personal.birth_date.visibility": "projection.mask_visibility",
            "profile.personal.birth_date.display_value": "projection.mask_display",
            "profile.personal.phone.visibility": "projection.mask_visibility",
            "profile.personal.phone.display_value": "projection.mask_display",
            "profile.employment.employment_start_date": "employee.employment_start_date",
            "profile.employment.contract_type": "employment.contract_type",
            "profile.employment.work_type": "employment.work_type",
            "profile.organization.current_assignment.legal_entity.code": (
                "organization.legal_entity.code"
            ),
            "profile.organization.current_assignment.legal_entity.name": (
                "organization.legal_entity.name"
            ),
            "profile.organization.current_assignment.branch.code": ("organization.branch.code"),
            "profile.organization.current_assignment.branch.name": ("organization.branch.name"),
            "profile.organization.current_assignment.department.code": (
                "organization.department.code"
            ),
            "profile.organization.current_assignment.department.name": (
                "organization.department.name"
            ),
            "profile.organization.current_assignment.position.code": ("organization.position.code"),
            "profile.organization.current_assignment.position.title": (
                "organization.position.title"
            ),
            "profile.organization.current_assignment.manager.full_name": (
                "organization.manager.full_name"
            ),
        },
    ),
}

EMPLOYEE_RESPONSE_FIELD_REGISTRY = MappingProxyType(
    {
        model.__name__: MappingProxyType(fields)
        for model, (_scope, fields) in _RESPONSE_CONTRACTS.items()
    }
)


def response_model_leaf_paths(model: type[BaseModel]) -> frozenset[str]:
    """Return named leaves and reject implicit serializers that bypass the registry."""

    leaves: set[str] = set()

    def visit(annotation: object, prefix: str) -> None:
        origin = get_origin(annotation)
        if origin is not None:
            candidates = tuple(
                candidate for candidate in get_args(annotation) if candidate is not type(None)
            )
            nested = False
            for candidate in candidates:
                candidate_origin = get_origin(candidate)
                if candidate_origin in {list, tuple, set, frozenset}:
                    visit(get_args(candidate)[0], prefix)
                    nested = True
                elif isinstance(candidate, type) and issubclass(candidate, BaseModel):
                    visit(candidate, prefix)
                    nested = True
            if nested:
                return
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            computed_fields = annotation.model_computed_fields
            model_serializers = annotation.__pydantic_decorators__.model_serializers
            if computed_fields or model_serializers:
                implicit_names = sorted((*computed_fields, *model_serializers))
                raise UnclassifiedEmployeeFieldError(
                    f"{annotation.__name__} has implicit serialized fields: {implicit_names}"
                )
            for field_name, field in annotation.model_fields.items():
                visit(field.annotation, f"{prefix}.{field_name}" if prefix else field_name)
            return
        leaves.add(prefix)

    visit(model, "")
    return frozenset(leaves)


def enforce_response_contract(response: BaseModel) -> None:
    """Fail at runtime if a response schema gains an unclassified or newly visible leaf."""

    model = type(response)
    try:
        scope, registered = _RESPONSE_CONTRACTS[model]
    except KeyError as exc:
        raise UnclassifiedEmployeeFieldError(model.__name__) from exc
    actual = response_model_leaf_paths(model)
    expected = frozenset(registered)
    if actual != expected:
        difference = sorted(actual.symmetric_difference(expected))
        raise UnclassifiedEmployeeFieldError(
            f"{model.__name__} response fields differ: {difference}"
        )
    for field_name, policy_name in registered.items():
        visibility = field_policy(policy_name).visibility(scope)
        if visibility is EXCLUDED:
            raise EmployeeFieldExcludedError(
                f"{model.__name__}.{field_name} is excluded from {scope.value}"
            )


def enforce_hr_profile_contract(profile: EmployeeProfileRead) -> EmployeeProfileRead:
    enforce_response_contract(profile)
    return profile


# Exact ORM namespaces guarded by the central coverage test.  Adding a persisted field requires
# an explicit classification before it can be intentionally projected anywhere.
EMPLOYEE_DOMAIN_MODEL_FIELDS = MappingProxyType(
    {
        Employee.__name__: frozenset(
            field_name.removeprefix("employee.")
            for field_name in EMPLOYEE_FIELD_POLICIES
            if field_name.startswith("employee.")
        ),
        EmployeePersonalProfile.__name__: frozenset(
            field_name.removeprefix("personal.")
            for field_name in EMPLOYEE_FIELD_POLICIES
            if field_name.startswith("personal.")
        ),
        EmployeeEmploymentProfile.__name__: frozenset(
            field_name.removeprefix("employment.")
            for field_name in EMPLOYEE_FIELD_POLICIES
            if field_name.startswith("employment.")
        ),
        EmployeeAssignment.__name__: frozenset(
            field_name.removeprefix("assignment.")
            for field_name in EMPLOYEE_FIELD_POLICIES
            if field_name.startswith("assignment.") and field_name != "assignment.is_current"
        ),
    }
)


def enforce_legacy_employee_response_contract() -> None:
    """Keep the additive P4A employee response inside the same classification registry."""

    scope, fields = _RESPONSE_CONTRACTS[EmployeeRead]
    actual = response_model_leaf_paths(EmployeeRead)
    if actual != frozenset(fields):
        raise UnclassifiedEmployeeFieldError(
            f"EmployeeRead response fields differ: {sorted(actual.symmetric_difference(fields))}"
        )
    for policy_name in fields.values():
        if field_policy(policy_name).visibility(scope) is EXCLUDED:
            raise EmployeeFieldExcludedError(policy_name)


__all__ = [
    "EMPLOYEE_DOMAIN_MODEL_FIELDS",
    "EMPLOYEE_RESPONSE_FIELD_REGISTRY",
    "enforce_hr_profile_contract",
    "enforce_legacy_employee_response_contract",
    "enforce_response_contract",
    "response_model_leaf_paths",
]
