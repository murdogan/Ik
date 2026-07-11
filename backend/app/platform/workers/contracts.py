from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from app.platform.request_context import (
    AuthenticationStrength,
    WorkerRequestContext,
    is_valid_request_id,
    is_valid_trace_id,
)

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
    request_context: Mapping[str, JsonValue] | None = None
    _payload_json: str = field(init=False, repr=False, compare=False)
    _request_context_json: str | None = field(init=False, repr=False, compare=False)

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
            if not is_valid_request_id(self.correlation_id):
                raise ValueError("correlation_id must be a safe opaque request identifier")
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

        request_context_json = _canonical_request_context_json(
            self.request_context,
            tenant_id=self.tenant_id,
            correlation_id=self.correlation_id,
        )
        if request_context_json is None:
            object.__setattr__(self, "_request_context_json", None)
        else:
            canonical_context = json.loads(request_context_json)
            object.__setattr__(self, "request_context", _freeze_json(canonical_context))
            object.__setattr__(self, "_request_context_json", request_context_json)

    def payload_for_transport(self) -> dict[str, JsonValue]:
        """Return a fresh mutable JSON object for a provider adapter to serialize."""

        payload = json.loads(self._payload_json)
        if not isinstance(payload, dict):  # pragma: no cover - protected by construction
            raise RuntimeError("canonical job payload is not an object")
        return payload

    def request_context_for_transport(self) -> WorkerRequestContext | None:
        """Return a fresh JSON-safe context allowlist for the provider adapter."""

        if self._request_context_json is None:
            return None
        context = json.loads(self._request_context_json)
        if not isinstance(context, dict):  # pragma: no cover - protected by construction
            raise RuntimeError("canonical request context is not an object")
        return context  # type: ignore[return-value]


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


_WORKER_CONTEXT_KEYS = frozenset(WorkerRequestContext.__required_keys__)
_OPTIONAL_WORKER_UUID_FIELDS = (
    "actor_id",
    "session_id",
    "support_session_id",
    "support_operator_actor_id",
)


def _canonical_request_context_json(
    context: Mapping[str, JsonValue] | None,
    *,
    tenant_id: UUID,
    correlation_id: str | None,
) -> str | None:
    if context is None:
        return None
    if not isinstance(context, Mapping) or set(context) != _WORKER_CONTEXT_KEYS:
        raise ValueError("request_context must contain only the safe worker context allowlist")
    try:
        canonical_json = json.dumps(
            dict(context),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        canonical = json.loads(canonical_json)
    except (TypeError, ValueError) as exc:
        raise ValueError("request_context must be a JSON-safe worker context") from exc
    if not isinstance(canonical, dict):  # pragma: no cover - mapping input guard
        raise ValueError("request_context must be a JSON object")

    request_id = canonical["request_id"]
    trace_id = canonical["trace_id"]
    if not is_valid_request_id(request_id) or not is_valid_trace_id(trace_id):
        raise ValueError("request_context contains invalid correlation identifiers")
    context_tenant_id = _context_uuid("tenant_id", canonical["tenant_id"])
    if context_tenant_id != tenant_id:
        raise ValueError("request_context tenant_id must match the job tenant_id")
    for field_name in _OPTIONAL_WORKER_UUID_FIELDS:
        value = canonical[field_name]
        if value is not None:
            _context_uuid(field_name, value)
    if (
        canonical["support_operator_actor_id"] is not None
        and canonical["support_session_id"] is None
    ):
        raise ValueError("support operator context requires support_session_id")
    try:
        AuthenticationStrength(canonical["authentication_strength"])
    except (TypeError, ValueError) as exc:
        raise ValueError("request_context authentication_strength is invalid") from exc
    if correlation_id is not None and correlation_id != request_id:
        raise ValueError("correlation_id must match request_context request_id")
    return canonical_json


def _context_uuid(field_name: str, value: object) -> UUID:
    try:
        parsed = UUID(value) if isinstance(value, str) else None
    except ValueError as exc:
        raise ValueError(f"request_context {field_name} must be a non-zero UUID") from exc
    if parsed is None or parsed.int == 0 or str(parsed) != value:
        raise ValueError(f"request_context {field_name} must be a canonical non-zero UUID")
    return parsed
