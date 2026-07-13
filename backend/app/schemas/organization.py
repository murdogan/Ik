"""Contracts for tenant legal entities and branch/location administration."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models.organization import BranchStatus, LegalEntityStatus
from app.platform.pagination import decode_cursor, encode_cursor

ORGANIZATION_LIST_DEFAULT_LIMIT = 25
ORGANIZATION_LIST_MAX_LIMIT = 100

OrganizationCode = Annotated[
    StrictStr,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,31})$",
    ),
]
NormalizedOrganizationCode = Annotated[
    StrictStr,
    StringConstraints(
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9](?:[a-z0-9_-]{0,31})$",
    ),
]
OrganizationName = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
RegisteredName = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=240),
]
OrganizationTimezone = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
]
CountryCode = Annotated[
    StrictStr,
    StringConstraints(
        strip_whitespace=True,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Za-z]{2}$",
    ),
]
TaxNumber = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
]
City = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
Address = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class _OrganizationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after", check_fields=False)
    @classmethod
    def reject_nul_characters(cls, value: object) -> object:
        # PostgreSQL text types reject U+0000 while SQLite would persist it. Reject at the
        # transport boundary so both supported development/runtime dialects behave identically.
        if isinstance(value, str) and "\x00" in value:
            raise ValueError("Text fields cannot contain NUL characters")
        return value

    @field_validator("code", check_fields=False)
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("country_code", check_fields=False)
    @classmethod
    def normalize_country_code(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @field_validator("timezone", check_fields=False)
    @classmethod
    def validate_iana_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Timezone must be a recognized IANA timezone") from exc
        return value


class LegalEntityCreate(_OrganizationPayload):
    code: OrganizationCode
    name: OrganizationName
    registered_name: RegisteredName
    country_code: CountryCode | None = None
    tax_number: TaxNumber | None = None
    timezone: OrganizationTimezone


class LegalEntityUpdate(_OrganizationPayload):
    name: OrganizationName | None = None
    registered_name: RegisteredName | None = None
    country_code: CountryCode | None = None
    tax_number: TaxNumber | None = None
    timezone: OrganizationTimezone | None = None
    status: LegalEntityStatus | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        _require_patch(
            self,
            non_nullable={"name", "registered_name", "timezone", "status"},
        )
        return self


class LegalEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    code: str
    name: str
    registered_name: str
    country_code: str | None
    tax_number: str | None
    timezone: str
    status: LegalEntityStatus
    is_default: bool
    created_at: datetime
    updated_at: datetime


class BranchCreate(_OrganizationPayload):
    legal_entity_id: UUID
    code: OrganizationCode
    name: OrganizationName
    timezone: OrganizationTimezone
    country_code: CountryCode | None = None
    city: City | None = None
    address: Address | None = None


class BranchUpdate(_OrganizationPayload):
    name: OrganizationName | None = None
    timezone: OrganizationTimezone | None = None
    country_code: CountryCode | None = None
    city: City | None = None
    address: Address | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        _require_patch(self, non_nullable={"name", "timezone"})
        return self


class BranchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    legal_entity_id: UUID
    code: str
    name: str
    timezone: str
    country_code: str | None
    city: str | None
    address: str | None
    status: BranchStatus
    archived_at: datetime | None
    accepts_new_assignments: bool
    created_at: datetime
    updated_at: datetime


class LegalEntityListCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: NormalizedOrganizationCode
    id: UUID

    @classmethod
    def from_token(cls, token: str) -> Self:
        return cls.model_validate(
            decode_cursor(token, expected_resource="legal_entities")
        )

    def to_token(self) -> str:
        return encode_cursor("legal_entities", self.model_dump(mode="json"))


class LegalEntityListPagination(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(
        default=ORGANIZATION_LIST_DEFAULT_LIMIT,
        ge=1,
        le=ORGANIZATION_LIST_MAX_LIMIT,
    )
    cursor: LegalEntityListCursor | None = None


class BranchListCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: NormalizedOrganizationCode
    id: UUID
    status: str = ""
    legal_entity_id: str = ""

    @classmethod
    def from_token(cls, token: str) -> Self:
        values = decode_cursor(token, expected_resource="branches")
        if set(values) != {"code", "id", "status", "legal_entity_id"}:
            raise ValueError("Invalid branch cursor fields")
        return cls.model_validate(values)

    def to_token(self) -> str:
        return encode_cursor("branches", self.model_dump(mode="json"))


class BranchListPagination(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(
        default=ORGANIZATION_LIST_DEFAULT_LIMIT,
        ge=1,
        le=ORGANIZATION_LIST_MAX_LIMIT,
    )
    cursor: BranchListCursor | None = None
    status: BranchStatus | None = None
    legal_entity_id: UUID | None = None

    def cursor_matches_filters(self) -> bool:
        if self.cursor is None:
            return True
        return (
            self.cursor.status == (self.status.value if self.status is not None else "")
            and self.cursor.legal_entity_id
            == (str(self.legal_entity_id) if self.legal_entity_id is not None else "")
        )

    def next_cursor(self, *, code: str, branch_id: UUID) -> str:
        return BranchListCursor(
            code=code,
            id=branch_id,
            status=self.status.value if self.status is not None else "",
            legal_entity_id=(
                str(self.legal_entity_id) if self.legal_entity_id is not None else ""
            ),
        ).to_token()


def _require_patch(payload: BaseModel, *, non_nullable: set[str]) -> None:
    if not payload.model_fields_set:
        raise ValueError("At least one field must be provided")
    for field_name in payload.model_fields_set & non_nullable:
        if getattr(payload, field_name) is None:
            raise ValueError(f"{field_name} cannot be null")


__all__ = [
    "BranchCreate",
    "BranchListCursor",
    "BranchListPagination",
    "BranchRead",
    "BranchUpdate",
    "LegalEntityCreate",
    "LegalEntityListCursor",
    "LegalEntityListPagination",
    "LegalEntityRead",
    "LegalEntityUpdate",
    "ORGANIZATION_LIST_DEFAULT_LIMIT",
    "ORGANIZATION_LIST_MAX_LIMIT",
]
