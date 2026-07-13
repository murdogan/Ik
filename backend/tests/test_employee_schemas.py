from datetime import date, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from app.models.employee import EmployeeStatus
from app.platform.pagination import InvalidCursorError, encode_cursor
from app.schemas.employee import (
    EMPLOYEE_LIST_DEFAULT_LIMIT,
    EMPLOYEE_LIST_MAX_LIMIT,
    EmployeeCreate,
    EmployeeListCursor,
    EmployeeListFilters,
    EmployeeListPagination,
    EmployeeRead,
    EmployeeUpdate,
)
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


def test_employee_create_requires_end_date_when_status_is_terminated() -> None:
    with pytest.raises(ValidationError):
        EmployeeCreate(
            employee_number="WF-001",
            first_name="Ada",
            last_name="Yilmaz",
            status=EmployeeStatus.TERMINATED,
            employment_start_date=date(2026, 7, 1),
        )


@pytest.mark.parametrize("status", [EmployeeStatus.ACTIVE, EmployeeStatus.ON_LEAVE])
def test_employee_create_rejects_end_date_for_non_terminated_status(
    status: EmployeeStatus,
) -> None:
    with pytest.raises(ValidationError):
        EmployeeCreate(
            employee_number="WF-001",
            first_name="Ada",
            last_name="Yilmaz",
            status=status,
            employment_start_date=date(2026, 7, 1),
            employment_end_date=date(2026, 7, 10),
        )


def test_employee_create_allows_same_day_start_and_end_dates() -> None:
    payload = EmployeeCreate(
        employee_number="WF-001",
        first_name="Ada",
        last_name="Yilmaz",
        status=EmployeeStatus.TERMINATED,
        employment_start_date=date(2026, 7, 1),
        employment_end_date=date(2026, 7, 1),
    )

    assert payload.employment_end_date == payload.employment_start_date
    assert payload.status == EmployeeStatus.TERMINATED


@pytest.mark.parametrize("value", ["20260701", "2026-W27-3", "2026-02-30"])
def test_employee_create_rejects_non_full_date_strings(value: str) -> None:
    with pytest.raises(ValidationError):
        EmployeeCreate(
            employee_number="WF-001",
            first_name="Ada",
            last_name="Yilmaz",
            employment_start_date=value,
        )


@pytest.mark.parametrize("field", ["employment_start_date", "employment_end_date"])
def test_employee_create_rejects_datetime_strings_for_date_fields(field: str) -> None:
    data = {
        "employee_number": "WF-001",
        "first_name": "Ada",
        "last_name": "Yilmaz",
        "employment_start_date": "2026-07-01",
        "employment_end_date": "2026-07-02",
    }
    data[field] = "2026-07-01T00:00:00"

    with pytest.raises(ValidationError):
        EmployeeCreate(**data)


@pytest.mark.parametrize("field", ["employment_start_date", "employment_end_date"])
def test_employee_create_rejects_numeric_date_values(field: str) -> None:
    data = {
        "employee_number": "WF-001",
        "first_name": "Ada",
        "last_name": "Yilmaz",
        "status": EmployeeStatus.TERMINATED,
        "employment_start_date": "2026-07-01",
        "employment_end_date": "2026-07-02",
    }
    data[field] = 0

    with pytest.raises(ValidationError):
        EmployeeCreate(**data)


def test_employee_update_allows_partial_payload_and_null_email() -> None:
    payload = EmployeeUpdate(first_name=" Ada ", email=None)

    assert payload.model_dump(exclude_unset=True) == {
        "first_name": "Ada",
        "email": None,
    }


def test_employee_update_accepts_positive_expected_version() -> None:
    payload = EmployeeUpdate(version=3, position="People Lead")

    assert payload.model_dump(exclude_unset=True) == {
        "position": "People Lead",
        "version": 3,
    }


