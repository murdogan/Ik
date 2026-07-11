"""Framework-neutral platform event primitives; persistence remains a Phase-2 concern."""

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
    require_platform_event_contract,
)
from app.platform.events.fake import RecordingPlatformEventRecorder
from app.platform.events.recorder import (
    DEFAULT_PLATFORM_EVENT_RECORDER,
    DiscardingPlatformEventRecorder,
    PlatformEventRecorder,
)

__all__ = [
    "DEFAULT_PLATFORM_EVENT_RECORDER",
    "DiscardingPlatformEventRecorder",
    "PlatformEventActorType",
    "PlatformEventCategory",
    "PlatformEventContract",
    "PlatformEventDataClassification",
    "PlatformEventRecorder",
    "PlatformEventResult",
    "PlatformEventScopeType",
    "PlatformEventSeverity",
    "PlatformEventVisibilityClass",
    "RecordingPlatformEventRecorder",
    "register_platform_event_contract",
    "require_platform_event_contract",
]
