"""Persist the closed Phase-1 platform event catalog as F2E audit events."""

from __future__ import annotations

from app.modules.core.application.events import (
    FeatureFlagChangedEvent,
    TenantCreatedEvent,
    TenantSettingChangedEvent,
    TenantStatusChangedEvent,
)
from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditRecorder,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.events import PlatformEventActorType, PlatformEventContract
from app.platform.events.contracts import require_platform_event_contract


class PlatformEventAuditRecorder:
    """Translate only the exact existing event types into the persistent audit vocabulary."""

    def __init__(self, recorder: AuditRecorder) -> None:
        self._recorder = recorder

    async def record(self, raw_event: PlatformEventContract, /) -> None:
        event = require_platform_event_contract(raw_event)
        is_tenant_actor = event.actor_type is PlatformEventActorType.USER
        metadata: dict[str, object] = {}
        changed_fields: tuple[str, ...] = ()

        if type(event) is TenantCreatedEvent:
            event_type = AuditEventType.PLATFORM_TENANT_CREATED
            metadata = {
                "status": event.status.value,  # type: ignore[attr-defined]
                "plan_code": event.plan_code.value,  # type: ignore[attr-defined]
                "data_region": event.data_region.value,  # type: ignore[attr-defined]
            }
        elif type(event) is TenantStatusChangedEvent:
            event_type = AuditEventType.PLATFORM_TENANT_STATUS_CHANGED
            metadata = {
                "before_status": event.before_status.value,  # type: ignore[attr-defined]
                "after_status": event.after_status.value,  # type: ignore[attr-defined]
            }
            changed_fields = ("status",)
        elif type(event) is TenantSettingChangedEvent:
            event_type = (
                AuditEventType.TENANT_SETTING_CHANGED
                if is_tenant_actor
                else AuditEventType.PLATFORM_TENANT_SETTING_CHANGED
            )
            changed_fields = tuple(  # type: ignore[attr-defined]
                field.value for field in event.changed_fields
            )
        elif type(event) is FeatureFlagChangedEvent:
            event_type = AuditEventType.PLATFORM_FEATURE_FLAG_CHANGED
            metadata = {
                "feature_key": event.feature_key.value,  # type: ignore[attr-defined]
                "before_enabled": event.before_enabled,  # type: ignore[attr-defined]
                "after_enabled": event.after_enabled,  # type: ignore[attr-defined]
            }
            changed_fields = ("enabled",)
        else:  # pragma: no cover - exact registry already guards this invariant
            raise TypeError("Unsupported platform event contract")

        await self._recorder.record(
            AuditEventDraft(
                id=event.id,
                occurred_at=event.occurred_at,
                scope_type=(
                    AuditScopeType.TENANT if is_tenant_actor else AuditScopeType.PLATFORM
                ),
                tenant_id=event.tenant_id if is_tenant_actor else None,
                actor_type=(
                    AuditActorType.USER
                    if is_tenant_actor
                    else AuditActorType.PLATFORM_ADMIN
                ),
                actor_user_id=event.actor_user_id,
                session_id=event.session_id,
                event_type=event_type,
                category=(
                    AuditCategory.TENANT_ADMIN
                    if is_tenant_actor
                    else AuditCategory.PLATFORM_OPERATIONS
                ),
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                action=event.action,
                context=AuditContext(
                    request_id=event.request_id,
                    trace_id=event.trace_id,
                ),
                changed_fields=changed_fields,
                metadata=metadata,
                data_classification=(
                    AuditDataClassification.TENANT_ADMINISTRATION
                    if is_tenant_actor
                    else AuditDataClassification.PLATFORM_METADATA
                ),
                visibility_class=(
                    AuditVisibilityClass.TENANT_ADMIN
                    if is_tenant_actor
                    else AuditVisibilityClass.PLATFORM_OPS
                ),
            )
        )


__all__ = ["PlatformEventAuditRecorder"]
