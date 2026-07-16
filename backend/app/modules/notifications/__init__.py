"""User-visible notification policy and delivery-state boundary."""

from app.modules.notifications.email import (
    EmailDeliveryError,
    EmailMessage,
    EmailProvider,
    LocalCaptureEmailProvider,
    UnavailableEmailProvider,
)

__all__ = [
    "EmailDeliveryError",
    "EmailMessage",
    "EmailProvider",
    "LocalCaptureEmailProvider",
    "UnavailableEmailProvider",
]
