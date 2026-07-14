"""Closed P4E request and response contracts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.employee import EmployeeStatus
from app.models.employee_profile_change_request import EmployeeProfileChangeRequestStatus
from app.schemas.date_fields import DateOnly
from app.schemas.employee_account_link import OwnMaskedFieldRead

PROFILE_CHANGE_REQUEST_LIMIT_MAX = 100
PROFILE_CHANGE_REQUEST_LIMIT_DEFAULT = 25
PROFILE_CHANGE_REJECTION_REASON_MAX_LENGTH = 500
PROFILE_CHANGE_REQUEST_FIELDS = frozenset({"preferred_name", "phone", "birth_date"})

EmployeeProfileChangeFieldName = Literal["preferred_name", "phone", "birth_date"]
_MASK_MARKERS = frozenset({"•", "●", "·", "▪", "◦"})
_PHONE_INPUT = re.compile(r"\+?[0-9][0-9 ()-]*[0-9]")


def normalize_preferred_name(value: str) -> str:
    """Normalize display whitespace without inventing locale-sensitive name rules."""

    normalized = " ".join(value.split())
    _reject_control_characters(normalized)
    return normalized


def _reject_control_characters(value: str) -> None:
    if any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in value):
        raise ValueError("Control characters cannot be submitted")


def normalize_phone(value: str) -> str:
    """Return a stable phone representation accepted by the P4E request boundary."""

    if any(marker in value for marker in _MASK_MARKERS) or "*" in value:
        raise ValueError("Masked phone displays cannot be submitted")
    if _PHONE_INPUT.fullmatch(value) is None or not _has_structured_phone_separators(value):
        raise ValueError("Phone format is invalid")
    digits = "".join(character for character in value if character.isdigit())
    if not 7 <= len(digits) <= 15:
        raise ValueError("Phone must contain between 7 and 15 digits")
    return f"+{digits}" if value.startswith("+") else digits


def _has_structured_phone_separators(value: str) -> bool:
    """Reject ambiguous separators and unbalanced/non-digit parenthesized groups."""

    body = value.removeprefix("+")
    parenthesized = False
    group_digits = 0
    for index, character in enumerate(body):
        previous = body[index - 1] if index else None
        following = body[index + 1] if index + 1 < len(body) else None
        if character.isdigit():
            if parenthesized:
                group_digits += 1
            continue
        if character == "(":
            if parenthesized or following is None or not following.isdigit():
                return False
            if previous is not None and not (previous.isdigit() or previous == " "):
                return False
            parenthesized = True
            group_digits = 0
            continue
        if character == ")":
            if not parenthesized or group_digits == 0:
                return False
            if following is not None and not (following.isdigit() or following in " -"):
                return False
            parenthesized = False
            continue
        if character in " -":
            if parenthesized or previous is None or following is None:
                return False
            if not (previous.isdigit() or previous == ")"):
                return False
            if not (following.isdigit() or following == "("):
                return False
            continue
        return False
    return not parenthesized


def normalized_existing_phone(value: str | None) -> str | None:
    """Normalize a legacy current value when possible for no-op comparison."""

    if value is None:
        return None
    try:
        return normalize_phone(value.strip())
    except ValueError:
        return value.strip()


class EmployeeProfileChangeRequestCreate(BaseModel):
    """Only the three currently requestable personal fields; omission means unchanged."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    preferred_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    birth_date: DateOnly | None = None

    @field_validator("preferred_name")
    @classmethod
    def validate_preferred_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(marker in value for marker in _MASK_MARKERS) or "*" in value:
            raise ValueError("Masked displays cannot be submitted")
        normalized = normalize_preferred_name(value)
        if not normalized:
            raise ValueError("preferred_name cannot be blank; use null to clear it")
        if len(normalized) > 200:
            raise ValueError("preferred_name is too long")
        return normalized

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value:
            raise ValueError("phone cannot be blank; use null to clear it")
        return normalize_phone(value)

    @model_validator(mode="after")
    def require_selected_field(self) -> Self:
        if not self.model_fields_set.intersection(PROFILE_CHANGE_REQUEST_FIELDS):
            raise ValueError("At least one requestable profile field must be selected")
        return self

    def selected_fields(self) -> tuple[EmployeeProfileChangeFieldName, ...]:
        return tuple(
            field_name
            for field_name in ("preferred_name", "phone", "birth_date")
            if field_name in self.model_fields_set
        )


class EmployeeProfileChangeRequestExpectedVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(strict=True, ge=1)


class EmployeeProfileChangeRequestReject(EmployeeProfileChangeRequestExpectedVersion):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=PROFILE_CHANGE_REJECTION_REASON_MAX_LENGTH)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("reason cannot be blank")
        _reject_control_characters(normalized)
        return normalized


class OwnPreferredNameChangeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_value: str | None
    proposed_value: str | None


class OwnMaskedProfileChangeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_value: OwnMaskedFieldRead
    proposed_value: OwnMaskedFieldRead


class OwnEmployeeProfileChangesRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_name: OwnPreferredNameChangeRead | None
    phone: OwnMaskedProfileChangeRead | None
    birth_date: OwnMaskedProfileChangeRead | None


class EmployeeProfileChangeRequestCommonRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: EmployeeProfileChangeRequestStatus
    version: int = Field(ge=1)
    submitted_at: datetime
    decided_at: datetime | None
    cancelled_at: datetime | None
    rejection_reason: str | None
    changed_fields: tuple[EmployeeProfileChangeFieldName, ...]

    @field_validator("submitted_at", "decided_at", "cancelled_at")
    @classmethod
    def require_aware_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Profile-change timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def require_consistent_terminal_state(self) -> Self:
        if not self.changed_fields or len(set(self.changed_fields)) != len(self.changed_fields):
            raise ValueError("changed_fields must contain distinct requestable fields")
        if self.status is EmployeeProfileChangeRequestStatus.SUBMITTED:
            valid = (
                self.decided_at is None
                and self.cancelled_at is None
                and self.rejection_reason is None
            )
        elif self.status is EmployeeProfileChangeRequestStatus.APPROVED:
            valid = (
                self.decided_at is not None
                and self.cancelled_at is None
                and self.rejection_reason is None
            )
        elif self.status is EmployeeProfileChangeRequestStatus.REJECTED:
            valid = (
                self.decided_at is not None
                and self.cancelled_at is None
                and self.rejection_reason is not None
            )
        else:
            valid = (
                self.decided_at is None
                and self.cancelled_at is not None
                and self.rejection_reason is None
            )
        if not valid:
            raise ValueError("Profile-change request state is inconsistent")
        return self


class OwnEmployeeProfileChangeRequestRead(EmployeeProfileChangeRequestCommonRead):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    changes: OwnEmployeeProfileChangesRead


class EmployeeProfileChangeRequestEmployeeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    employee_number: str
    first_name: str
    last_name: str
    email: str | None
    status: EmployeeStatus


class EmployeeProfileChangeRequestHrSummaryRead(EmployeeProfileChangeRequestCommonRead):
    model_config = ConfigDict(extra="forbid")

    employee: EmployeeProfileChangeRequestEmployeeRead
    base_profile_version: int = Field(ge=1)
    current_profile_version: int = Field(ge=1)
    profile_is_stale: bool


class HrPreferredNameChangeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_value: str | None
    current_value: str | None
    proposed_value: str | None
    current_matches_base: bool


class HrPhoneChangeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_value: str | None
    current_value: str | None
    proposed_value: str | None
    current_matches_base: bool


class HrBirthDateChangeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_value: DateOnly | None
    current_value: DateOnly | None
    proposed_value: DateOnly | None
    current_matches_base: bool


class HrEmployeeProfileChangesRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_name: HrPreferredNameChangeRead | None
    phone: HrPhoneChangeRead | None
    birth_date: HrBirthDateChangeRead | None


class EmployeeProfileChangeRequestHrDetailRead(EmployeeProfileChangeRequestHrSummaryRead):
    model_config = ConfigDict(extra="forbid")

    changes: HrEmployeeProfileChangesRead


__all__ = [
    "PROFILE_CHANGE_REJECTION_REASON_MAX_LENGTH",
    "PROFILE_CHANGE_REQUEST_FIELDS",
    "PROFILE_CHANGE_REQUEST_LIMIT_DEFAULT",
    "PROFILE_CHANGE_REQUEST_LIMIT_MAX",
    "EmployeeProfileChangeFieldName",
    "EmployeeProfileChangeRequestCommonRead",
    "EmployeeProfileChangeRequestCreate",
    "EmployeeProfileChangeRequestEmployeeRead",
    "EmployeeProfileChangeRequestExpectedVersion",
    "EmployeeProfileChangeRequestHrDetailRead",
    "EmployeeProfileChangeRequestHrSummaryRead",
    "EmployeeProfileChangeRequestReject",
    "HrBirthDateChangeRead",
    "HrEmployeeProfileChangesRead",
    "HrPhoneChangeRead",
    "HrPreferredNameChangeRead",
    "OwnEmployeeProfileChangeRequestRead",
    "OwnEmployeeProfileChangesRead",
    "OwnMaskedProfileChangeRead",
    "OwnPreferredNameChangeRead",
    "normalize_phone",
    "normalize_preferred_name",
    "normalized_existing_phone",
]
