from __future__ import annotations

import ast
import inspect
from datetime import date
from uuid import UUID

import pytest
from app.models.employee import Employee
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_profile import (
    EmployeeEmploymentProfile,
    EmployeePersonalProfile,
)
from app.schemas.employee import EmployeeRead
from app.schemas.employee_account_link import (
    OwnEmployeeEmploymentProfileRead,
    OwnEmployeeOrganizationRead,
    OwnEmployeePersonalProfileRead,
    OwnEmployeeProfileCoreRead,
    OwnEmployeeProfileRead,
    OwnEmployeeProfileStateRead,
    OwnMaskedFieldRead,
)
from app.schemas.employee_assignment import (
    ManagerTeamAssignmentRead,
    ManagerTeamCurrentAssignmentRead,
    ManagerTeamEmployeeRead,
    ManagerTeamEmploymentRead,
    ManagerTeamMemberProfileRead,
    ManagerTeamOrganizationRead,
    ManagerTeamOrganizationReferenceRead,
    ManagerTeamPositionReferenceRead,
    TeamMemberRead,
)
from app.schemas.employee_profile import (
    EmployeeEmploymentProfileMutationRead,
    EmployeeEmploymentProfileRead,
    EmployeePersonalProfileMutationRead,
    EmployeePersonalProfileRead,
    EmployeeProfileCoreRead,
    EmployeeProfileOrganizationRead,
    EmployeeProfileRead,
)
from app.services import (
    employee_field_policy,
    employee_field_projection,
    employee_projection_contract,
)
from app.services.employee_field_policy import (
    EMPLOYEE_FIELD_POLICIES,
    RESTRICTED_FUTURE_FIELD_NAMES,
    EmployeeFieldClass,
    EmployeeFieldExcludedError,
    EmployeeFieldVisibility,
    EmployeeProjectionScope,
    UnclassifiedEmployeeFieldError,
    field_policy,
    project_field,
)
from app.services.employee_projection_contract import (
    EMPLOYEE_DOMAIN_MODEL_FIELDS,
    EMPLOYEE_RESPONSE_FIELD_REGISTRY,
    response_model_leaf_paths,
)
from pydantic import BaseModel, computed_field, model_serializer

EMPLOYEE_ID = UUID("a4000000-0000-4000-8000-000000000001")
RAW_PHONE = "+90 555 987 6543"
RAW_BIRTH_DATE = date(1992, 5, 14)

FUTURE_RESTRICTED_FIELDS = frozenset(
    {
        "restricted.national_identifier",
        "restricted.passport",
        "restricted.bank_account",
        "restricted.iban",
        "restricted.compensation",
        "restricted.payroll",
        "restricted.health",
        "restricted.private_address",
        "restricted.emergency_contact",
    }
)


def test_policy_classifies_current_domain_and_future_sensitive_fields_explicitly() -> None:
    registry_fields = set(EMPLOYEE_FIELD_POLICIES)
    model_fields = {
        *(f"employee.{column.name}" for column in Employee.__table__.columns),
        *(f"personal.{column.name}" for column in EmployeePersonalProfile.__table__.columns),
        *(f"employment.{column.name}" for column in EmployeeEmploymentProfile.__table__.columns),
        *(f"assignment.{column.name}" for column in EmployeeAssignment.__table__.columns),
    }

    assert model_fields <= registry_fields
    assert FUTURE_RESTRICTED_FIELDS <= RESTRICTED_FUTURE_FIELD_NAMES
    assert RESTRICTED_FUTURE_FIELD_NAMES <= registry_fields
    assert field_policy("employee.employee_number").classification is (EmployeeFieldClass.WORK_SAFE)
    assert field_policy("personal.preferred_name").classification is (EmployeeFieldClass.WORK_SAFE)
    assert field_policy("personal.phone").classification is (EmployeeFieldClass.PERSONAL_CONTACT)
    assert field_policy("personal.birth_date").classification is (
        EmployeeFieldClass.PERSONAL_CONTACT
    )
    assert field_policy("assignment.manager_user_id").classification is (
        EmployeeFieldClass.OPERATIONAL_INTERNAL
    )
    assert all(
        field_policy(field_name).classification is EmployeeFieldClass.RESTRICTED_FUTURE
        for field_name in RESTRICTED_FUTURE_FIELD_NAMES
    )
    assert all(
        all(
            field_policy(field_name).visibility(scope) is EmployeeFieldVisibility.EXCLUDED
            for scope in EmployeeProjectionScope
        )
        for field_name in RESTRICTED_FUTURE_FIELD_NAMES
    )

    for model in (
        Employee,
        EmployeePersonalProfile,
        EmployeeEmploymentProfile,
        EmployeeAssignment,
    ):
        assert EMPLOYEE_DOMAIN_MODEL_FIELDS[model.__name__] == frozenset(
            column.name for column in model.__table__.columns
        )


