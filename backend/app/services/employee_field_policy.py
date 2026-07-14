"""Closed employee-field classification and per-scope visibility policy.

Authorization and relationship scope are proved by calling services. This module owns the
deny-by-default decision for each employee field and the only explicit masking implementations.
Projection constructors and schema coverage live in adjacent small modules and call this policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import MappingProxyType
from typing import cast

from app.schemas.employee_account_link import OwnMaskedFieldRead


class EmployeeFieldClass(StrEnum):
    WORK_SAFE = "work_safe"
    PERSONAL_CONTACT = "personal_contact"
    OPERATIONAL_INTERNAL = "operational_internal"
    RESTRICTED_FUTURE = "restricted_future"


class EmployeeProjectionScope(StrEnum):
    HR_TENANT = "hr_tenant"
    MANAGER_TEAM = "manager_team"
    EMPLOYEE_OWN = "employee_own"


class EmployeeFieldVisibility(StrEnum):
    FULL = "full"
    MASKED = "masked"
    EXCLUDED = "excluded"


class UnclassifiedEmployeeFieldError(RuntimeError):
    """A field absent from the closed registry reached a projection boundary."""


class EmployeeFieldExcludedError(RuntimeError):
    """A classified field was requested for a scope where it is not visible."""


@dataclass(frozen=True, slots=True)
class EmployeeFieldPolicy:
    classification: EmployeeFieldClass
    hr_tenant: EmployeeFieldVisibility = EmployeeFieldVisibility.EXCLUDED
    manager_team: EmployeeFieldVisibility = EmployeeFieldVisibility.EXCLUDED
    employee_own: EmployeeFieldVisibility = EmployeeFieldVisibility.EXCLUDED

    def visibility(self, scope: EmployeeProjectionScope) -> EmployeeFieldVisibility:
        if scope is EmployeeProjectionScope.HR_TENANT:
            return self.hr_tenant
        if scope is EmployeeProjectionScope.MANAGER_TEAM:
            return self.manager_team
        return self.employee_own


FULL = EmployeeFieldVisibility.FULL
MASKED = EmployeeFieldVisibility.MASKED
EXCLUDED = EmployeeFieldVisibility.EXCLUDED
WORK_SAFE = EmployeeFieldClass.WORK_SAFE
PERSONAL_CONTACT = EmployeeFieldClass.PERSONAL_CONTACT
OPERATIONAL_INTERNAL = EmployeeFieldClass.OPERATIONAL_INTERNAL
RESTRICTED_FUTURE = EmployeeFieldClass.RESTRICTED_FUTURE


def _policy(
    classification: EmployeeFieldClass,
    *,
    hr: EmployeeFieldVisibility = EXCLUDED,
    manager: EmployeeFieldVisibility = EXCLUDED,
    own: EmployeeFieldVisibility = EXCLUDED,
) -> EmployeeFieldPolicy:
    return EmployeeFieldPolicy(
        classification=classification,
        hr_tenant=hr,
        manager_team=manager,
        employee_own=own,
    )


# These names are policy-only sentinels.  They are not schema, persistence, encryption, or future
# reveal placeholders.  Their explicit classification makes the permanent no-audience decision
# testable while the product deliberately has no such data fields.
RESTRICTED_FUTURE_FIELD_NAMES = frozenset(
    {
        "restricted.bank_account",
        "restricted.compensation",
        "restricted.emergency_contact",
        "restricted.health",
        "restricted.iban",
        "restricted.national_identifier",
        "restricted.passport",
        "restricted.payroll",
        "restricted.private_address",
        "restricted.special_category",
        "restricted.tckn",
    }
)


_FIELD_POLICIES: dict[str, EmployeeFieldPolicy] = {
    # Employee domain and public work identity.
    "employee.id": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "employee.tenant_id": _policy(OPERATIONAL_INTERNAL),
    "employee.employee_number": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "employee.employee_number_normalized": _policy(OPERATIONAL_INTERNAL),
    "employee.first_name": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "employee.last_name": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "employee.full_name_normalized": _policy(OPERATIONAL_INTERNAL),
    "employee.email": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "employee.email_normalized": _policy(OPERATIONAL_INTERNAL),
    "employee.department": _policy(WORK_SAFE, hr=FULL),
    "employee.department_normalized": _policy(OPERATIONAL_INTERNAL),
    "employee.position": _policy(WORK_SAFE, hr=FULL),
    "employee.status": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "employee.version": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "employee.employment_start_date": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "employee.employment_end_date": _policy(WORK_SAFE, hr=FULL),
    "employee.archived_at": _policy(OPERATIONAL_INTERNAL),
    "employee.created_at": _policy(OPERATIONAL_INTERNAL),
    "employee.updated_at": _policy(OPERATIONAL_INTERNAL),
    # Focused personal profile.
    "personal.id": _policy(OPERATIONAL_INTERNAL),
    "personal.tenant_id": _policy(OPERATIONAL_INTERNAL),
    "personal.employee_id": _policy(OPERATIONAL_INTERNAL),
    "personal.preferred_name": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "personal.birth_date": _policy(PERSONAL_CONTACT, hr=FULL, own=MASKED),
    "personal.phone": _policy(PERSONAL_CONTACT, hr=FULL, own=MASKED),
    "personal.version": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "personal.created_at": _policy(OPERATIONAL_INTERNAL),
    "personal.updated_at": _policy(OPERATIONAL_INTERNAL),
    # Focused employment profile.
    "employment.id": _policy(OPERATIONAL_INTERNAL),
    "employment.tenant_id": _policy(OPERATIONAL_INTERNAL),
    "employment.employee_id": _policy(OPERATIONAL_INTERNAL),
    "employment.contract_type": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "employment.work_type": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "employment.version": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "employment.created_at": _policy(OPERATIONAL_INTERNAL),
    "employment.updated_at": _policy(OPERATIONAL_INTERNAL),
    # Current organization display and HR-only assignment operations metadata.
    "assignment.id": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "assignment.tenant_id": _policy(OPERATIONAL_INTERNAL),
    "assignment.employee_id": _policy(OPERATIONAL_INTERNAL),
    "assignment.legal_entity_id": _policy(OPERATIONAL_INTERNAL),
    "assignment.branch_id": _policy(OPERATIONAL_INTERNAL),
    "assignment.department_id": _policy(OPERATIONAL_INTERNAL),
    "assignment.position_id": _policy(OPERATIONAL_INTERNAL),
    "assignment.manager_user_id": _policy(OPERATIONAL_INTERNAL),
    "assignment.effective_from": _policy(WORK_SAFE, hr=FULL, manager=FULL),
    "assignment.effective_to": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "assignment.supersedes_assignment_id": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "assignment.change_reason": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "assignment.is_current": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "assignment.created_at": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "assignment.updated_at": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "assignment.created_by_user_id": _policy(OPERATIONAL_INTERNAL),
    "organization.legal_entity.id": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "organization.legal_entity.code": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "organization.legal_entity.name": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "organization.legal_entity.status": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "organization.branch.id": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "organization.branch.code": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "organization.branch.name": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "organization.branch.status": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "organization.department.id": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "organization.department.code": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "organization.department.name": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "organization.department.status": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "organization.position.id": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "organization.position.code": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "organization.position.title": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "organization.position.status": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "organization.manager.id": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "organization.manager.full_name": _policy(WORK_SAFE, hr=FULL, manager=FULL, own=FULL),
    "organization.manager.email": _policy(WORK_SAFE, hr=FULL),
    "organization.manager.status": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "organization.history_limit": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    "organization.history_truncated": _policy(OPERATIONAL_INTERNAL, hr=FULL),
    # Projection-shape metadata contains no employee value.
    "projection.availability": _policy(OPERATIONAL_INTERNAL, own=FULL),
    "projection.mask_visibility": _policy(OPERATIONAL_INTERNAL, own=FULL),
    "projection.mask_display": _policy(PERSONAL_CONTACT, own=MASKED),
}
for _restricted_name in RESTRICTED_FUTURE_FIELD_NAMES:
    _FIELD_POLICIES[_restricted_name] = _policy(RESTRICTED_FUTURE)

EMPLOYEE_FIELD_POLICIES = MappingProxyType(_FIELD_POLICIES)


def field_policy(field_name: str) -> EmployeeFieldPolicy:
    try:
        return EMPLOYEE_FIELD_POLICIES[field_name]
    except KeyError as exc:
        raise UnclassifiedEmployeeFieldError(field_name) from exc


def project_field[T](
    scope: EmployeeProjectionScope,
    field_name: str,
    value: T,
) -> T | OwnMaskedFieldRead:
    """Project one explicitly named value or fail closed for absent/excluded policy."""

    visibility = field_policy(field_name).visibility(scope)
    if visibility is EXCLUDED:
        raise EmployeeFieldExcludedError(f"{field_name} is excluded from {scope.value}")
    if visibility is FULL:
        return value
    if scope is not EmployeeProjectionScope.EMPLOYEE_OWN:
        raise EmployeeFieldExcludedError(f"{field_name} has no masker for {scope.value}")
    if field_name == "personal.phone":
        return _mask_phone(cast(str | None, value))
    if field_name == "personal.birth_date":
        return _mask_birth_date(cast(date | None, value))
    raise EmployeeFieldExcludedError(f"{field_name} has no explicit mask implementation")


def _mask_phone(value: str | None) -> OwnMaskedFieldRead:
    if value is None:
        return OwnMaskedFieldRead(visibility="unavailable", display_value=None)
    digits = "".join(character for character in value if character.isdigit())
    suffix = digits[-2:] if len(digits) >= 2 else ""
    return OwnMaskedFieldRead(
        visibility="masked",
        display_value=f"••••••••{suffix}",
    )


def _mask_birth_date(value: date | None) -> OwnMaskedFieldRead:
    if value is None:
        return OwnMaskedFieldRead(visibility="unavailable", display_value=None)
    return OwnMaskedFieldRead(
        visibility="masked",
        display_value=f"••••-{value.month:02d}-{value.day:02d}",
    )


__all__ = [
    "EMPLOYEE_FIELD_POLICIES",
    "EXCLUDED",
    "EmployeeFieldClass",
    "EmployeeFieldExcludedError",
    "EmployeeFieldPolicy",
    "EmployeeFieldVisibility",
    "EmployeeProjectionScope",
    "RESTRICTED_FUTURE_FIELD_NAMES",
    "UnclassifiedEmployeeFieldError",
    "field_policy",
    "project_field",
]