@pytest.mark.parametrize("value", [None, 0, -1])
def test_employee_update_rejects_invalid_explicit_version(value: int | None) -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdate(version=value)


def test_employee_update_rejects_end_date_before_start_date_when_both_provided() -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdate(
            employment_start_date=date(2026, 7, 10),
            employment_end_date=date(2026, 7, 1),
        )


def test_employee_update_rejects_explicit_null_start_date() -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdate(employment_start_date=None)


@pytest.mark.parametrize("value", ["20260701", "2026-W27-3", "2026-02-30"])
def test_employee_update_rejects_non_full_date_strings(value: str) -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdate(employment_start_date=value)


def test_employee_update_rejects_explicit_null_status() -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdate(status=None)


@pytest.mark.parametrize("status", [EmployeeStatus.ACTIVE, EmployeeStatus.ON_LEAVE])
def test_employee_update_rejects_end_date_for_non_terminated_status(
    status: EmployeeStatus,
) -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdate(status=status, employment_end_date=date(2026, 7, 10))


def test_employee_update_rejects_terminated_status_with_explicit_null_end_date() -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdate(status=EmployeeStatus.TERMINATED, employment_end_date=None)


@pytest.mark.parametrize("status", [EmployeeStatus.ACTIVE, EmployeeStatus.ON_LEAVE])
def test_employee_update_allows_non_terminated_status_with_explicit_null_end_date(
    status: EmployeeStatus,
) -> None:
    payload = EmployeeUpdate(status=status, employment_end_date=None)

    assert payload.status == status
    assert payload.employment_end_date is None


def test_employee_update_allows_terminated_status_without_end_date_in_partial_payload() -> None:
    payload = EmployeeUpdate(status=EmployeeStatus.TERMINATED)

    assert payload.status == EmployeeStatus.TERMINATED


def test_employee_update_rejects_datetime_objects_for_date_fields() -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdate(employment_start_date=datetime(2026, 7, 1))


@pytest.mark.parametrize("field", ["employment_start_date", "employment_end_date"])
def test_employee_update_rejects_numeric_date_values(field: str) -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdate(**{field: 0})


def test_employee_update_rejects_empty_name_when_provided() -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdate(last_name=" ")


def test_employee_list_filters_strip_text_and_convert_empty_values_to_none() -> None:
    payload = EmployeeListFilters(
        department=" People ",
        status=EmployeeStatus.ON_LEAVE,
        q=" ",
    )

    assert payload.department == "People"
    assert payload.status == EmployeeStatus.ON_LEAVE
    assert payload.q is None


def test_employee_list_filters_accept_structured_assignment_ids() -> None:
    legal_entity_id = UUID("11111111-1111-4111-8111-111111111111")
    branch_id = UUID("22222222-2222-4222-8222-222222222222")
    department_id = UUID("33333333-3333-4333-8333-333333333333")
    position_id = UUID("44444444-4444-4444-8444-444444444444")

    payload = EmployeeListFilters(
        legal_entity_id=legal_entity_id,
        branch_id=branch_id,
        department_id=department_id,
        position_id=position_id,
    )

    assert payload.model_dump() == {
        "department": None,
        "status": None,
        "q": None,
        "legal_entity_id": legal_entity_id,
        "branch_id": branch_id,
        "department_id": department_id,
        "position_id": position_id,
    }


def test_employee_list_pagination_has_bounded_defaults() -> None:
    payload = EmployeeListPagination()

    assert payload.limit == EMPLOYEE_LIST_DEFAULT_LIMIT
    assert payload.offset == 0


