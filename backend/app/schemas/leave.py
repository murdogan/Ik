"""Closed Phase 6 leave configuration, balance, and workflow contracts."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from re import fullmatch
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.leave_request import LeaveRequestStatus
from app.platform.pagination import decode_cursor, encode_cursor

LEAVE_LIST_DEFAULT_LIMIT = 50
LEAVE_LIST_MAX_LIMIT = 200
LEAVE_CODE_PATTERN = r"[a-z][a-z0-9_]{0,63}"


class LeaveLedgerEntryType(StrEnum):
    EARNED = "earned"
    ADJUSTMENT = "adjustment"
    PLANNED = "planned"
    PLANNED_RELEASE = "planned_release"
    USED = "used"
    USED_RELEASE = "used_release"


class LeaveTimelineEventType(StrEnum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class LeaveAccessScope(StrEnum):
    OWN = "own"
    TEAM = "team"
    TENANT = "tenant"


class LeavePolicyRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    leave_type_id: UUID
    leave_type_code: str
    leave_type_name: str
    version: int = Field(ge=1)
    effective_from: date
    effective_to: date | None = None
    paid: bool
    document_required: bool
    negative_balance_allowed: bool
    accrual_enabled: bool
    accrual_days_per_month: Decimal = Field(ge=0, le=31)
    carryover_enabled: bool
    carryover_limit_days: Decimal | None = Field(default=None, ge=0, le=366)
    created_at: datetime


class LeaveTypeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if fullmatch(LEAVE_CODE_PATTERN, value) is None:
            raise ValueError("Leave type code must be a lowercase identifier")
        return value


class LeaveTypeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_mutation(self) -> Self:
        changed = set(self.model_fields_set) - {"expected_version"}
        if not changed:
            raise ValueError("At least one leave type field must be provided")
        if "name" in changed and self.name is None:
            raise ValueError("name cannot be null")
        if "is_active" in changed and self.is_active is None:
            raise ValueError("is_active cannot be null")
        return self


class LeaveTypeRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    version: int = Field(ge=1)
    current_policy: LeavePolicyRead | None = None
    created_at: datetime
    updated_at: datetime


class HolidayEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    holiday_date: date
    name: str = Field(min_length=1, max_length=200)


class HolidayEntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_mutation(self) -> Self:
        changed = set(self.model_fields_set) - {"expected_version"}
        if not changed:
            raise ValueError("At least one holiday field must be provided")
        if any(getattr(self, field) is None for field in changed):
            raise ValueError("Holiday update fields cannot be null")
        return self


class HolidayEntryRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    holiday_date: date
    name: str
    is_active: bool
    version: int = Field(ge=1)


class HolidayCalendarCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    is_default: bool = False
    non_working_weekdays: list[int] = Field(default_factory=lambda: [5, 6], max_length=7)

    @field_validator("non_working_weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        return _validated_weekdays(value)


class HolidayCalendarUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_default: bool | None = None
    is_active: bool | None = None
    non_working_weekdays: list[int] | None = Field(default=None, max_length=7)

    @field_validator("non_working_weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int] | None) -> list[int] | None:
        return None if value is None else _validated_weekdays(value)

    @model_validator(mode="after")
    def require_mutation(self) -> Self:
        changed = set(self.model_fields_set) - {"expected_version"}
        if not changed:
            raise ValueError("At least one calendar field must be provided")
        if any(getattr(self, field) is None for field in changed):
            raise ValueError("Calendar update fields cannot be null")
        return self


class HolidayCalendarRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    name: str
    is_default: bool
    is_active: bool
    non_working_weekdays: list[int]
    version: int = Field(ge=1)
    entries: list[HolidayEntryRead] = Field(default_factory=list)
    entries_truncated: bool = False
    created_at: datetime
    updated_at: datetime


class LeavePolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leave_type_id: UUID
    effective_from: date
    paid: bool
    document_required: bool
    negative_balance_allowed: bool = False
    accrual_enabled: bool = False
    accrual_days_per_month: Decimal = Field(
        default=Decimal("0"), ge=0, le=31, multiple_of=Decimal("0.01")
    )
    carryover_enabled: bool = False
    carryover_limit_days: Decimal | None = Field(
        default=None, ge=0, le=366, multiple_of=Decimal("0.01")
    )

    @model_validator(mode="after")
    def validate_optional_rules(self) -> Self:
        if not self.accrual_enabled and self.accrual_days_per_month != 0:
            raise ValueError("Accrual rate must be zero while automated accrual is disabled")
        if self.accrual_enabled and self.accrual_days_per_month <= 0:
            raise ValueError("Enabled accrual requires a positive monthly rate")
        if not self.carryover_enabled and self.carryover_limit_days is not None:
            raise ValueError("Carryover limit requires carryover to be enabled")
        return self


class LeaveBalanceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    employee_id: UUID
    period_year: int = Field(ge=1900, le=2200)
    leave_type_id: UUID
    leave_type_code: str
    leave_type_name: str
    leave_type: str
    earned_days: Decimal
    adjusted_days: Decimal
    used_days: Decimal = Field(ge=0)
    planned_days: Decimal = Field(ge=0)
    available_days: Decimal
    negative_balance_allowed: bool
    opening_balance_days: Decimal
    remaining_days: Decimal
    calculation_mode: Literal["ledger"] = "ledger"
    external_integration_enabled: Literal[False] = False


class LeaveLedgerEntryRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    employee_id: UUID
    leave_type_id: UUID
    leave_type_code: str
    leave_type_name: str
    period_year: int = Field(ge=1900, le=2200)
    entry_type: LeaveLedgerEntryType
    amount_days: Decimal
    effective_date: date
    reason: str | None = None
    created_at: datetime


class LeaveAdjustmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    employee_id: UUID
    leave_type_id: UUID
    period_year: int = Field(ge=1900, le=2200)
    amount_days: Decimal = Field(
        ge=Decimal("-3660"),
        le=Decimal("3660"),
        multiple_of=Decimal("0.01"),
    )
    effective_date: date
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("amount_days")
    @classmethod
    def require_non_zero_amount(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("Adjustment amount must not be zero")
        return value

    @model_validator(mode="after")
    def require_matching_period(self) -> Self:
        if self.effective_date.year != self.period_year:
            raise ValueError("Adjustment effective date must belong to period_year")
        return self


class LeaveRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    leave_type_id: UUID
    start_date: date
    end_date: date
    employee_note: str | None = Field(default=None, max_length=1000)
    document_id: UUID | None = None

    @field_validator("employee_note")
    @classmethod
    def reject_blank_note(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("employee_note must not be empty")
        return value

    @model_validator(mode="after")
    def validate_date_order(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("Leave end date must be on or after start date")
        if self.start_date.year < 1900 or self.end_date.year > 2200:
            raise ValueError("Leave dates must fall between years 1900 and 2200")
        return self


class LeaveRequestDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    decision_note: str | None = Field(default=None, max_length=1000)

    @field_validator("decision_note")
    @classmethod
    def reject_blank_note(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("decision_note must not be empty")
        return value


class LeaveRequestTimelineRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    event_type: LeaveTimelineEventType
    status: LeaveRequestStatus
    actor_user_id: UUID
    occurred_at: datetime


class LeaveRequestRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    employee_id: UUID
    employee_name: str
    leave_type_id: UUID
    leave_type: str
    leave_type_code: str
    leave_type_name: str
    policy_id: UUID
    start_date: date
    end_date: date
    counted_days: Decimal = Field(ge=0)
    status: LeaveRequestStatus
    requested_by_user_id: UUID
    decided_by_user_id: UUID | None
    employee_note: str | None
    decision_note: str | None
    has_document: bool
    version: int = Field(ge=1)
    created_at: datetime
    decided_at: datetime | None
    timeline: list[LeaveRequestTimelineRead] = Field(default_factory=list)


class LeaveRequestListCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_at: datetime
    start_date: date
    id: UUID

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Cursor timestamp must include a timezone")
        return value

    @classmethod
    def from_token(cls, token: str) -> LeaveRequestListCursor:
        return cls.model_validate(decode_cursor(token, expected_resource="leave_requests"))

    def to_token(self) -> str:
        return encode_cursor("leave_requests", self.model_dump(mode="json"))


class HolidayEntryListCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    holiday_date: date
    id: UUID

    @classmethod
    def from_token(cls, token: str) -> HolidayEntryListCursor:
        return cls.model_validate(decode_cursor(token, expected_resource="holiday_entries"))

    def to_token(self) -> str:
        return encode_cursor("holiday_entries", self.model_dump(mode="json"))


class LeaveLedgerListCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_at: datetime
    id: UUID

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Cursor timestamp must include a timezone")
        return value

    @classmethod
    def from_token(cls, token: str) -> LeaveLedgerListCursor:
        return cls.model_validate(decode_cursor(token, expected_resource="leave_ledger"))

    def to_token(self) -> str:
        return encode_cursor("leave_ledger", self.model_dump(mode="json"))


class ApprovalTaskListCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_at: datetime
    id: UUID

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Cursor timestamp must include a timezone")
        return value

    @classmethod
    def from_token(cls, token: str) -> ApprovalTaskListCursor:
        return cls.model_validate(decode_cursor(token, expected_resource="approval_tasks"))

    def to_token(self) -> str:
        return encode_cursor("approval_tasks", self.model_dump(mode="json"))


class LeaveRequestListFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: LeaveRequestStatus | None = None
    scope: LeaveAccessScope | None = None
    employee_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_order(self) -> Self:
        if self.start_date is not None and self.end_date is not None:
            if self.end_date < self.start_date:
                raise ValueError("Leave request end_date filter must be on or after start_date")
        return self


class LeaveListPagination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=LEAVE_LIST_DEFAULT_LIMIT, ge=1, le=LEAVE_LIST_MAX_LIMIT)
    cursor: LeaveRequestListCursor | LeaveLedgerListCursor | None = None


class ApprovalTaskRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    request: LeaveRequestRead
    available_days: Decimal
    manager_context: str | None = None


class TeamCalendarEntryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    request_id: UUID
    employee_id: UUID
    employee_name: str
    leave_type_code: str
    leave_type_name: str
    start_date: date
    end_date: date
    counted_days: Decimal = Field(ge=0)
    status: Literal["approved"] = "approved"


def _validated_weekdays(value: list[int]) -> list[int]:
    if len(set(value)) != len(value):
        raise ValueError("Non-working weekdays must be unique")
    if any(type(item) is not int or item < 0 or item > 6 for item in value):
        raise ValueError("Weekdays must use 0=Monday through 6=Sunday")
    if len(value) == 7:
        raise ValueError("A workweek must contain at least one working weekday")
    return sorted(value)


__all__ = [
    "ApprovalTaskRead",
    "ApprovalTaskListCursor",
    "HolidayCalendarCreate",
    "HolidayCalendarRead",
    "HolidayCalendarUpdate",
    "HolidayEntryCreate",
    "HolidayEntryListCursor",
    "HolidayEntryRead",
    "HolidayEntryUpdate",
    "LEAVE_LIST_DEFAULT_LIMIT",
    "LEAVE_LIST_MAX_LIMIT",
    "LeaveAccessScope",
    "LeaveAdjustmentCreate",
    "LeaveBalanceRead",
    "LeaveLedgerEntryRead",
    "LeaveLedgerEntryType",
    "LeaveLedgerListCursor",
    "LeaveListPagination",
    "LeavePolicyCreate",
    "LeavePolicyRead",
    "LeaveRequestCreate",
    "LeaveRequestDecision",
    "LeaveRequestListCursor",
    "LeaveRequestListFilters",
    "LeaveRequestRead",
    "LeaveRequestTimelineRead",
    "LeaveTimelineEventType",
    "LeaveTypeCreate",
    "LeaveTypeRead",
    "LeaveTypeUpdate",
    "TeamCalendarEntryRead",
]
