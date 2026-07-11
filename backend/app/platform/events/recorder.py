"""Replaceable recording capability for platform event contracts."""

from __future__ import annotations

from typing import Protocol

from app.platform.events.contracts import (
    PlatformEventContract,
    require_platform_event_contract,
)


class PlatformEventRecorder(Protocol):
    """Small async port that Phase 2 can implement with transactional persistence."""

    async def record(self, event: PlatformEventContract, /) -> None: ...


class DiscardingPlatformEventRecorder:
    """Phase-1 default: accept typed events without claiming audit persistence."""

    async def record(self, event: PlatformEventContract, /) -> None:
        require_platform_event_contract(event)


DEFAULT_PLATFORM_EVENT_RECORDER: PlatformEventRecorder = DiscardingPlatformEventRecorder()


__all__ = [
    "DEFAULT_PLATFORM_EVENT_RECORDER",
    "DiscardingPlatformEventRecorder",
    "PlatformEventRecorder",
]
