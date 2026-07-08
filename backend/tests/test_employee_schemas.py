from datetime import date
from uuid import UUID

import pytest
from app.models.employee import EmployeeStatus
from app.schemas.employee import EmployeeCreate, EmployeeRead, EmployeeUpdate
from pydantic import ValidationError


def test_employee_create_accepts_minimal_valid_payload() -> None:
    payload = EmployeeCreate(
        employee_number=" WF-001 ",
        first_name=" Ada ",
        last_name=" Yilmaz ",
        employment_start_date=date(2026, 7, 1),
    )

    assert payload.employee_number == "WF-001"
    assert payload.first_name == "Ada"
    assert payload.last_name == "Yilmaz"
    assert payload.status == EmployeeStatus.ACTIVE
    assert payload.email is None


@pytest.mark.parametrize("field", ["employee_number", "first_name", "last_name"])
def test_employee_create_rejects_empty_required_text(field: str) -> None:
    data = {
        "employee_number": "WF-001",
        "first_name": "Ada",
        "last_name": "Yilmaz",
        "employment_start_date": date(2026, 7, 1),
    }
    data[field] = " "

    with pytest.raises(ValidationError):
        EmployeeCreate(**data)


def test_employee_create_rejects_invalid_email_format() -> None:
    with pytest.raises(ValidationError):
        EmployeeCreate(
            employee_number="WF-001",
            first_name="Ada",
            last_name="Yilmaz",
            email="not-an-email",
            employment_start_date=date(2026, 7, 1),
        )


def test_employee_create_rejects_client_controlled_tenant_id() -> None:
    with pytest.raises(ValidationError):
        EmployeeCreate(
            employee_number="WF-001",
            first_name="Ada",
            last_name="Yilmaz",
            employment_start_date=date(2026, 7, 1),
            tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
        )


def test_employee_create_rejects_end_date_before_start_date() -> None:
    with pytest.raises(ValidationError):
        EmployeeCreate(
            employee_number="WF-001",
            first_name="Ada",
            last_name="Yilmaz",
            employment_start_date=date(2026, 7, 10),
            employment_end_date=date(2026, 7, 1),
        )


def test_employee_update_allows_partial_payload_and_null_email() -> None:
    payload = EmployeeUpdate(first_name=" Ada ", email=None)

    assert payload.model_dump(exclude_unset=True) == {
        "first_name": "Ada",
        "email": None,
    }


def test_employee_update_rejects_empty_name_when_provided() -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdate(last_name=" ")


def test_employee_read_does_not_expose_tenant_id() -> None:
    payload = EmployeeRead(
        id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        employee_number="WF-001",
        first_name="Ada",
        last_name="Yilmaz",
        email="ada@example.com",
        department="People",
        position="HR Specialist",
        status=EmployeeStatus.ACTIVE,
        employment_start_date=date(2026, 7, 1),
        employment_end_date=None,
    )

    assert "tenant_id" not in payload.model_dump()
