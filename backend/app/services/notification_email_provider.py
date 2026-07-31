"""Legacy persistence adapters for the notification email application contract."""

from __future__ import annotations

from asyncio import to_thread
from email.message import EmailMessage as StdlibEmailMessage
from smtplib import (
    SMTP,
    SMTP_SSL,
    SMTPAuthenticationError,
    SMTPConnectError,
    SMTPDataError,
    SMTPException,
    SMTPRecipientsRefused,
    SMTPSenderRefused,
    SMTPServerDisconnected,
)
from ssl import create_default_context
from typing import Literal
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


class SmtpEmailProvider:
    """Production SMTP adapter with bounded blocking work isolated from the event loop."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        from_address: str,
        username: str | None,
        password: str | None,
        tls_mode: Literal["none", "starttls", "implicit"],
        timeout_seconds: float,
    ) -> None:
        self._host = host
        self._port = port
        self._from_address = from_address
        self._username = username
        self._password = password
        self._tls_mode = tls_mode
        self._timeout_seconds = timeout_seconds

    async def send(self, message: EmailMessage, /) -> None:
        try:
            await to_thread(self._send_blocking, message)
        except SMTPRecipientsRefused as exc:
            raise EmailDeliveryError("recipient_unavailable") from exc
        except (
            SMTPAuthenticationError,
            SMTPSenderRefused,
            SMTPDataError,
        ) as exc:
            raise EmailDeliveryError("provider_rejected") from exc
        except (
            SMTPConnectError,
            SMTPServerDisconnected,
            TimeoutError,
            OSError,
        ) as exc:
            raise EmailDeliveryError("provider_unavailable") from exc
        except SMTPException as exc:
            raise EmailDeliveryError("provider_unavailable") from exc
        except (UnicodeError, ValueError) as exc:
            raise EmailDeliveryError("provider_rejected") from exc

    def _send_blocking(self, message: EmailMessage) -> None:
        outbound = self._outbound_message(message)
        if self._tls_mode == "implicit":
            context = create_default_context()
            with SMTP_SSL(
                host=self._host,
                port=self._port,
                timeout=self._timeout_seconds,
                context=context,
            ) as client:
                self._send_with_optional_authentication(client, outbound)
            return

        with SMTP(
            host=self._host,
            port=self._port,
            timeout=self._timeout_seconds,
        ) as client:
            if self._tls_mode == "starttls":
                client.starttls(context=create_default_context())
            self._send_with_optional_authentication(client, outbound)

    def _send_with_optional_authentication(
        self,
        client: SMTP,
        outbound: StdlibEmailMessage,
    ) -> None:
        if self._username is not None and self._password is not None:
            client.login(self._username, self._password)
        client.send_message(outbound)

    def _outbound_message(self, message: EmailMessage) -> StdlibEmailMessage:
        outbound = StdlibEmailMessage()
        outbound["From"] = self._from_address
        outbound["To"] = message.recipient_email
        outbound["Subject"] = message.subject
        outbound["Message-ID"] = message.message_id
        outbound["X-Idempotency-Key"] = message.idempotency_key
        outbound["Auto-Submitted"] = "auto-generated"
        outbound.set_content(message.body)
        return outbound


__all__ = [
    "EmailDeliveryError",
    "EmailMessage",
    "EmailProvider",
    "LocalCaptureEmailProvider",
    "SmtpEmailProvider",
    "UnavailableEmailProvider",
]
