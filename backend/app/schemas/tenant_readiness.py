"""Strict tenant setup-readiness response contract."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class TenantReadinessItemKey(StrEnum):
    DEFAULT_LEGAL_ENTITY = "default_legal_entity"
    ORGANIZATION_STRUCTURE = "organization_structure"
    ACTIVE_TENANT_ADMINISTRATOR = "active_tenant_administrator"
    EMPLOYEE_MASTER_DATA = "employee_master_data"
    LEAVE_CONFIGURATION = "leave_configuration"
    DOCUMENT_CONFIGURATION = "document_configuration"
    PRIVACY_NOTICE = "privacy_notice"
    FEATURE_DEPENDENCIES = "feature_dependencies"
    NOTIFICATION_DELIVERY = "notification_delivery"


class TenantReadinessItemState(StrEnum):
    READY = "ready"
    ACTION_REQUIRED = "action_required"
    NOT_APPLICABLE = "not_applicable"


class TenantReadinessOverallState(StrEnum):
    READY = "ready"
    ACTION_REQUIRED = "action_required"


TenantReadinessCount = Annotated[int, Field(strict=True, ge=0)]
TenantReadinessRemediationRoute = Literal[
    "/organization",
    "/users",
    "/employees",
    "/leave/admin",
    "/document-types",
    "/privacy/manage",
]

TENANT_READINESS_ITEM_ORDER: tuple[TenantReadinessItemKey, ...] = tuple(TenantReadinessItemKey)

_COUNTED_ITEM_KEYS = frozenset(
    {
        TenantReadinessItemKey.DEFAULT_LEGAL_ENTITY,
        TenantReadinessItemKey.ACTIVE_TENANT_ADMINISTRATOR,
        TenantReadinessItemKey.EMPLOYEE_MASTER_DATA,
        TenantReadinessItemKey.DOCUMENT_CONFIGURATION,
        TenantReadinessItemKey.PRIVACY_NOTICE,
    }
)
_OPTIONAL_ITEM_KEYS = frozenset(
    {
        TenantReadinessItemKey.LEAVE_CONFIGURATION,
        TenantReadinessItemKey.DOCUMENT_CONFIGURATION,
        TenantReadinessItemKey.NOTIFICATION_DELIVERY,
    }
)
_FIXED_REMEDIATION_ROUTES: dict[
    TenantReadinessItemKey,
    TenantReadinessRemediationRoute | None,
] = {
    TenantReadinessItemKey.DEFAULT_LEGAL_ENTITY: "/organization",
    TenantReadinessItemKey.ORGANIZATION_STRUCTURE: "/organization",
    TenantReadinessItemKey.ACTIVE_TENANT_ADMINISTRATOR: "/users",
    TenantReadinessItemKey.EMPLOYEE_MASTER_DATA: "/employees",
    TenantReadinessItemKey.LEAVE_CONFIGURATION: "/leave/admin",
    TenantReadinessItemKey.PRIVACY_NOTICE: "/privacy/manage",
    TenantReadinessItemKey.FEATURE_DEPENDENCIES: None,
    TenantReadinessItemKey.NOTIFICATION_DELIVERY: None,
}


class TenantReadinessItemRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: TenantReadinessItemKey
    state: TenantReadinessItemState
    count: TenantReadinessCount | None
    remediation_route: TenantReadinessRemediationRoute | None
    evaluated_at: AwareDatetime

    @field_validator("evaluated_at")
    @classmethod
    def require_utc_timestamp(cls, value: AwareDatetime) -> AwareDatetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("Readiness timestamps must be UTC")
        return value

    @model_validator(mode="after")
    def require_item_contract(self) -> Self:
        if (self.key in _COUNTED_ITEM_KEYS) != (self.count is not None):
            raise ValueError("Readiness count presence does not match the item contract")
        if self.key in {
            TenantReadinessItemKey.DEFAULT_LEGAL_ENTITY,
            TenantReadinessItemKey.PRIVACY_NOTICE,
        } and self.count not in {0, 1}:
            raise ValueError("This readiness count must be zero or one")
        if (
            self.state is TenantReadinessItemState.NOT_APPLICABLE
            and self.key not in _OPTIONAL_ITEM_KEYS
        ):
            raise ValueError("This readiness item is never not-applicable")
        if (
            self.key is TenantReadinessItemKey.NOTIFICATION_DELIVERY
            and self.state is TenantReadinessItemState.READY
        ):
            raise ValueError("Notification delivery cannot be pilot-ready")

        expected_route = (
            "/document-types"
            if self.key is TenantReadinessItemKey.DOCUMENT_CONFIGURATION and self.count == 0
            else None
            if self.key is TenantReadinessItemKey.DOCUMENT_CONFIGURATION
            else _FIXED_REMEDIATION_ROUTES[self.key]
        )
        if self.remediation_route != expected_route:
            raise ValueError("Readiness remediation route does not match the item contract")

        if self.key is TenantReadinessItemKey.DEFAULT_LEGAL_ENTITY and (
            (self.count == 1) != (self.state is TenantReadinessItemState.READY)
        ):
            raise ValueError("Default legal-entity readiness does not match its count")
        if self.key in {
            TenantReadinessItemKey.ACTIVE_TENANT_ADMINISTRATOR,
            TenantReadinessItemKey.EMPLOYEE_MASTER_DATA,
            TenantReadinessItemKey.PRIVACY_NOTICE,
        } and ((self.count or 0) > 0) != (self.state is TenantReadinessItemState.READY):
            raise ValueError("Readiness state does not match its resource count")
        if (
            self.key is TenantReadinessItemKey.DOCUMENT_CONFIGURATION
            and self.count == 0
            and self.state is TenantReadinessItemState.READY
        ):
            raise ValueError("Document readiness requires a document type")
        return self


class TenantReadinessRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    overall_state: TenantReadinessOverallState
    evaluated_at: AwareDatetime
    items: list[TenantReadinessItemRead] = Field(
        min_length=len(TENANT_READINESS_ITEM_ORDER),
        max_length=len(TENANT_READINESS_ITEM_ORDER),
    )

    @field_validator("evaluated_at")
    @classmethod
    def require_utc_timestamp(cls, value: AwareDatetime) -> AwareDatetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("Readiness timestamps must be UTC")
        return value

    @model_validator(mode="after")
    def require_projection_contract(self) -> Self:
        if tuple(item.key for item in self.items) != TENANT_READINESS_ITEM_ORDER:
            raise ValueError("Readiness items must use the fixed checklist order")
        if any(item.evaluated_at != self.evaluated_at for item in self.items):
            raise ValueError("All readiness timestamps must be identical")
        expected_overall_state = (
            TenantReadinessOverallState.READY
            if all(
                item.state
                in {
                    TenantReadinessItemState.READY,
                    TenantReadinessItemState.NOT_APPLICABLE,
                }
                for item in self.items
            )
            else TenantReadinessOverallState.ACTION_REQUIRED
        )
        if self.overall_state is not expected_overall_state:
            raise ValueError("Overall readiness does not match the checklist")
        return self


__all__ = [
    "TENANT_READINESS_ITEM_ORDER",
    "TenantReadinessItemKey",
    "TenantReadinessItemRead",
    "TenantReadinessItemState",
    "TenantReadinessOverallState",
    "TenantReadinessRead",
]
