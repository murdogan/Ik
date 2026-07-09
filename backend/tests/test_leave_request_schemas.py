from datetime import date
from uuid import UUID

import pytest
from app.models.leave_request import LeaveRequestStatus
from app.schemas.leave_request import (
    LEAVE_REQUEST_LIST_DEFAULT_LIMIT,
    LEAVE_REQUEST_LIST_MAX_LIMIT,
    LeaveRequestCreate,
    LeaveRequestDecision,
    LeaveRequestListFilters,
    LeaveRequestListPagination,
    LeaveRequestRead,
)
from pydantic import ValidationError

EMPLOYEE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
REQUESTING_USER_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
DECIDING_USER_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


def test_leave_request_create_accepts_minimal_pending_request_payload() -> None:
    payload = LeaveRequestCreate(
        employee_id=EMPLOYEE_ID,
        leave_type=" annual ",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 22),
        requested_by_user_id=REQUESTING_USER_ID,
    )

    assert payload.leave_type == "annual"
    assert "status" not in payload.model_dump()


def test_leave_request_create_rejects_client_controlled_status() -> None:
    with pytest.raises(ValidationError):
        LeaveRequestCreate(
            employee_id=EMPLOYEE_ID,
            leave_type="annual",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 22),
            requested_by_user_id=REQUESTING_USER_ID,
            status=LeaveRequestStatus.APPROVED,
        )


def test_leave_request_create_rejects_empty_leave_type() -> None:
    with pytest.raises(ValidationError):
        LeaveRequestCreate(
            employee_id=EMPLOYEE_ID,
            leave_type=" ",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 22),
            requested_by_user_id=REQUESTING_USER_ID,
        )


def test_leave_request_create_rejects_end_date_before_start_date() -> None:
    with pytest.raises(ValidationError):
        LeaveRequestCreate(
            employee_id=EMPLOYEE_ID,
            leave_type="annual",
            start_date=date(2026, 7, 22),
            end_date=date(2026, 7, 20),
            requested_by_user_id=REQUESTING_USER_ID,
        )


def test_leave_request_create_allows_same_day_start_and_end_dates() -> None:
    payload = LeaveRequestCreate(
        employee_id=EMPLOYEE_ID,
        leave_type="sick",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 20),
        requested_by_user_id=REQUESTING_USER_ID,
    )

    assert payload.end_date == payload.start_date


@pytest.mark.parametrize("field", ["start_date", "end_date"])
def test_leave_request_create_rejects_datetime_strings_for_date_fields(field: str) -> None:
    data = {
        "employee_id": EMPLOYEE_ID,
        "leave_type": "annual",
        "start_date": "2026-07-20",
        "end_date": "2026-07-22",
        "requested_by_user_id": REQUESTING_USER_ID,
    }
    data[field] = "2026-07-20T00:00:00"

    with pytest.raises(ValidationError):
        LeaveRequestCreate(**data)


def test_leave_request_decision_accepts_optional_note() -> None:
    payload = LeaveRequestDecision(
        decided_by_user_id=DECIDING_USER_ID,
        decision_note=" coverage planned ",
    )

    assert payload.decision_note == "coverage planned"


def test_leave_request_decision_rejects_empty_note_when_provided() -> None:
    with pytest.raises(ValidationError):
        LeaveRequestDecision(decided_by_user_id=DECIDING_USER_ID, decision_note=" ")


def test_leave_request_list_filters_accept_supported_query_fields() -> None:
    filters = LeaveRequestListFilters(
        status=LeaveRequestStatus.APPROVED,
        employee_id=EMPLOYEE_ID,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
    )

    assert filters.status == LeaveRequestStatus.APPROVED
    assert filters.employee_id == EMPLOYEE_ID


def test_leave_request_list_filters_reject_invalid_date_range() -> None:
    with pytest.raises(ValidationError):
        LeaveRequestListFilters(
            start_date=date(2026, 7, 31),
            end_date=date(2026, 7, 1),
        )


def test_leave_request_list_filters_reject_datetime_strings_for_date_fields() -> None:
    with pytest.raises(ValidationError):
        LeaveRequestListFilters(
            start_date="2026-07-01T00:00:00",
            end_date="2026-07-31",
        )


def test_leave_request_list_pagination_has_bounded_defaults() -> None:
    payload = LeaveRequestListPagination()

    assert payload.limit == LEAVE_REQUEST_LIST_DEFAULT_LIMIT
    assert payload.offset == 0


@pytest.mark.parametrize(
    "data",
    [
        {"limit": 0},
        {"limit": LEAVE_REQUEST_LIST_MAX_LIMIT + 1},
        {"offset": -1},
    ],
)
def test_leave_request_list_pagination_rejects_unbounded_values(data: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        LeaveRequestListPagination(**data)


def test_leave_request_read_exposes_workflow_fields_without_tenant_id() -> None:
    payload = LeaveRequestRead(
        id=UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
        employee_id=EMPLOYEE_ID,
        leave_type="annual",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 22),
        status=LeaveRequestStatus.PENDING,
        requested_by_user_id=REQUESTING_USER_ID,
        decided_by_user_id=None,
        decision_note=None,
    )

    data = payload.model_dump()
    assert data["status"] == LeaveRequestStatus.PENDING
    assert "tenant_id" not in data
