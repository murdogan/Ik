from datetime import date, datetime
from re import Pattern, compile
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.error_messages import (
    EMPLOYEE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE,
    EMPLOYEE_END_DATE_ONLY_FOR_TERMINATED_MESSAGE,
    EMPLOYEE_START_DATE_MUST_NOT_BE_NULL_MESSAGE,
    EMPLOYEE_STATUS_MUST_NOT_BE_NULL_MESSAGE,
    EMPLOYEE_TERMINATED_REQUIRES_END_DATE_MESSAGE,
)
from app.models.employee import EmployeeStatus
from app.platform.pagination import decode_cursor, encode_cursor
from app.schemas.date_fields import DateOnly

EMAIL_PATTERN: Pattern[str] = compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMPLOYEE_LIST_DEFAULT_LIMIT = 50
EMPLOYEE_LIST_MAX_LIMIT = 200


class EmployeeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    employee_number: str = Field(min_length=1, max_length=64)
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: str | None = Field(default=None, max_length=320)
    department: str | None = None
    position: str | None = None
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    employment_start_date: DateOnly
    employment_end_date: DateOnly | None = None

    @field_validator("employee_number", "first_name", "last_name")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Field must not be empty")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("Email must not be empty")
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Email format is invalid")
        return value

    @model_validator(mode="after")
    def validate_date_order(self) -> Self:
        if (
            self.employment_end_date is not None
            and self.employment_end_date < self.employment_start_date
        ):
            raise ValueError(EMPLOYEE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE)
        _validate_lifecycle_status_end_date(self.status, self.employment_end_date)
        return self


class EmployeeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    employee_number: str | None = Field(default=None, min_length=1, max_length=64)
    first_name: str | None = Field(default=None, min_length=1)
    last_name: str | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, max_length=320)
    department: str | None = None
    position: str | None = None
    status: EmployeeStatus | None = None
    employment_start_date: DateOnly | None = None
    employment_end_date: DateOnly | None = None
    version: int | None = Field(default=None, ge=1)

    @field_validator("employee_number", "first_name", "last_name")
    @classmethod
    def require_non_empty_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Field must not be empty")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("Email must not be empty")
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Email format is invalid")
        return value

    @model_validator(mode="after")
    def validate_date_order_when_complete(self) -> Self:
        fields_set = self.model_fields_set
        if "employment_start_date" in fields_set and self.employment_start_date is None:
            raise ValueError(EMPLOYEE_START_DATE_MUST_NOT_BE_NULL_MESSAGE)
        if (
            self.employment_start_date is not None
            and self.employment_end_date is not None
            and self.employment_end_date < self.employment_start_date
        ):
            raise ValueError(EMPLOYEE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE)
        if "status" in fields_set and self.status is None:
            raise ValueError(EMPLOYEE_STATUS_MUST_NOT_BE_NULL_MESSAGE)
        if "version" in fields_set and self.version is None:
            raise ValueError("Version must not be null")
        if "status" in fields_set and "employment_end_date" in fields_set:
            _validate_lifecycle_status_end_date(self.status, self.employment_end_date)
        return self


class EmployeeListFilters(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    department: str | None = None
    status: EmployeeStatus | None = None
    q: str | None = Field(default=None, max_length=320)
    legal_entity_id: UUID | None = None
    branch_id: UUID | None = None
    department_id: UUID | None = None
    position_id: UUID | None = None

    @field_validator("department", "q")
    @classmethod
    def empty_text_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value or None


class EmployeeListCursor(BaseModel):
    """Opaque employee continuation key for immutable creation order."""

    model_config = ConfigDict(extra="forbid")

    created_at: datetime
    id: UUID

    @field_validator("created_at")
    @classmethod
    def require_timezone_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Employee cursor created_at must include a timezone")
        return value

    @classmethod
    def from_token(cls, token: str) -> "EmployeeListCursor":
        return cls.model_validate(decode_cursor(token, expected_resource="employees"))

    def to_token(self) -> str:
        return encode_cursor("employees", self.model_dump(mode="json"))


class EmployeeListPagination(BaseModel):
    limit: int = Field(
        default=EMPLOYEE_LIST_DEFAULT_LIMIT,
        ge=1,
        le=EMPLOYEE_LIST_MAX_LIMIT,
    )
    offset: int = Field(default=0, ge=0)
    cursor: EmployeeListCursor | None = None

    @model_validator(mode="after")
    def reject_cursor_with_positive_offset(self) -> Self:
        if self.cursor is not None and self.offset > 0:
            raise ValueError("Cursor pagination requires offset=0")
        return self


class EmployeeOrganizationReferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    code: str
    name: str


class EmployeePositionReferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    code: str
    title: str


class EmployeeCurrentAssignmentRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    legal_entity: EmployeeOrganizationReferenceRead
    branch: EmployeeOrganizationReferenceRead
    department: EmployeeOrganizationReferenceRead
    position: EmployeePositionReferenceRead
    effective_from: DateOnly


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_number: str
    first_name: str
    last_name: str
    email: str | None
    department: str | None
    position: str | None
    status: EmployeeStatus
    employment_start_date: DateOnly
    employment_end_date: DateOnly | None
    version: int = Field(default=1, ge=1)
    current_assignment: EmployeeCurrentAssignmentRead | None = None

    @model_validator(mode="after")
    def validate_lifecycle_status_end_date(self) -> Self:
        _validate_lifecycle_status_end_date(self.status, self.employment_end_date)
        return self


def _validate_lifecycle_status_end_date(
    status: EmployeeStatus | None,
    employment_end_date: date | None,
) -> None:
    if status == EmployeeStatus.TERMINATED:
        if employment_end_date is None:
            raise ValueError(EMPLOYEE_TERMINATED_REQUIRES_END_DATE_MESSAGE)
        return

    if employment_end_date is not None:
        raise ValueError(EMPLOYEE_END_DATE_ONLY_FOR_TERMINATED_MESSAGE)
