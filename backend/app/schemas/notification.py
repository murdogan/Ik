"""Current-user notification inbox contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

NOTIFICATION_LIST_DEFAULT_LIMIT = 30
NOTIFICATION_LIST_MAX_LIMIT = 100
NOTIFICATION_READ_ALL_LIMIT = 100


class NotificationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    notification_type: str
    title: str
    body: str
    portal_path: str
    read_at: datetime | None
    version: int = Field(ge=1)
    created_at: datetime


class NotificationListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NotificationRead]
    next_cursor: str | None
    unread_count: int = Field(ge=0)


class NotificationMarkRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class NotificationReadAllResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    updated_count: int = Field(ge=0, le=NOTIFICATION_READ_ALL_LIMIT)
    has_more: bool


__all__ = [
    "NOTIFICATION_LIST_DEFAULT_LIMIT",
    "NOTIFICATION_LIST_MAX_LIMIT",
    "NOTIFICATION_READ_ALL_LIMIT",
    "NotificationListRead",
    "NotificationMarkRead",
    "NotificationRead",
    "NotificationReadAllResult",
]
