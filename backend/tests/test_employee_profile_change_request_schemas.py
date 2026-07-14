from datetime import date

import pytest
from app.schemas.employee_profile_change_request import (
    EmployeeProfileChangeRequestCreate,
    EmployeeProfileChangeRequestReject,
)
from pydantic import ValidationError


def test_create_accepts_only_selected_typed_fields_and_explicit_clear() -> None:
    payload = EmployeeProfileChangeRequestCreate(
        preferred_name="  Ada   Deniz  ",
        phone="+90 (555) 000-0000",
        birth_date="1992-05-14",
    )

    assert payload.preferred_name == "Ada Deniz"
    assert payload.phone == "+905550000000"
    assert payload.birth_date == date(1992, 5, 14)
    assert payload.selected_fields() == ("preferred_name", "phone", "birth_date")
    clear = EmployeeProfileChangeRequestCreate(phone=None)
    assert clear.selected_fields() == ("phone",)
    assert clear.phone is None


@pytest.mark.parametrize(
    "candidate",
    [
        {},
        {"first_name": "Forbidden"},
        {"employee_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
        {"changes": {"phone": "+905550000000"}},
        {"phone": ""},
        {"phone": "••••••••00"},
        {"phone": "▪▪▪▪▪▪▪▪00"},
        {"phone": "◦◦◦◦◦◦◦◦00"},
        {"phone": "123"},
        {"phone": "call-me"},
        {"phone": "-------1234567"},
        {"phone": "+()()()1234567"},
        {"phone": "123(4567"},
        {"phone": "123)4567("},
        {"phone": "+90  (555) 000-0000"},
        {"phone": "+90 (55-5) 000-0000"},
        {"preferred_name": "••••"},
        {"preferred_name": " "},
        {"preferred_name": "Ada\x00Hidden"},
        {"preferred_name": "Ada\x01Hidden"},
        {"preferred_name": "x" * 201},
        {"birth_date": "1992-05-14T12:30:00Z"},
        {"birth_date": "14.05.1992"},
    ],
)
def test_create_rejects_unknown_forbidden_empty_masked_and_malformed_values(
    candidate: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        EmployeeProfileChangeRequestCreate.model_validate(candidate)


def test_decision_payloads_are_strict_and_rejection_reason_is_bounded() -> None:
    payload = EmployeeProfileChangeRequestReject(
        expected_version=2,
        reason="  Belge   gerekli  ",
    )
    assert payload.reason == "Belge gerekli"

    for candidate in (
        {"expected_version": 0, "reason": "no"},
        {"expected_version": 1, "reason": " "},
        {"expected_version": 1, "reason": "x" * 501},
        {"expected_version": 1, "reason": "no", "employee_id": "forbidden"},
        {"expected_version": "1", "reason": "no"},
        {"expected_version": True, "reason": "no"},
        {"expected_version": 1, "reason": "Unsafe\x00Reason"},
    ):
        with pytest.raises(ValidationError):
            EmployeeProfileChangeRequestReject.model_validate(candidate)
