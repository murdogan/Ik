"""Closed, redacted event contracts for CORE tenant platform operations.

These models deliberately expose no generic payload, metadata, or before/after mapping. A later
audit adapter can persist them, but cannot use this boundary to smuggle credentials or HR records
into a platform event.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StrictBool,
    field_validator,
    model_validator,
)

from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.modules.core.domain.tenant import TenantPlan, TenantRegion, TenantStatus
from app.platform.events.contracts import (
    PlatformEventActorType,
    PlatformEventCategory,
    PlatformEventContract,
    PlatformEventDataClassification,
    PlatformEventResult,
    PlatformEventScopeType,
    PlatformEventSeverity,
    PlatformEventVisibilityClass,
    register_platform_event_contract,
)
from app.platform.request_context import is_valid_request_id, is_valid_trace_id


class PlatformEventType(StrEnum):
    """The complete Phase-1 CORE platform-event catalog."""

    TENANT_CREATED = "tenant.created"
    TENANT_STATUS_CHANGED = "tenant.status_changed"
    TENANT_SETTING_CHANGED = "tenant.setting_changed"
    FEATURE_FLAG_CHANGED = "feature_flag.changed"


class TenantSettingField(StrEnum):
    """Platform-safe tenant fields that may be named in a settings-change event."""

    NAME = "name"
    PLAN_CODE = "plan_code"
    DATA_REGION = "data_region"
    LOCALE = "locale"
    TIMEZONE = "timezone"
    WEEK_START_DAY = "week_start_day"
    DATE_FORMAT = "date_format"
    TIME_FORMAT = "time_format"
    ACTIVE_EMPLOYEE_LIMIT = "active_employee_limit"


class _PlatformTenantEvent(BaseModel, PlatformEventContract):
    """Fixed audit-safe metadata shared by the four explicit event contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    occurred_at: AwareDatetime
    tenant_id: UUID
    resource_id: UUID
    actor_type: PlatformEventActorType
    actor_user_id: UUID | None = None
    session_id: UUID | None = None
    support_session_id: UUID | None = None
    request_id: str
    trace_id: str

    scope_type: Literal[PlatformEventScopeType.TENANT] = PlatformEventScopeType.TENANT
    category: Literal[PlatformEventCategory.PLATFORM_OPERATIONS] = (
        PlatformEventCategory.PLATFORM_OPERATIONS
    )
    severity: Literal[PlatformEventSeverity.INFO] = PlatformEventSeverity.INFO
    result: Literal[PlatformEventResult.SUCCESS] = PlatformEventResult.SUCCESS
    data_classification: Literal[PlatformEventDataClassification.PLATFORM_METADATA] = (
        PlatformEventDataClassification.PLATFORM_METADATA
    )
    visibility_class: Literal[PlatformEventVisibilityClass.PLATFORM_OPS] = (
        PlatformEventVisibilityClass.PLATFORM_OPS
    )

    @field_validator("id", "tenant_id", "resource_id")
    @classmethod
    def require_nonzero_uuid(cls, value: UUID) -> UUID:
        if value.int == 0:
            raise ValueError("Platform event identifiers must be non-zero UUIDs")
        return value

    @field_validator("actor_user_id", "session_id", "support_session_id")
    @classmethod
    def require_optional_nonzero_uuid(cls, value: UUID | None) -> UUID | None:
        if value is not None and value.int == 0:
            raise ValueError("Platform event actor/session identifiers must be non-zero UUIDs")
        return value

    @model_validator(mode="after")
    def require_tenant_resource_scope(self) -> Self:
        if self.resource_id != self.tenant_id:
            raise ValueError("Phase-1 platform event resource_id must match tenant_id")
        return self

    @field_validator("occurred_at")
    @classmethod
    def require_timezone_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Platform event occurred_at must include a timezone")
        return value

    @field_validator("request_id")
    @classmethod
    def require_safe_request_id(cls, value: str) -> str:
        if not is_valid_request_id(value):
            raise ValueError("Platform event request_id must be a safe opaque identifier")
        return value

    @field_validator("trace_id")
    @classmethod
    def require_safe_trace_id(cls, value: str) -> str:
        if not is_valid_trace_id(value):
            raise ValueError("Platform event trace_id must be a canonical non-zero trace ID")
        return value


