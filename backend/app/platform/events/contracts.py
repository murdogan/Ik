"""Framework-neutral primitives for redacted platform event contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import cast
from uuid import UUID


class PlatformEventScopeType(StrEnum):
    TENANT = "tenant"


class PlatformEventActorType(StrEnum):
    """Non-identifying actor kinds accepted before Phase-2 identity/RBAC enrichment."""

    USER = "user"
    SYSTEM = "system"
    PLATFORM_ADMIN = "platform_admin"


class PlatformEventCategory(StrEnum):
    PLATFORM_OPERATIONS = "platform_operations"


class PlatformEventSeverity(StrEnum):
    INFO = "info"


class PlatformEventResult(StrEnum):
    SUCCESS = "success"


class PlatformEventDataClassification(StrEnum):
    PLATFORM_METADATA = "platform_metadata"


class PlatformEventVisibilityClass(StrEnum):
    PLATFORM_OPS = "platform_ops"


class PlatformEventContract:
    """Nominal marker for closed event models accepted by recorder adapters.

    Concrete product events inherit this marker and apply their own frozen/extra-forbid schema.
    Nominal typing prevents arbitrary structural objects with additional secret or HR attributes
    from satisfying the recorder boundary merely by copying the common property names.
    """

    __slots__ = ()

    id: UUID
    occurred_at: datetime
    tenant_id: UUID
    resource_id: UUID
    event_type: str
    actor_type: PlatformEventActorType
    actor_user_id: UUID | None
    session_id: UUID | None
    support_session_id: UUID | None
    resource_type: str
    action: str
    request_id: str
    trace_id: str
    scope_type: PlatformEventScopeType
    category: PlatformEventCategory
    severity: PlatformEventSeverity
    result: PlatformEventResult
    data_classification: PlatformEventDataClassification
    visibility_class: PlatformEventVisibilityClass


_CLOSED_EVENT_IDENTITIES = frozenset({
    ("app.modules.core.application.events", "TenantCreatedEvent"),
    ("app.modules.core.application.events", "TenantStatusChangedEvent"),
    ("app.modules.core.application.events", "TenantSettingChangedEvent"),
    ("app.modules.core.application.events", "FeatureFlagChangedEvent"),
})
_registered_event_types: dict[
    tuple[str, str],
    type[PlatformEventContract],
] = {}


def register_platform_event_contract[T: type[PlatformEventContract]](
    event_type: T,
) -> T:
    """Register one exact type from the frozen F1D event catalog."""

    identity = (event_type.__module__, event_type.__name__)
    if identity not in _CLOSED_EVENT_IDENTITIES:
        raise TypeError("Platform event type is outside the approved closed catalog")
    previous_type = _registered_event_types.setdefault(identity, event_type)
    if previous_type is not event_type:
        raise TypeError("Platform event identity is already registered")
    return event_type


def require_platform_event_contract(event: object, /) -> PlatformEventContract:
    """Accept only one of the four exact, closed F1D event model classes.

    Exact registry membership rejects the marker itself, structural lookalikes, and subclasses
    that add sensitive fields. The framework-neutral platform module never imports a product
    module; CORE registers only the four identities frozen above as each concrete class is defined.
    """

    if type(event) not in _registered_event_types.values():
        raise TypeError("Recorder requires an approved closed platform event contract")
    return cast(PlatformEventContract, event)


__all__ = [
    "PlatformEventActorType",
    "PlatformEventCategory",
    "PlatformEventContract",
    "PlatformEventDataClassification",
    "PlatformEventResult",
    "PlatformEventScopeType",
    "PlatformEventSeverity",
    "PlatformEventVisibilityClass",
    "register_platform_event_contract",
    "require_platform_event_contract",
]
