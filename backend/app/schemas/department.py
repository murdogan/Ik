"""Strict contracts for tenant department hierarchy administration."""

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

from app.models.department import DepartmentStatus
from app.platform.pagination import decode_cursor, encode_cursor

DEPARTMENT_LIST_DEFAULT_LIMIT = 25
DEPARTMENT_LIST_MAX_LIMIT = 100

DepartmentCode = Annotated[
    StrictStr,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,31})$",
    ),
]
NormalizedDepartmentCode = Annotated[
    StrictStr,
    StringConstraints(
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9](?:[a-z0-9_-]{0,31})$",
    ),
]
DepartmentName = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class _DepartmentPayload(BaseModel):
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


class DepartmentCreate(_DepartmentPayload):
    code: DepartmentCode
    name: DepartmentName
    parent_id: UUID | None = None


class DepartmentUpdate(_DepartmentPayload):
    name: DepartmentName | None = None
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class DepartmentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    parent_id: UUID | None
    code: str
    name: str
    status: DepartmentStatus
    archived_at: datetime | None
    has_children: bool
    accepts_new_assignments: bool
    created_at: datetime
    updated_at: datetime


class DepartmentListCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: NormalizedDepartmentCode
    id: UUID
    status: Literal["", "active", "archived"] = ""

    @classmethod
    def from_token(cls, token: str) -> Self:
        values = decode_cursor(token, expected_resource="departments")
        if set(values) != {"code", "id", "status"}:
            raise ValueError("Invalid department cursor fields")
        return cls.model_validate(values)

    def to_token(self) -> str:
        return encode_cursor("departments", self.model_dump(mode="json"))


class DepartmentListPagination(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(
        default=DEPARTMENT_LIST_DEFAULT_LIMIT,
        ge=1,
        le=DEPARTMENT_LIST_MAX_LIMIT,
    )
    cursor: DepartmentListCursor | None = None
    status: DepartmentStatus | None = None

    def cursor_matches_filters(self) -> bool:
        if self.cursor is None:
            return True
        return self.cursor.status == (self.status.value if self.status is not None else "")

    def next_cursor(self, *, code: str, department_id: UUID) -> str:
        return DepartmentListCursor(
            code=code,
            id=department_id,
            status=self.status.value if self.status is not None else "",
        ).to_token()


class DepartmentTreeCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: NormalizedDepartmentCode
    id: UUID
    parent_id: Annotated[StrictStr, StringConstraints(max_length=36)] = ""
    include_archived: Literal["0", "1"] = "0"

    @classmethod
    def from_token(cls, token: str) -> Self:
        values = decode_cursor(token, expected_resource="department_tree")
        if set(values) != {"code", "id", "parent_id", "include_archived"}:
            raise ValueError("Invalid department tree cursor fields")
        return cls.model_validate(values)

    def to_token(self) -> str:
        return encode_cursor("department_tree", self.model_dump(mode="json"))


class DepartmentTreePagination(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(
        default=DEPARTMENT_LIST_DEFAULT_LIMIT,
        ge=1,
        le=DEPARTMENT_LIST_MAX_LIMIT,
    )
    cursor: DepartmentTreeCursor | None = None
    parent_id: UUID | None = None
    include_archived: bool = False

    def cursor_matches_filters(self) -> bool:
        if self.cursor is None:
            return True
        return self.cursor.parent_id == (
            str(self.parent_id) if self.parent_id is not None else ""
        ) and self.cursor.include_archived == ("1" if self.include_archived else "0")

    def next_cursor(self, *, code: str, department_id: UUID) -> str:
        return DepartmentTreeCursor(
            code=code,
            id=department_id,
            parent_id=str(self.parent_id) if self.parent_id is not None else "",
            include_archived="1" if self.include_archived else "0",
        ).to_token()


__all__ = [
    "DEPARTMENT_LIST_DEFAULT_LIMIT",
    "DEPARTMENT_LIST_MAX_LIMIT",
    "DepartmentCreate",
    "DepartmentListCursor",
    "DepartmentListPagination",
    "DepartmentRead",
    "DepartmentTreeCursor",
    "DepartmentTreePagination",
    "DepartmentUpdate",
]
