from datetime import date
from uuid import UUID

import pytest
from app.schemas.employee_account_link import (
    EmployeeAccountLinkUpdate,
    OwnEmployeeEmploymentProfileRead,
    OwnEmployeeOrganizationRead,
    OwnEmployeePersonalProfileRead,
    OwnEmployeeProfileCoreRead,
    OwnEmployeeProfileRead,
    OwnEmployeeProfileStateRead,
)
from pydantic import ValidationError

MEMBERSHIP_ID = UUID("11111111-1111-4111-8111-111111111111")
EMPLOYEE_ID = UUID("22222222-2222-4222-8222-222222222222")


def test_account_link_patch_is_strict_and_requires_both_nullable_command_fields() -> None:
    linked = EmployeeAccountLinkUpdate(
        membership_id=MEMBERSHIP_ID,
        expected_version=None,
    )
    unlinked = EmployeeAccountLinkUpdate(membership_id=None, expected_version=2)
    assert linked.membership_id == MEMBERSHIP_ID
    assert unlinked.expected_version == 2

    for invalid in (
        {"membership_id": str(MEMBERSHIP_ID)},
        {"expected_version": None},
        {"membership_id": None, "expected_version": 0},
        {
            "membership_id": str(MEMBERSHIP_ID),
            "expected_version": None,
            "employee_id": str(EMPLOYEE_ID),
        },
    ):
        with pytest.raises(ValidationError):
            EmployeeAccountLinkUpdate.model_validate(invalid)


def test_own_profile_contract_is_allowlisted_and_unavailable_state_leaks_no_ids() -> None:
    unavailable = OwnEmployeeProfileStateRead(
        availability="unavailable",
        employee_id=None,
        profile=None,
    )
    assert unavailable.model_dump() == {
        "availability": "unavailable",
        "employee_id": None,
        "profile": None,
    }

    profile = OwnEmployeeProfileRead(
        core=OwnEmployeeProfileCoreRead(
            id=EMPLOYEE_ID,
            employee_number="WF-1",
            first_name="Ada",
            last_name="Yilmaz",
            email="ada@example.test",
            status="active",
        ),
        personal=OwnEmployeePersonalProfileRead(
            preferred_name="Ada",
            birth_date={"visibility": "masked", "display_value": "••••-05-14"},
            phone={"visibility": "masked", "display_value": "••••••••00"},
        ),
        employment=OwnEmployeeEmploymentProfileRead(
            employment_start_date=date(2026, 7, 1),
            contract_type="indefinite",
            work_type="full_time",
        ),
        organization=OwnEmployeeOrganizationRead(current_assignment=None),
    )
    dumped = profile.model_dump(mode="json")
    serialized = repr(dumped).lower()
    assert "1992-05-14" not in serialized
    assert "+90 555 000 0000" not in serialized
    for forbidden in (
        "version",
        "history",
        "audit",
        "salary",
        "identity_id",
        "membership_id",
        "manager_user_id",
    ):
        assert forbidden not in serialized

    with pytest.raises(ValidationError):
        OwnEmployeeProfileStateRead(
            availability="unavailable",
            employee_id=EMPLOYEE_ID,
            profile=None,
        )
