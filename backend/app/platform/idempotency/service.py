"""Transport-neutral command idempotency contracts."""

import json
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from app.platform.errors.application import ApplicationError


class IdempotencyKeyMismatchError(ApplicationError):
    """The same tenant key was already used for a different command request."""


class IdempotencyReplayUnavailableError(ApplicationError):
    """A receipt exists but cannot yet be replayed safely."""


@dataclass(frozen=True, slots=True)
class IdempotencyReplay:
    resource_id: UUID
    response_payload: dict[str, object]


def command_fingerprint(payload: dict[str, object]) -> str:
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(canonical_payload).hexdigest()
