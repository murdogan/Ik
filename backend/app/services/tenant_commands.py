from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.models.tenant import Tenant
from app.modules.core.application.events import (
    FeatureFlagChangedEvent,
    PlatformEventActorType,
    TenantCreatedEvent,
    TenantSettingChangedEvent,
    TenantSettingField,
    TenantStatusChangedEvent,
)
from app.modules.core.domain.tenant import TenantPlan, TenantRegion, TenantStatus
from app.platform.db import UnitOfWork
from app.platform.events import (
    DEFAULT_PLATFORM_EVENT_RECORDER,
    PlatformEventRecorder,
)
from app.platform.request_context import RequestContext
from app.schemas.tenant import (
    TenantFeaturesUpdate,
    TenantPlatformCreate,
    TenantPlatformUpdate,
    TenantSettingsUpdate,
)
from app.services.tenant_feature_service import (
    TenantFeatureService,
    TenantFeatureSnapshot,
)
from app.services.tenant_service import TenantService, TenantSettingsSnapshot

type EventIdFactory = Callable[[], UUID]
type EventTimeFactory = Callable[[], datetime]


class TenantCommandHandler:
    """Compose tenant writes and redacted event recording inside one transaction boundary."""

    def __init__(
        self,
        *,
        service: TenantService,
        unit_of_work: UnitOfWork,
        feature_service: TenantFeatureService | None = None,
        event_recorder: PlatformEventRecorder = DEFAULT_PLATFORM_EVENT_RECORDER,
        event_id_factory: EventIdFactory = uuid4,
        event_time_factory: EventTimeFactory = lambda: datetime.now(UTC),
    ) -> None:
        self.service = service
        self.feature_service = feature_service
        self.unit_of_work = unit_of_work
        self.event_recorder = event_recorder
        self.event_id_factory = event_id_factory
        self.event_time_factory = event_time_factory

    async def create_tenant(
        self,
        payload: TenantPlatformCreate,
        *,
        request_context: RequestContext,
    ) -> Tenant:
        async def operation() -> Tenant:
            tenant = await self.service.create_tenant(payload)
            await self.event_recorder.record(
                TenantCreatedEvent(
                    **self._event_metadata(
                        tenant.id,
                        request_context,
                        actor_type=PlatformEventActorType.PLATFORM_ADMIN,
                    ),
                    status=TenantStatus(tenant.status),
                    plan_code=TenantPlan(tenant.plan_code),
                    data_region=TenantRegion(tenant.data_region),
                )
            )
            return tenant

        return await self.unit_of_work.execute(operation)

    async def update_tenant(
        self,
        tenant_id: UUID,
        payload: TenantPlatformUpdate,
        *,
        request_context: RequestContext,
    ) -> Tenant:
        async def operation() -> Tenant:
            mutation = await self.service.update_tenant_with_changes(tenant_id, payload)
            if "status" in mutation.changed_fields:
                await self.event_recorder.record(
                    TenantStatusChangedEvent(
                        **self._event_metadata(
                            tenant_id,
                            request_context,
                            actor_type=PlatformEventActorType.PLATFORM_ADMIN,
                        ),
                        before_status=mutation.previous_status,
                        after_status=TenantStatus(mutation.tenant.status),
                    )
                )
            setting_fields = tuple(
                TenantSettingField(field_name)
                for field_name in mutation.changed_fields
                if field_name != "status"
            )
            if setting_fields:
                await self.event_recorder.record(
                    TenantSettingChangedEvent(
                        **self._event_metadata(
                            tenant_id,
                            request_context,
                            actor_type=PlatformEventActorType.PLATFORM_ADMIN,
                        ),
                        changed_fields=setting_fields,
                    )
                )
            return mutation.tenant

        return await self.unit_of_work.execute(operation)

    async def update_tenant_settings(
        self,
        tenant_id: UUID,
        payload: TenantSettingsUpdate,
        *,
        request_context: RequestContext,
    ) -> TenantSettingsSnapshot:
        async def operation() -> TenantSettingsSnapshot:
            mutation = await self.service.update_tenant_settings_with_changes(
                tenant_id,
                payload,
            )
            if mutation.changed_fields:
                await self.event_recorder.record(
                    TenantSettingChangedEvent(
                        **self._event_metadata(
                            tenant_id,
                            request_context,
                            actor_type=PlatformEventActorType.USER,
                        ),
                        changed_fields=tuple(
                            TenantSettingField(field_name)
                            for field_name in mutation.changed_fields
                        ),
                    )
                )
            return mutation.settings

        return await self.unit_of_work.execute(operation)

    async def update_tenant_features(
        self,
        tenant_id: UUID,
        payload: TenantFeaturesUpdate,
        *,
        request_context: RequestContext,
    ) -> tuple[TenantFeatureSnapshot, ...]:
        if self.feature_service is None:
            raise RuntimeError("Tenant feature service is required for feature commands")

        async def operation() -> tuple[TenantFeatureSnapshot, ...]:
            mutation = await self.feature_service.update_tenant_features(
                tenant_id,
                payload,
            )
            for change in mutation.changes:
                await self.event_recorder.record(
                    FeatureFlagChangedEvent(
                        **self._event_metadata(
                            tenant_id,
                            request_context,
                            actor_type=PlatformEventActorType.PLATFORM_ADMIN,
                        ),
                        feature_key=change.key,
                        before_enabled=change.previous_enabled,
                        after_enabled=change.enabled,
                    )
                )
            return mutation.features

        return await self.unit_of_work.execute(operation)

    def _event_metadata(
        self,
        tenant_id: UUID,
        request_context: RequestContext,
        *,
        actor_type: PlatformEventActorType,
    ) -> dict[str, object]:
        return {
            "id": self.event_id_factory(),
            "occurred_at": self.event_time_factory(),
            "tenant_id": tenant_id,
            "resource_id": tenant_id,
            "actor_type": actor_type,
            "actor_user_id": request_context.actor_id,
            "session_id": request_context.session_id,
            "support_session_id": (
                request_context.support_session.support_session_id
                if request_context.support_session is not None
                else None
            ),
            "request_id": request_context.request_id,
            "trace_id": request_context.trace_id,
        }
