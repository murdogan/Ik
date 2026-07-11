from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self
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

from app.modules.core.domain.tenant import (
    TenantDateFormat,
    TenantHealth,
    TenantLocale,
    TenantPlan,
    TenantRegion,
    TenantStatus,
    TenantTimeFormat,
    TenantWeekStartDay,
)
from app.platform.pagination import decode_cursor, encode_cursor

TENANT_LIST_DEFAULT_LIMIT = 50
TENANT_LIST_MAX_LIMIT = 200

TenantSlug = Annotated[
    StrictStr,
    StringConstraints(
        strip_whitespace=True,
        min_length=2,
        max_length=80,
        pattern=r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$",
    ),
]
TenantName = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
TenantTimezone = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
]
TenantPlanRead = TenantPlan | Literal["premium"]


class _TenantPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("timezone", check_fields=False)
    @classmethod
    def validate_iana_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Timezone must be a recognized IANA timezone") from exc
        return value


class TenantSettingsProvision(_TenantPayload):
    week_start_day: TenantWeekStartDay = TenantWeekStartDay.MONDAY
    date_format: TenantDateFormat = TenantDateFormat.DAY_MONTH_YEAR
    time_format: TenantTimeFormat = TenantTimeFormat.HOUR_24


class TenantPlatformCreate(_TenantPayload):
    slug: TenantSlug
    name: TenantName
    plan_code: TenantPlan = TenantPlan.CORE
    data_region: TenantRegion = TenantRegion.TR_1
    locale: TenantLocale = TenantLocale.TR_TR
    timezone: TenantTimezone = "Europe/Istanbul"
    settings: TenantSettingsProvision = Field(default_factory=TenantSettingsProvision)


class TenantPlatformUpdate(_TenantPayload):
    name: TenantName | None = None
    status: TenantStatus | None = None
    plan_code: TenantPlan | None = None
    data_region: TenantRegion | None = None
    locale: TenantLocale | None = None
    timezone: TenantTimezone | None = None

    @model_validator(mode="after")
    def require_non_null_change(self) -> Self:
        _require_non_null_patch(self)
        return self


class TenantSettingsUpdate(_TenantPayload):
    locale: TenantLocale | None = None
    timezone: TenantTimezone | None = None
    week_start_day: TenantWeekStartDay | None = None
    date_format: TenantDateFormat | None = None
    time_format: TenantTimeFormat | None = None

    @model_validator(mode="after")
    def require_non_null_change(self) -> Self:
        _require_non_null_patch(self)
        return self


class TenantPlatformRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    status: TenantStatus
    plan_code: TenantPlanRead
    data_region: TenantRegion
    locale: TenantLocale
    timezone: str
    health: TenantHealth
    created_at: datetime
    updated_at: datetime


class TenantListCursor(BaseModel):
    """Opaque platform-tenant continuation key for the stable creation order."""

    model_config = ConfigDict(extra="forbid")

    created_at: datetime
    id: UUID

    @field_validator("created_at")
    @classmethod
    def require_timezone_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Tenant cursor created_at must include a timezone")
        return value

    @classmethod
    def from_token(cls, token: str) -> TenantListCursor:
        return cls.model_validate(decode_cursor(token, expected_resource="platform_tenants"))

    def to_token(self) -> str:
        return encode_cursor("platform_tenants", self.model_dump(mode="json"))


class TenantListPagination(BaseModel):
    """Cursor-only pagination for the new Phase-1 platform list contract."""

    limit: int = Field(
        default=TENANT_LIST_DEFAULT_LIMIT,
        ge=1,
        le=TENANT_LIST_MAX_LIMIT,
    )
    cursor: TenantListCursor | None = None


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    status: TenantStatus
    plan_code: TenantPlanRead
    locale: TenantLocale
    timezone: str


class TenantSettingsRead(BaseModel):
    locale: TenantLocale
    timezone: str
    week_start_day: TenantWeekStartDay
    date_format: TenantDateFormat
    time_format: TenantTimeFormat


def _require_non_null_patch(payload: BaseModel) -> None:
    if not payload.model_fields_set:
        raise ValueError("At least one setting or tenant field must be provided")
    if any(getattr(payload, field_name) is None for field_name in payload.model_fields_set):
        raise ValueError("Patch fields cannot be null")