def test_policy_projects_one_source_differently_for_hr_manager_and_own() -> None:
    values = {
        "employee.id": EMPLOYEE_ID,
        "employee.employee_number": "WF-001",
        "employee.first_name": "Ada",
        "employee.last_name": "Yilmaz",
        "employee.email": "ada@example.test",
        "employee.status": "active",
        "personal.preferred_name": "Ada",
        "personal.birth_date": RAW_BIRTH_DATE,
        "personal.phone": RAW_PHONE,
        "employee.employment_start_date": date(2026, 7, 1),
        "employment.contract_type": "indefinite",
        "employment.work_type": "full_time",
        "employee.version": 7,
        "personal.version": 8,
        "employment.version": 9,
        "assignment.manager_user_id": UUID("a4000000-0000-4000-8000-000000000002"),
        "restricted.national_identifier": "TR-12345678901",
        "restricted.iban": "TR000000000000000000000001",
    }

    def projection(scope: EmployeeProjectionScope) -> dict[str, object]:
        result: dict[str, object] = {}
        for field_name, value in values.items():
            try:
                result[field_name] = project_field(scope, field_name, value)
            except EmployeeFieldExcludedError:
                pass
        return result

    hr = projection(EmployeeProjectionScope.HR_TENANT)
    manager = projection(EmployeeProjectionScope.MANAGER_TEAM)
    own = projection(EmployeeProjectionScope.EMPLOYEE_OWN)

    assert hr["personal.phone"] == RAW_PHONE
    assert hr["personal.birth_date"] == RAW_BIRTH_DATE
    assert hr["employee.version"] == 7

    assert set(manager) == {
        "employee.id",
        "employee.employee_number",
        "employee.first_name",
        "employee.last_name",
        "employee.email",
        "employee.status",
        "personal.preferred_name",
        "employee.employment_start_date",
        "employment.contract_type",
        "employment.work_type",
    }

    own_phone = own["personal.phone"]
    own_birth_date = own["personal.birth_date"]
    assert isinstance(own_phone, OwnMaskedFieldRead)
    assert isinstance(own_birth_date, OwnMaskedFieldRead)
    assert own_phone.visibility == "masked"
    assert own_birth_date.visibility == "masked"
    assert own_phone.display_value is not None
    assert own_birth_date.display_value is not None
    assert RAW_PHONE not in own_phone.display_value
    assert RAW_BIRTH_DATE.isoformat() not in own_birth_date.display_value
    assert own_phone.display_value.endswith("43")
    for field_name in (
        "employee.version",
        "personal.version",
        "employment.version",
        "assignment.manager_user_id",
        *RESTRICTED_FUTURE_FIELD_NAMES,
    ):
        assert field_name not in manager
        assert field_name not in own


def test_own_masking_has_an_explicit_unavailable_state_and_no_reveal_contract() -> None:
    projected = {
        field_name: project_field(
            EmployeeProjectionScope.EMPLOYEE_OWN,
            field_name,
            None,
        )
        for field_name in ("personal.phone", "personal.birth_date")
    }

    assert projected == {
        "personal.phone": OwnMaskedFieldRead(visibility="unavailable", display_value=None),
        "personal.birth_date": OwnMaskedFieldRead(visibility="unavailable", display_value=None),
    }
    assert set(OwnMaskedFieldRead.model_fields) == {"visibility", "display_value"}