@pytest.mark.parametrize(
    "data",
    [
        {"limit": 0},
        {"limit": EMPLOYEE_LIST_MAX_LIMIT + 1},
        {"offset": -1},
    ],
)
def test_employee_list_pagination_rejects_unbounded_values(data: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        EmployeeListPagination(**data)


def test_employee_list_pagination_rejects_cursor_with_positive_offset() -> None:
    cursor = EmployeeListCursor(
        id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    )

    with pytest.raises(ValidationError):
        EmployeeListPagination(offset=1, cursor=cursor)


def test_employee_list_cursor_round_trips_immutable_id_key_opaquely() -> None:
    cursor = EmployeeListCursor(
        id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    )

    token = cursor.to_token()

    assert EmployeeListCursor.from_token(token) == cursor
    assert str(cursor.id) not in token


def test_employee_list_cursor_rejects_legacy_created_at_token() -> None:
    token = encode_cursor(
        "employees",
        {
            "created_at": "2026-07-13T09:00:00.000001Z",
            "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        },
    )

    with pytest.raises(ValidationError):
        EmployeeListCursor.from_token(token)


def test_employee_list_cursor_rejects_legacy_mutable_employee_number_token() -> None:
    token = encode_cursor(
        "employees",
        {
            "employee_number": "WF-001",
            "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        },
    )

    with pytest.raises(ValidationError):
        EmployeeListCursor.from_token(token)


def test_employee_list_cursor_rejects_token_for_another_resource() -> None:
    token = encode_cursor(
        "leave_requests",
        {
            "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        },
    )

    with pytest.raises(InvalidCursorError):
        EmployeeListCursor.from_token(token)


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
        version=4,
    )

    assert "tenant_id" not in payload.model_dump()
    assert payload.version == 4


def test_employee_read_accepts_model_lifecycle_status_string() -> None:
    payload = EmployeeRead.model_validate(
        SimpleNamespace(
            id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            employee_number="WF-001",
            first_name="Ada",
            last_name="Yilmaz",
            email=None,
            department="People",
            position="HR Specialist",
            status=EmployeeStatus.TERMINATED.value,
            employment_start_date=date(2026, 7, 1),
            employment_end_date=date(2026, 7, 31),
        )
    )

    assert payload.status == EmployeeStatus.TERMINATED
    assert payload.employment_end_date == date(2026, 7, 31)


def test_employee_read_exposes_current_structured_assignment_summary() -> None:
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
        version=1,
        current_assignment={
            "id": "55555555-5555-4555-8555-555555555555",
            "legal_entity": {
                "id": "11111111-1111-4111-8111-111111111111",
                "code": "WF",
                "name": "Wealthy Falcon",
            },
            "branch": {
                "id": "22222222-2222-4222-8222-222222222222",
                "code": "HQ",
                "name": "Merkez",
            },
            "department": {
                "id": "33333333-3333-4333-8333-333333333333",
                "code": "PEOPLE",
                "name": "People",
            },
            "position": {
                "id": "44444444-4444-4444-8444-444444444444",
                "code": "HR",
                "title": "HR Specialist",
            },
            "effective_from": "2026-07-01",
        },
    )

    assert payload.current_assignment is not None
    assert payload.current_assignment.department.name == "People"
    assert payload.current_assignment.position.title == "HR Specialist"


def test_employee_read_rejects_terminated_status_without_end_date() -> None:
    with pytest.raises(ValidationError):
        EmployeeRead(
            id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            employee_number="WF-001",
            first_name="Ada",
            last_name="Yilmaz",
            email=None,
            department="People",
            position="HR Specialist",
            status=EmployeeStatus.TERMINATED,
            employment_start_date=date(2026, 7, 1),
            employment_end_date=None,
        )


@pytest.mark.parametrize("status", [EmployeeStatus.ACTIVE, EmployeeStatus.ON_LEAVE])
def test_employee_read_rejects_end_date_for_current_statuses(
    status: EmployeeStatus,
) -> None:
    with pytest.raises(ValidationError):
        EmployeeRead(
            id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            employee_number="WF-001",
            first_name="Ada",
            last_name="Yilmaz",
            email=None,
            department="People",
            position="HR Specialist",
            status=status,
            employment_start_date=date(2026, 7, 1),
            employment_end_date=date(2026, 7, 31),
        )
