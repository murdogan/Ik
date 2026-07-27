"""Provider-neutral email delivery contract and safe failure vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class EmailDeliveryError(Exception):
    """Only a fixed safe code/message may cross into terminal delivery metadata."""

    _SAFE_MESSAGES = {
        "provider_unavailable": "Outbound email provider is not configured",
        "provider_rejected": "Email provider rejected delivery",
        "recipient_unavailable": "Email recipient is unavailable",
        "capture_failed": "Local email capture failed",
    }

    def __init__(self, code: str) -> None:
        if code not in self._SAFE_MESSAGES:
            raise ValueError("Unsupported email delivery error code")
        self.code = code
        self.safe_message = self._SAFE_MESSAGES[code]
        super().__init__(self.safe_message)


@dataclass(frozen=True, slots=True)
class EmailMessage:
    tenant_id: UUID
    delivery_id: UUID
    recipient_user_id: UUID
    recipient_email: str
    subject: str
    body: str
    portal_url: str
    idempotency_key: str
    attempt_number: int


class EmailProvider(Protocol):
    async def send(self, message: EmailMessage, /) -> None: ...


__all__ = ["EmailDeliveryError", "EmailMessage", "EmailProvider"]
