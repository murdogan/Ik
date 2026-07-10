from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type FrozenJsonValue = (
    None
    | bool
    | int
    | float
    | str
    | tuple[FrozenJsonValue, ...]
    | Mapping[str, FrozenJsonValue]
)


@dataclass(frozen=True, slots=True)
class JobSpec:
    """Provider-neutral job envelope with mandatory operational safeguards."""

    task_name: str
    tenant_id: UUID
    idempotency_key: str
    payload: Mapping[str, JsonValue]
    timeout_seconds: int
    max_attempts: int
    queue: str = "default"
    correlation_id: str | None = None
    _payload_json: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_token("task_name", self.task_name, maximum_length=100)
        _require_token("queue", self.queue, maximum_length=50)
        _require_token("idempotency_key", self.idempotency_key, maximum_length=128)
        if not isinstance(self.tenant_id, UUID) or self.tenant_id.int == 0:
            raise ValueError("tenant_id must be a non-zero UUID")
        if (
            not isinstance(self.timeout_seconds, int)
            or isinstance(self.timeout_seconds, bool)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive integer")
        if (
            not isinstance(self.max_attempts, int)
            or isinstance(self.max_attempts, bool)
            or self.max_attempts <= 0
        ):
            raise ValueError("max_attempts must be a positive integer")
        if self.correlation_id is not None:
            _require_token("correlation_id", self.correlation_id, maximum_length=128)
        if not isinstance(self.payload, Mapping):
            raise ValueError("payload must be a JSON object with finite JSON values")

        try:
            payload_json = json.dumps(
                dict(self.payload),
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            canonical_payload = json.loads(payload_json)
        except (TypeError, ValueError) as exc:
            raise ValueError("payload must be a JSON object with finite JSON values") from exc
        if not isinstance(canonical_payload, dict):
            raise ValueError("payload must be a JSON object")
        object.__setattr__(self, "payload", _freeze_json(canonical_payload))
        object.__setattr__(self, "_payload_json", payload_json)

    def payload_for_transport(self) -> dict[str, JsonValue]:
        """Return a fresh mutable JSON object for a provider adapter to serialize."""

        payload = json.loads(self._payload_json)
        if not isinstance(payload, dict):  # pragma: no cover - protected by construction
            raise RuntimeError("canonical job payload is not an object")
        return payload


@dataclass(frozen=True, slots=True)
class QueuedJob:
    id: str
    queue: str


class JobQueue(Protocol):
    """Small enqueue capability implemented by a later worker-provider adapter."""

    async def enqueue(self, job: JobSpec, /) -> QueuedJob: ...


def _require_token(field_name: str, value: str, *, maximum_length: int) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty and have no surrounding whitespace")
    if len(value) > maximum_length:
        raise ValueError(f"{field_name} must be at most {maximum_length} characters")


def _freeze_json(value: JsonValue) -> FrozenJsonValue:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value
