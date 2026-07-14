"""Safe Employee 360 summary and product-activity read contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.employee_profile_change_request import (
    EmployeeProfileChangeRequestStatus,
)
from app.platform.pagination import InvalidCursorError, decode_cursor, encode_cursor

EMPLOYEE_PROFILE_ACTIVITY_DEFAULT_LIMIT = 20
EMPLOYEE_PROFILE_ACTIVITY_MAX_LIMIT = 50
_EMPLOYEE_PROFILE_ACTIVITY_CURSOR_RESOURCE = "employee_profile_activity"


class EmployeeProfileActivityKind(StrEnum):
    """Closed product vocabulary; raw audit event types never cross this boundary."""

    EMPLOYEE_CREATED = "employee.created"
    EMPLOYEE_UPDATED = "employee.updated"
    EMPLOYEE_LIFECYCLE_CHANGED = "employee.lifecycle.changed"
    EMPLOYEE_ARCHIVED = "employee.archived"
    EMPLOYEE_PERSONAL_PROFILE_UPDATED = "employee.personal_profile.updated"
    EMPLOYEE_EMPLOYMENT_PROFILE_UPDATED = "employee.employment_profile.updated"
    EMPLOYEE_ACCOUNT_LINK_CHANGED = "employee.account_link.changed"
    EMPLOYEE_PROFILE_CHANGE_REQUEST_SUBMITTED = (
        "employee.profile_change_request.submitted"
    )
    EMPLOYEE_PROFILE_CHANGE_REQUEST_APPROVED = (
        "employee.profile_change_request.approved"
    )
    EMPLOYEE_PROFILE_CHANGE_REQUEST_REJECTED = (
        "employee.profile_change_request.rejected"
    )
    EMPLOYEE_PROFILE_CHANGE_REQUEST_CANCELLED = (
        "employee.profile_change_request.cancelled"
    )
    EMPLOYEE_ASSIGNMENT_CHANGED = "employee.assignment.changed"
    REPORTING_LINE_CHANGED = "reporting_line.changed"


class EmployeeDocumentsSummaryRead(BaseModel):
    """Stable Phase 5 placeholder; deliberately carries no synthetic document count."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    availability: Literal["unavailable"] = "unavailable"


class EmployeeLeaveSummaryRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    period_year: int = Field(ge=1900, le=2200)
    remaining_balance_days: float
    pending_request_count: int = Field(ge=0)


class EmployeeProfileChangesSummaryRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    submitted_request_count: int = Field(ge=0)
    latest_status: EmployeeProfileChangeRequestStatus | None
    latest_submitted_at: AwareDatetime | None


class EmployeeProfileActivityRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    occurred_at: AwareDatetime
    kind: EmployeeProfileActivityKind


class EmployeeProfileActivityPageRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[EmployeeProfileActivityRead]
    limit: int = Field(ge=1, le=EMPLOYEE_PROFILE_ACTIVITY_MAX_LIMIT)
    next_cursor: str | None


class EmployeeProfileInsightsRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    documents: EmployeeDocumentsSummaryRead
    leave: EmployeeLeaveSummaryRead
    profile_changes: EmployeeProfileChangesSummaryRead
    activity: EmployeeProfileActivityPageRead


class EmployeeProfileActivityCursor(BaseModel):
    """Opaque newest-first continuation key bound to one employee resource."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    occurred_at: AwareDatetime
    id: UUID

    def to_token(self, *, employee_id: UUID) -> str:
        return encode_cursor(
            _cursor_resource(employee_id),
            {
                "occurred_at": self.occurred_at.isoformat(),
                "id": str(self.id),
            },
        )

    @classmethod
    def from_token(cls, token: str, *, employee_id: UUID) -> Self:
        try:
            values = decode_cursor(
                token,
                expected_resource=_cursor_resource(employee_id),
            )
            if set(values) != {"occurred_at", "id"}:
                raise InvalidCursorError
            occurred_at = datetime.fromisoformat(values["occurred_at"])
            if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
                raise InvalidCursorError
            event_id = UUID(values["id"])
            if event_id.int == 0:
                raise InvalidCursorError
            return cls(occurred_at=occurred_at, id=event_id)
        except (InvalidCursorError, KeyError, ValueError) as exc:
            raise InvalidCursorError from exc


def _cursor_resource(employee_id: UUID) -> str:
    return f"{_EMPLOYEE_PROFILE_ACTIVITY_CURSOR_RESOURCE}:{employee_id}"


__all__ = [
    "EMPLOYEE_PROFILE_ACTIVITY_DEFAULT_LIMIT",
    "EMPLOYEE_PROFILE_ACTIVITY_MAX_LIMIT",
    "EmployeeDocumentsSummaryRead",
    "EmployeeLeaveSummaryRead",
    "EmployeeProfileActivityCursor",
    "EmployeeProfileActivityKind",
    "EmployeeProfileActivityPageRead",
    "EmployeeProfileActivityRead",
    "EmployeeProfileChangesSummaryRead",
    "EmployeeProfileInsightsRead",
]
