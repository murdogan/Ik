"""Strict announcement commands and recipient-safe projections."""

from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.announcement import AnnouncementStatus

ANNOUNCEMENT_LIST_DEFAULT_LIMIT = 30
ANNOUNCEMENT_LIST_MAX_LIMIT = 100
ANNOUNCEMENT_TARGET_DIMENSION_MAX = 20


def _plain_text(value: str) -> str:
    normalized = "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").split("\n"))
    normalized = normalized.strip()
    if not normalized or any(
        ord(character) < 32 and character not in {"\n", "\t"} for character in normalized
    ):
        raise ValueError("Announcement text must be non-empty plain text")
    return normalized


def _single_line_text(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or any(ord(character) < 32 for character in normalized):
        raise ValueError("Announcement title must be non-empty plain text")
    return normalized


class AnnouncementTargets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_ids: list[UUID] = Field(default_factory=list, max_length=ANNOUNCEMENT_TARGET_DIMENSION_MAX)
    department_ids: list[UUID] = Field(
        default_factory=list, max_length=ANNOUNCEMENT_TARGET_DIMENSION_MAX
    )
    branch_ids: list[UUID] = Field(
        default_factory=list, max_length=ANNOUNCEMENT_TARGET_DIMENSION_MAX
    )

    @field_validator("role_ids", "department_ids", "branch_ids")
    @classmethod
    def require_unique_nonzero_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)) or any(identifier.int == 0 for identifier in value):
            raise ValueError("Announcement target identifiers must be unique and non-zero")
        return value


class AnnouncementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10_000)
    is_critical: bool = False
    targets: AnnouncementTargets = Field(default_factory=AnnouncementTargets)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _single_line_text(value)

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        return _plain_text(value)


class AnnouncementUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=10_000)
    is_critical: bool | None = None
    targets: AnnouncementTargets | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        return None if value is None else _single_line_text(value)

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str | None) -> str | None:
        return None if value is None else _plain_text(value)

    @model_validator(mode="after")
    def require_update(self) -> Self:
        changed = set(self.model_fields_set) - {"expected_version"}
        if not changed:
            raise ValueError("At least one announcement field must be provided")
        if any(getattr(self, field_name) is None for field_name in changed):
            raise ValueError("Announcement update fields cannot be null")
        return self


class AnnouncementVersionAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class AnnouncementTargetOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    label: str


class AnnouncementTargetOptionsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles: list[AnnouncementTargetOption]
    departments: list[AnnouncementTargetOption]
    branches: list[AnnouncementTargetOption]


class AnnouncementSummaryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    is_critical: bool
    status: AnnouncementStatus
    version: int = Field(ge=1)
    published_at: datetime | None
    archived_at: datetime | None
    read_at: datetime | None = None
    acknowledged_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AnnouncementDetailRead(AnnouncementSummaryRead):
    model_config = ConfigDict(extra="forbid")

    body: str
    targets: AnnouncementTargets | None = None


__all__ = [
    "ANNOUNCEMENT_LIST_DEFAULT_LIMIT",
    "ANNOUNCEMENT_LIST_MAX_LIMIT",
    "AnnouncementCreate",
    "AnnouncementDetailRead",
    "AnnouncementSummaryRead",
    "AnnouncementTargetOption",
    "AnnouncementTargetOptionsRead",
    "AnnouncementTargets",
    "AnnouncementUpdate",
    "AnnouncementVersionAction",
]