@register_platform_event_contract
class TenantCreatedEvent(_PlatformTenantEvent):
    """Redacted tenant-provisioning result without customer or settings payloads."""

    event_type: Literal[PlatformEventType.TENANT_CREATED] = PlatformEventType.TENANT_CREATED
    resource_type: Literal["tenant"] = "tenant"
    action: Literal["create"] = "create"
    status: Literal[TenantStatus.PROVISIONING] = TenantStatus.PROVISIONING
    plan_code: TenantPlan
    data_region: TenantRegion


@register_platform_event_contract
class TenantStatusChangedEvent(_PlatformTenantEvent):
    """One successful, actual tenant lifecycle transition."""

    event_type: Literal[PlatformEventType.TENANT_STATUS_CHANGED] = (
        PlatformEventType.TENANT_STATUS_CHANGED
    )
    resource_type: Literal["tenant"] = "tenant"
    action: Literal["change_status"] = "change_status"
    before_status: TenantStatus
    after_status: TenantStatus

    @model_validator(mode="after")
    def require_actual_status_change(self) -> Self:
        if self.before_status is self.after_status:
            raise ValueError("Tenant status event requires an actual status change")
        return self


@register_platform_event_contract
class TenantSettingChangedEvent(_PlatformTenantEvent):
    """Names changed safe fields without copying their values or entity snapshots."""

    event_type: Literal[PlatformEventType.TENANT_SETTING_CHANGED] = (
        PlatformEventType.TENANT_SETTING_CHANGED
    )
    resource_type: Literal["tenant"] = "tenant"
    action: Literal["change_setting"] = "change_setting"
    changed_fields: tuple[TenantSettingField, ...]

    @field_validator("changed_fields")
    @classmethod
    def require_nonempty_unique_fields(
        cls,
        value: tuple[TenantSettingField, ...],
    ) -> tuple[TenantSettingField, ...]:
        if not value:
            raise ValueError("Tenant settings event requires at least one changed field")
        if len(value) != len(set(value)):
            raise ValueError("Tenant settings event changed fields must be unique")
        return value


@register_platform_event_contract
class FeatureFlagChangedEvent(_PlatformTenantEvent):
    """One typed tenant flag transition with no arbitrary rollout metadata."""

    event_type: Literal[PlatformEventType.FEATURE_FLAG_CHANGED] = (
        PlatformEventType.FEATURE_FLAG_CHANGED
    )
    resource_type: Literal["feature_flag"] = "feature_flag"
    action: Literal["change_flag"] = "change_flag"
    feature_key: FeatureFlagKey
    before_enabled: StrictBool
    after_enabled: StrictBool

    @model_validator(mode="after")
    def require_actual_feature_change(self) -> Self:
        if self.before_enabled is self.after_enabled:
            raise ValueError("Feature flag event requires an actual enabled-state change")
        return self


type PlatformEvent = (
    TenantCreatedEvent
    | TenantStatusChangedEvent
    | TenantSettingChangedEvent
    | FeatureFlagChangedEvent
)

# Runtime adapters use exact type membership rather than ``isinstance`` so a subclass cannot add
# a password, token, employee payload, or other field and still cross the recording boundary.
PLATFORM_EVENT_TYPES: tuple[type[PlatformEventContract], ...] = (
    TenantCreatedEvent,
    TenantStatusChangedEvent,
    TenantSettingChangedEvent,
    FeatureFlagChangedEvent,
)


__all__ = [
    "FeatureFlagChangedEvent",
    "PlatformEvent",
    "PLATFORM_EVENT_TYPES",
    "PlatformEventActorType",
    "PlatformEventType",
    "TenantCreatedEvent",
    "TenantSettingChangedEvent",
    "TenantSettingField",
    "TenantStatusChangedEvent",
]
