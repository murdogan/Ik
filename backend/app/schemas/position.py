"""Strict contracts for the tenant position/job-title catalog."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models.position import PositionStatus
from app.platform.pagination import decode_cursor, encode_cursor

POSITION_LIST_DEFAULT_LIMIT = 25
POSITION_LIST_MAX_LIMIT = 100
POSITION_SEARCH_MIN_LENGTH = 1
POSITION_SEARCH_MAX_LENGTH = 100

PositionCode = Annotated[
    StrictStr,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,31})$",
    ),
]
NormalizedPositionCode = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=32),
]
PositionTitle = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
PositionSearch = Annotated[
    StrictStr,
    StringConstraints(
        strip_whitespace=True,
        min_length=POSITION_SEARCH_MIN_LENGTH,
        max_length=POSITION_SEARCH_MAX_LENGTH,
    ),
]


def position_search_uses_exact_code(value: str) -> bool:
    """Use the tenant code B-tree for one- or two-character exact-code searches."""

    if not 1 <= len(value) <= 2:
        return False
    first_character, *remaining_characters = value
    if not (first_character.isascii() and first_character.isalnum()):
        return False
    return all(
        character.isascii() and (character.isalnum() or character in "_-")
        for character in remaining_characters
    )


def _contains_indexable_word_trigram(value: str) -> bool:
    consecutive_word_characters = 0
    for character in value:
        if character.isalnum():
            consecutive_word_characters += 1
            if consecutive_word_characters >= 3:
                return True
        else:
            consecutive_word_characters = 0
    return False


class _PositionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after", check_fields=False)
    @classmethod
    def reject_nul_characters(cls, value: object) -> object:
        if isinstance(value, str) and "\x00" in value:
            raise ValueError("Text fields cannot contain NUL characters")
        return value

    @field_validator("code", check_fields=False)
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class PositionCreate(_PositionPayload):
    code: PositionCode
    title: PositionTitle


class PositionUpdate(_PositionPayload):
    title: PositionTitle | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        return self


class PositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    code: str
    title: str
    status: PositionStatus
    archived_at: datetime | None
    accepts_new_assignments: bool
    created_at: datetime
    updated_at: datetime


class PositionListCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: NormalizedPositionCode
    id: UUID
    status: Literal["", "active", "archived"] = ""
    search: Annotated[StrictStr, StringConstraints(max_length=POSITION_SEARCH_MAX_LENGTH)] = ""

    @field_validator("code")
    @classmethod
    def reject_nul_code(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Cursor code cannot contain NUL characters")
        return value

    @classmethod
    def from_token(cls, token: str) -> Self:
        values = decode_cursor(token, expected_resource="positions")
        if set(values) != {"code", "id", "status", "search"}:
            raise ValueError("Invalid position cursor fields")
        return cls.model_validate(values)

    def to_token(self) -> str:
        return encode_cursor("positions", self.model_dump(mode="json"))


class PositionListPagination(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(
        default=POSITION_LIST_DEFAULT_LIMIT,
        ge=1,
        le=POSITION_LIST_MAX_LIMIT,
    )
    cursor: PositionListCursor | None = None
    status: PositionStatus | None = None
    search: PositionSearch | None = None

    @field_validator("search", mode="before")
    @classmethod
    def normalize_search(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if "\x00" in value:
            raise ValueError("Search cannot contain NUL characters")
        return value

    @field_validator("search")
    @classmethod
    def require_bounded_search(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if _contains_indexable_word_trigram(value) or position_search_uses_exact_code(value):
            return value
        raise ValueError(
            "Search must be an exact stable code or contain at least three consecutive "
            "letters or numbers"
        )

    def cursor_matches_filters(self) -> bool:
        if self.cursor is None:
            return True
        return self.cursor.status == (
            self.status.value if self.status is not None else ""
        ) and self.cursor.search == (self.search or "")

    def next_cursor(self, *, code: str, position_id: UUID) -> str:
        return PositionListCursor(
            code=code,
            id=position_id,
            status=self.status.value if self.status is not None else "",
            search=self.search or "",
        ).to_token()


__all__ = [
    "POSITION_LIST_DEFAULT_LIMIT",
    "POSITION_LIST_MAX_LIMIT",
    "POSITION_SEARCH_MAX_LENGTH",
    "POSITION_SEARCH_MIN_LENGTH",
    "position_search_uses_exact_code",
    "PositionCreate",
    "PositionListCursor",
    "PositionListPagination",
    "PositionRead",
    "PositionUpdate",
]
