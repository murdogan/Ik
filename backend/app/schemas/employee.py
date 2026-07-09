from datetime import date
from re import Pattern, compile
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.employee import EmployeeStatus

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
    employment_start_date: date
    employment_end_date: date | None = None

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
            raise ValueError("Employment end date must be on or after start date")
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
    employment_start_date: date | None = None
    employment_end_date: date | None = None

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
        if (
            self.employment_start_date is not None
            and self.employment_end_date is not None
            and self.employment_end_date < self.employment_start_date
        ):
            raise ValueError("Employment end date must be on or after start date")
        return self


class EmployeeListFilters(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    department: str | None = None
    status: EmployeeStatus | None = None
    q: str | None = Field(default=None, max_length=320)

    @field_validator("department", "q")
    @classmethod
    def empty_text_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value or None


class EmployeeListPagination(BaseModel):
    limit: int = Field(
        default=EMPLOYEE_LIST_DEFAULT_LIMIT,
        ge=1,
        le=EMPLOYEE_LIST_MAX_LIMIT,
    )
    offset: int = Field(default=0, ge=0)


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
    employment_start_date: date
    employment_end_date: date | None
