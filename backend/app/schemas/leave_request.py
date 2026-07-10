from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.error_messages import (
    LEAVE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE,
    LEAVE_REQUEST_FILTER_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE,
)
from app.models.leave_request import LeaveRequestStatus
from app.schemas.date_fields import DateOnly

LEAVE_REQUEST_LIST_DEFAULT_LIMIT = 50
LEAVE_REQUEST_LIST_MAX_LIMIT = 200


class LeaveRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    employee_id: UUID
    leave_type: str = Field(min_length=1, max_length=64)
    start_date: DateOnly
    end_date: DateOnly
    requested_by_user_id: UUID

    @field_validator("leave_type")
    @classmethod
    def require_non_empty_leave_type(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Leave type must not be empty")
        return value

    @model_validator(mode="after")
    def validate_date_order(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError(LEAVE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE)
        return self


class LeaveRequestDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decided_by_user_id: UUID
    decision_note: str | None = None

    @field_validator("decision_note")
    @classmethod
    def reject_empty_note_when_provided(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Decision note must not be empty")
        return value


class LeaveRequestListFilters(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    status: LeaveRequestStatus | None = None
    employee_id: UUID | None = None
    start_date: DateOnly | None = None
    end_date: DateOnly | None = None

    @model_validator(mode="after")
    def validate_date_range_when_complete(self) -> Self:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError(LEAVE_REQUEST_FILTER_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE)
        return self


class LeaveRequestListPagination(BaseModel):
    limit: int = Field(
        default=LEAVE_REQUEST_LIST_DEFAULT_LIMIT,
        ge=1,
        le=LEAVE_REQUEST_LIST_MAX_LIMIT,
    )
    offset: int = Field(default=0, ge=0)


class LeaveRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    leave_type: str
    start_date: DateOnly
    end_date: DateOnly
    status: LeaveRequestStatus
    requested_by_user_id: UUID
    decided_by_user_id: UUID | None
    decision_note: str | None
