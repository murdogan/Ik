"""Legacy persistence adapters for the notification email application contract."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import EmailCapture
from app.modules.notifications.application.email import (
    EmailDeliveryError,
    EmailMessage,
    EmailProvider,
)


class UnavailableEmailProvider:
    async def send(self, message: EmailMessage, /) -> None:
        del message
        raise EmailDeliveryError("provider_unavailable")


class LocalCaptureEmailProvider:
    """Development/staging adapter; capture insert is idempotent and transactional."""

    def __init__(self, session: AsyncSession, *, failures_before_success: int = 0) -> None:
        self.session = session
        self.failures_before_success = failures_before_success

    async def send(self, message: EmailMessage, /) -> None:
        if message.attempt_number <= self.failures_before_success:
            raise EmailDeliveryError("provider_rejected")
        existing = await self.session.scalar(
            select(EmailCapture.id).where(
                EmailCapture.tenant_id == message.tenant_id,
                EmailCapture.idempotency_key == message.idempotency_key,
            )
        )
        if existing is not None:
            return
        try:
            async with self.session.begin_nested():
                self.session.add(
                    EmailCapture(
                        id=uuid5(
                            NAMESPACE_URL,
                            f"wealthy-falcon:email-capture:{message.tenant_id}:"
                            f"{message.idempotency_key}",
                        ),
                        tenant_id=message.tenant_id,
                        delivery_id=message.delivery_id,
                        recipient_user_id=message.recipient_user_id,
                        recipient_email=message.recipient_email,
                        subject=message.subject,
                        body=message.body,
                        portal_url=message.portal_url,
                        idempotency_key=message.idempotency_key,
                    )
                )
                await self.session.flush()
        except Exception as exc:
            raise EmailDeliveryError("capture_failed") from exc


__all__ = [
    "EmailDeliveryError",
    "EmailMessage",
    "EmailProvider",
    "LocalCaptureEmailProvider",
    "UnavailableEmailProvider",
]
