"""CORE application contracts and orchestration boundary."""

from app.modules.core.application.events import (
    FeatureFlagChangedEvent,
    InitialTenantAdminInvitationCorrectedEvent,
    InitialTenantAdminInvitationReissuedEvent,
    PlatformEvent,
    PlatformEventActorType,
    PlatformEventType,
    TenantCreatedEvent,
    TenantSettingChangedEvent,
    TenantSettingField,
    TenantStatusChangedEvent,
)

__all__ = [
    "FeatureFlagChangedEvent",
    "InitialTenantAdminInvitationCorrectedEvent",
    "InitialTenantAdminInvitationReissuedEvent",
    "PlatformEvent",
    "PlatformEventActorType",
    "PlatformEventType",
    "TenantCreatedEvent",
    "TenantSettingChangedEvent",
    "TenantSettingField",
    "TenantStatusChangedEvent",
]
