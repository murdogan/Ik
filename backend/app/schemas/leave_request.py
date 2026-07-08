from datetime import date
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.leave_request import LeaveRequestStatus


class LeaveRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    employee_id: UUID
    leave_type: str = Field(min_length=1, max_length=64)
    start_date: date
    end_date: date
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
            raise ValueError("Leave end date must be on or after start date")
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


class LeaveRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    leave_type: str
    start_date: date
    end_date: date
    status: LeaveRequestStatus
    requested_by_user_id: UUID
    decided_by_user_id: UUID | None
    decision_note: str | None
