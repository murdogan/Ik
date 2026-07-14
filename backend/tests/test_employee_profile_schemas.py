from datetime import date
from uuid import UUID

import pytest
from app.schemas.employee_profile import (
    EmployeeContractType,
    EmployeeEmploymentProfileUpdate,
    EmployeePersonalProfileUpdate,
    EmployeeProfileRead,
    EmployeeWorkType,
)
from pydantic import ValidationError

EMPLOYEE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def test_employee_profile_read_contract_has_exact_section_shapes() -> None:
    profile = EmployeeProfileRead.model_validate(
        {
            "core": {
                "id": str(EMPLOYEE_ID),
                "employee_number": "WF-001",
                "first_name": "Ada",
                "last_name": "Yilmaz",
                "email": "ada@example.test",
                "status": "active",
                "employee_version": 3,
            },
            "personal": {
                "preferred_name": "Ada",
                "birth_date": "1992-05-14",
                "phone": "+90 555 000 0000",
                "version": 2,
            },
            "employment": {
                "employment_start_date": "2026-07-01",
                "contract_type": "indefinite",
                "work_type": "full_time",
                "version": 4,
            },
            "organization": {
                "current_assignment": None,
                "history": [],
                "history_limit": 50,
                "history_truncated": False,
            },
        }
    )

    dumped = profile.model_dump(mode="json")
    assert set(dumped) == {"core", "personal", "employment", "organization"}
    assert set(dumped["core"]) == {
        "id",
        "employee_number",
        "first_name",
        "last_name",
        "email",
        "status",
        "employee_version",
    }
    assert set(dumped["personal"]) == {
        "preferred_name",
        "birth_date",
        "phone",
        "version",
    }
    assert set(dumped["employment"]) == {
        "employment_start_date",
        "contract_type",
        "work_type",
        "version",
    }
    assert set(dumped["organization"]) == {
        "current_assignment",
        "history",
        "history_limit",
        "history_truncated",
    }


def test_personal_update_exposes_only_approved_fields_and_requires_section_version() -> None:
    assert set(EmployeePersonalProfileUpdate.model_fields) == {
        "expected_version",
        "expected_employee_version",
        "first_name",
        "last_name",
        "email",
        "preferred_name",
        "birth_date",
        "phone",
    }

    with pytest.raises(ValidationError):
        EmployeePersonalProfileUpdate(preferred_name="Ada")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("first_name", "Ayse"),
        ("last_name", "Demir"),
        ("email", "new@example.test"),
    ],
)
def test_personal_update_requires_employee_version_for_core_owned_fields(
    field: str,
    value: str,
) -> None:
    with pytest.raises(ValidationError):
        EmployeePersonalProfileUpdate(expected_version=1, **{field: value})

    payload = EmployeePersonalProfileUpdate(
        expected_version=1,
        expected_employee_version=2,
        **{field: value},
    )
    assert payload.expected_employee_version == 2


def test_personal_update_allows_section_only_changes_and_explicit_clears() -> None:
    payload = EmployeePersonalProfileUpdate(
        expected_version=2,
        preferred_name=None,
        birth_date=None,
        phone=None,
    )

    assert payload.model_dump(exclude_unset=True) == {
        "expected_version": 2,
        "preferred_name": None,
        "birth_date": None,
        "phone": None,
    }


@pytest.mark.parametrize(
    "forbidden",
    [
        {"gender": "female"},
        {"marital_status": "single"},
        {"nationality": "TR"},
        {"tckn": "10000000146"},
        {"address": "private"},
        {"salary": 100_000},
        {"status": "terminated"},
        {"employment_end_date": "2026-08-01"},
        {"department_id": str(EMPLOYEE_ID)},
    ],
)
def test_personal_update_rejects_forbidden_and_out_of_section_fields(
    forbidden: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        EmployeePersonalProfileUpdate(expected_version=1, **forbidden)


def test_employment_update_has_narrow_enums_and_requires_section_version() -> None:
    assert [value.value for value in EmployeeContractType] == [
        "indefinite",
        "fixed_term",
    ]
    assert [value.value for value in EmployeeWorkType] == [
        "full_time",
        "part_time",
    ]
    assert set(EmployeeEmploymentProfileUpdate.model_fields) == {
        "expected_version",
        "expected_employee_version",
        "employment_start_date",
        "contract_type",
        "work_type",
    }

    with pytest.raises(ValidationError):
        EmployeeEmploymentProfileUpdate(contract_type="indefinite")


def test_employment_update_requires_employee_version_only_for_start_date() -> None:
    section_only = EmployeeEmploymentProfileUpdate(
        expected_version=1,
        contract_type=EmployeeContractType.FIXED_TERM,
        work_type=EmployeeWorkType.PART_TIME,
    )
    assert section_only.expected_employee_version is None

    with pytest.raises(ValidationError):
        EmployeeEmploymentProfileUpdate(
            expected_version=1,
            employment_start_date=date(2026, 7, 2),
        )

    core_update = EmployeeEmploymentProfileUpdate(
        expected_version=1,
        expected_employee_version=3,
        employment_start_date=date(2026, 7, 2),
    )
    assert core_update.expected_employee_version == 3


def test_employment_update_allows_clears_but_rejects_unknown_codes_and_lifecycle() -> None:
    clears = EmployeeEmploymentProfileUpdate(
        expected_version=1,
        contract_type=None,
        work_type=None,
    )
    assert clears.model_dump(exclude_unset=True) == {
        "expected_version": 1,
        "contract_type": None,
        "work_type": None,
    }

    for invalid_payload in (
        {"contract_type": "contractor"},
        {"work_type": "hybrid"},
        {"status": "terminated"},
        {"employment_end_date": "2026-08-01"},
        {"manager_id": str(EMPLOYEE_ID)},
    ):
        with pytest.raises(ValidationError):
            EmployeeEmploymentProfileUpdate(expected_version=1, **invalid_payload)


@pytest.mark.parametrize("value", [0, -1, None])
def test_profile_update_versions_are_strictly_positive(value: int | None) -> None:
    with pytest.raises(ValidationError):
        EmployeePersonalProfileUpdate(expected_version=value, preferred_name="Ada")

    with pytest.raises(ValidationError):
        EmployeeEmploymentProfileUpdate(expected_version=value, work_type="full_time")


def test_profile_updates_require_at_least_one_mutable_field() -> None:
    with pytest.raises(ValidationError):
        EmployeePersonalProfileUpdate(expected_version=1)

    with pytest.raises(ValidationError):
        EmployeeEmploymentProfileUpdate(expected_version=1)
