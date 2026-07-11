"""Deterministic platform-event recorder for command and contract tests."""

from __future__ import annotations

from app.platform.events.contracts import (
    PlatformEventContract,
    require_platform_event_contract,
)


class RecordingPlatformEventRecorder:
    """In-memory test adapter that exposes an immutable event snapshot."""

    def __init__(self) -> None:
        self._events: list[PlatformEventContract] = []

    @property
    def events(self) -> tuple[PlatformEventContract, ...]:
        return tuple(self._events)

    async def record(self, event: PlatformEventContract, /) -> None:
        self._events.append(require_platform_event_contract(event))


__all__ = ["RecordingPlatformEventRecorder"]
