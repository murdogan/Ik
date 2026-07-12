from __future__ import annotations

from datetime import datetime
from typing import Annotated, Self
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

from app.models.user import UserStatus
from app.platform.pagination import decode_cursor, encode_cursor
from app.schemas.authorization import RoleSummaryRead

USER_LIST_DEFAULT_LIMIT = 25
USER_LIST_MAX_LIMIT = 100
USER_SEARCH_MIN_LENGTH = 3
USER_SEARCH_MAX_LENGTH = 100

UserSearch = Annotated[
    StrictStr,
    StringConstraints(
        strip_whitespace=True,
        min_length=USER_SEARCH_MIN_LENGTH,
        max_length=USER_SEARCH_MAX_LENGTH,
    ),
]
UserFullName = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class UserAdministrationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    full_name: str
    status: UserStatus
    roles: list[RoleSummaryRead]
    permission_version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class UserAdministrationUpdate(BaseModel):
    """Allowlisted tenant-admin changes; authority and tenant never enter the payload."""

    model_config = ConfigDict(extra="forbid")

    full_name: UserFullName | None = None
    status: UserStatus | None = None

    @model_validator(mode="after")
    def require_non_null_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one user field must be provided")
        if any(getattr(self, field_name) is None for field_name in self.model_fields_set):
            raise ValueError("User patch fields cannot be null")
        return self


class UserListCursor(BaseModel):
    """Opaque continuation key bound to the filters that produced it."""

    model_config = ConfigDict(extra="forbid")

    created_at: datetime
    id: UUID
    search: str = Field(default="", max_length=USER_SEARCH_MAX_LENGTH)
    status: str = Field(default="", max_length=32)

    @field_validator("created_at")
    @classmethod
    def require_timezone_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("User cursor created_at must include a timezone")
        return value

    @field_validator("status")
    @classmethod
    def require_known_status(cls, value: str) -> str:
        if value and value not in UserStatus:
            raise ValueError("User cursor status is invalid")
        return value

    @classmethod
    def from_token(cls, token: str) -> UserListCursor:
        return cls.model_validate(decode_cursor(token, expected_resource="users"))

    def to_token(self) -> str:
        return encode_cursor("users", self.model_dump(mode="json"))


class UserListPagination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(
        default=USER_LIST_DEFAULT_LIMIT,
        ge=1,
        le=USER_LIST_MAX_LIMIT,
    )
    search: UserSearch | None = None
    status: UserStatus | None = None
    cursor: UserListCursor | None = None

    @model_validator(mode="after")
    def require_cursor_filter_match(self) -> Self:
        if self.cursor is None:
            return self
        normalized_search = self.search.lower() if self.search is not None else ""
        normalized_status = self.status.value if self.status is not None else ""
        if self.cursor.search != normalized_search or self.cursor.status != normalized_status:
            raise ValueError("User cursor does not match the active filters")
        return self


__all__ = [
    "USER_LIST_DEFAULT_LIMIT",
    "USER_LIST_MAX_LIMIT",
    "USER_SEARCH_MIN_LENGTH",
    "USER_SEARCH_MAX_LENGTH",
    "UserAdministrationRead",
    "UserAdministrationUpdate",
    "UserListCursor",
    "UserListPagination",
    "UserSearch",
]