def test_policy_fails_closed_for_an_unclassified_field_and_uses_no_bulk_dump() -> None:
    with pytest.raises(UnclassifiedEmployeeFieldError):
        project_field(
            EmployeeProjectionScope.HR_TENANT,
            "employee.unclassified_new_field",
            "must-never-leak",
        )

    source = "\n".join(
        inspect.getsource(module)
        for module in (
            employee_field_policy,
            employee_field_projection,
            employee_projection_contract,
        )
    )
    tree = ast.parse(source)
    forbidden_attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in {"model_dump", "model_dump_json", "__dict__"}
    }
    forbidden_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "vars"
    }
    assert forbidden_attributes == set()
    assert forbidden_calls == set()


def test_response_coverage_rejects_implicit_pydantic_output_fields() -> None:
    class ComputedOutput(BaseModel):
        allowed: str

        @computed_field
        @property
        def unclassified_secret(self) -> str:
            return "must-never-serialize"

    class CustomSerializedOutput(BaseModel):
        allowed: str

        @model_serializer
        def serialize_model(self) -> dict[str, str]:
            return {
                "allowed": self.allowed,
                "unclassified_secret": "must-never-serialize",
            }

    for response_model in (ComputedOutput, CustomSerializedOutput):
        with pytest.raises(
            UnclassifiedEmployeeFieldError,
            match="implicit serialized fields",
        ):
            response_model_leaf_paths(response_model)


def test_response_contract_registries_are_exact_and_cannot_grow_silently() -> None:
    expected_fields = {
        EmployeeProfileCoreRead: {
            "id",
            "employee_number",
            "first_name",
            "last_name",
            "email",
            "status",
            "employee_version",
        },
        EmployeePersonalProfileRead: {
            "preferred_name",
            "birth_date",
            "phone",
            "version",
        },
        EmployeeEmploymentProfileRead: {
            "employment_start_date",
            "contract_type",
            "work_type",
            "version",
        },
        EmployeeProfileOrganizationRead: {
            "current_assignment",
            "history",
            "history_limit",
            "history_truncated",
        },
        EmployeeProfileRead: {"core", "personal", "employment", "organization"},
        EmployeePersonalProfileMutationRead: {"core", "personal"},
        EmployeeEmploymentProfileMutationRead: {"core", "employment"},
        ManagerTeamEmployeeRead: {
            "id",
            "employee_number",
            "first_name",
            "last_name",
            "preferred_name",
            "email",
            "status",
        },
        ManagerTeamOrganizationReferenceRead: {"code", "name"},
        ManagerTeamPositionReferenceRead: {"code", "title"},
        ManagerTeamAssignmentRead: {
            "legal_entity",
            "branch",
            "department",
            "position",
            "effective_from",
        },
        TeamMemberRead: {"employee", "assignment"},
        ManagerTeamCurrentAssignmentRead: {
            "legal_entity",
            "branch",
            "department",
            "position",
            "effective_from",
            "manager",
        },
        ManagerTeamEmploymentRead: {
            "employment_start_date",
            "contract_type",
            "work_type",
        },
        ManagerTeamOrganizationRead: {"current_assignment"},
        ManagerTeamMemberProfileRead: {"core", "employment", "organization"},
        OwnEmployeeProfileCoreRead: {
            "id",
            "employee_number",
            "first_name",
            "last_name",
            "email",
            "status",
        },
        OwnEmployeePersonalProfileRead: {
            "preferred_name",
            "birth_date",
            "phone",
        },
        OwnEmployeeEmploymentProfileRead: {
            "employment_start_date",
            "contract_type",
            "work_type",
        },
        OwnEmployeeOrganizationRead: {"current_assignment"},
        OwnEmployeeProfileRead: {"core", "personal", "employment", "organization"},
        OwnEmployeeProfileStateRead: {"availability", "employee_id", "profile"},
    }

    for model, fields in expected_fields.items():
        assert set(model.model_fields) == fields, model.__name__

    registered_models = {
        EmployeeRead,
        EmployeeProfileRead,
        EmployeePersonalProfileMutationRead,
        EmployeeEmploymentProfileMutationRead,
        TeamMemberRead,
        ManagerTeamMemberProfileRead,
        OwnEmployeeProfileStateRead,
    }
    assert set(EMPLOYEE_RESPONSE_FIELD_REGISTRY) == {model.__name__ for model in registered_models}
    for model in registered_models:
        assert response_model_leaf_paths(model) == frozenset(
            EMPLOYEE_RESPONSE_FIELD_REGISTRY[model.__name__]
        )
