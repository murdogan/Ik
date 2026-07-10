"""Small, versioned cursor codec shared by high-growth read paths."""

from base64 import b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from collections.abc import Mapping
from dataclasses import dataclass
from json import JSONDecodeError, dumps, loads
from typing import Any

CURSOR_VERSION = 1
MAX_CURSOR_LENGTH = 2048
NEXT_CURSOR_HEADER = "X-Next-Cursor"


class InvalidCursorError(ValueError):
    pass


@dataclass(frozen=True)
class CursorPage[T]:
    items: list[T]
    next_cursor: str | None


def encode_cursor(resource: str, values: Mapping[str, str]) -> str:
    payload = {
        "resource": resource,
        "values": dict(values),
        "version": CURSOR_VERSION,
    }
    encoded = urlsafe_b64encode(
        dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return encoded.rstrip(b"=").decode("ascii")


def decode_cursor(token: str, *, expected_resource: str) -> dict[str, str]:
    if not token or len(token) > MAX_CURSOR_LENGTH:
        raise InvalidCursorError

    try:
        padding = "=" * (-len(token) % 4)
        decoded = b64decode(f"{token}{padding}", altchars=b"-_", validate=True)
        payload: Any = loads(decoded)
    except (Base64Error, JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise InvalidCursorError from exc

    if not isinstance(payload, dict) or set(payload) != {"resource", "values", "version"}:
        raise InvalidCursorError
    if (
        type(payload["version"]) is not int
        or payload["version"] != CURSOR_VERSION
        or payload["resource"] != expected_resource
    ):
        raise InvalidCursorError

    values = payload["values"]
    if not isinstance(values, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in values.items()
    ):
        raise InvalidCursorError
    return values
