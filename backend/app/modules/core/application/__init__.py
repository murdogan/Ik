"""CORE application contracts and orchestration boundary."""

from app.modules.core.application.events import (
    FeatureFlagChangedEvent,
    InitialTenantAdminInvitationCorrectedEvent,
    InitialTenantAdminInvitationReissuedEvent,
    InitialTenantAdminManualLinkIssuedEvent,
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
    "InitialTenantAdminManualLinkIssuedEvent",
    "InitialTenantAdminInvitationReissuedEvent",
    "PlatformEvent",
    "PlatformEventActorType",
    "PlatformEventType",
    "TenantCreatedEvent",
    "TenantSettingChangedEvent",
    "TenantSettingField",
    "TenantStatusChangedEvent",
]
