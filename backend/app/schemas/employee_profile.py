"""Focused Employee 360 contracts for personal, employment, and organization data."""

from __future__ import annotations

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.employee import EmployeeStatus
from app.schemas.date_fields import DateOnly
from app.schemas.employee import EMAIL_PATTERN
from app.schemas.employee_assignment import EmployeeAssignmentRead

EMPLOYEE_PROFILE_HISTORY_LIMIT = 50


class EmployeeContractType(StrEnum):
    INDEFINITE = "indefinite"
    FIXED_TERM = "fixed_term"


class EmployeeWorkType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"


class EmployeeProfileCoreRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    employee_number: str
    first_name: str
    last_name: str
    email: str | None
    status: EmployeeStatus
    employee_version: int = Field(ge=1)


class EmployeePersonalProfileRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    preferred_name: str | None
    birth_date: DateOnly | None
    phone: str | None
    version: int = Field(ge=1)


class EmployeeEmploymentProfileRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    employment_start_date: DateOnly
    contract_type: EmployeeContractType | None
    work_type: EmployeeWorkType | None
    version: int = Field(ge=1)


class EmployeeProfileOrganizationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_assignment: EmployeeAssignmentRead | None
    history: list[EmployeeAssignmentRead]
    history_limit: int = Field(default=EMPLOYEE_PROFILE_HISTORY_LIMIT, ge=1, le=100)
    history_truncated: bool


class EmployeeProfileRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core: EmployeeProfileCoreRead
    personal: EmployeePersonalProfileRead
    employment: EmployeeEmploymentProfileRead
    organization: EmployeeProfileOrganizationRead


class EmployeePersonalProfileMutationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core: EmployeeProfileCoreRead
    personal: EmployeePersonalProfileRead


class EmployeeEmploymentProfileMutationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core: EmployeeProfileCoreRead
    employment: EmployeeEmploymentProfileRead


class _EmployeeProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    expected_employee_version: int | None = Field(default=None, ge=1)

    def _require_mutation(self, mutable_fields: frozenset[str]) -> None:
        if not self.model_fields_set.intersection(mutable_fields):
            raise ValueError("At least one profile field must be provided")

    def _require_employee_version(self, core_fields: frozenset[str]) -> None:
        if (
            self.model_fields_set.intersection(core_fields)
            and self.expected_employee_version is None
        ):
            raise ValueError("expected_employee_version is required for core employee fields")


class EmployeePersonalProfileUpdate(_EmployeeProfileUpdate):
    first_name: str | None = Field(default=None, min_length=1, max_length=200)
    last_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    preferred_name: str | None = Field(default=None, min_length=1, max_length=200)
    birth_date: DateOnly | None = None
    phone: str | None = Field(default=None, min_length=1, max_length=32)

    @field_validator("first_name", "last_name")
    @classmethod
    def reject_null_core_names(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Core employee names cannot be null")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None and not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Email format is invalid")
        return value

    @model_validator(mode="after")
    def validate_update_shape(self) -> Self:
        mutable_fields = frozenset(
            {
                "first_name",
                "last_name",
                "email",
                "preferred_name",
                "birth_date",
                "phone",
            }
        )
        self._require_mutation(mutable_fields)
        self._require_employee_version(frozenset({"first_name", "last_name", "email"}))
        return self


class EmployeeEmploymentProfileUpdate(_EmployeeProfileUpdate):
    employment_start_date: DateOnly | None = None
    contract_type: EmployeeContractType | None = None
    work_type: EmployeeWorkType | None = None

    @field_validator("employment_start_date")
    @classmethod
    def reject_null_start_date(cls, value: DateOnly | None) -> DateOnly | None:
        if value is None:
            raise ValueError("Employment start date cannot be null")
        return value

    @model_validator(mode="after")
    def validate_update_shape(self) -> Self:
        self._require_mutation(frozenset({"employment_start_date", "contract_type", "work_type"}))
        self._require_employee_version(frozenset({"employment_start_date"}))
        return self


__all__ = [
    "EMPLOYEE_PROFILE_HISTORY_LIMIT",
    "EmployeeContractType",
    "EmployeeEmploymentProfileMutationRead",
    "EmployeeEmploymentProfileRead",
    "EmployeeEmploymentProfileUpdate",
    "EmployeePersonalProfileMutationRead",
    "EmployeePersonalProfileRead",
    "EmployeePersonalProfileUpdate",
    "EmployeeProfileCoreRead",
    "EmployeeProfileOrganizationRead",
    "EmployeeProfileRead",
    "EmployeeWorkType",
]
