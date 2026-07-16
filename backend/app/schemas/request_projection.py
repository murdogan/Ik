"""Fixed normalized projection across leave, profile-change, and document requests."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

REQUEST_LIST_DEFAULT_LIMIT = 30
REQUEST_LIST_MAX_LIMIT = 100


class UnifiedRequestKind(StrEnum):
    LEAVE = "leave"
    PROFILE_CHANGE = "profile_change"
    DOCUMENT = "document"


class UnifiedRequestTimelineRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    status: str
    occurred_at: datetime


class UnifiedRequestRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    kind: UnifiedRequestKind
    status: str
    title: str
    requester_employee_id: UUID
    requester_name: str | None = None
    submitted_at: datetime
    updated_at: datetime
    version: int = Field(ge=1)
    start_date: date | None = None
    end_date: date | None = None
    counted_days: Decimal | None = None
    changed_fields: tuple[str, ...] = ()
    document_request_type: str | None = None
    timeline: list[UnifiedRequestTimelineRead] = Field(default_factory=list)


__all__ = [
    "REQUEST_LIST_DEFAULT_LIMIT",
    "REQUEST_LIST_MAX_LIMIT",
    "UnifiedRequestKind",
    "UnifiedRequestRead",
    "UnifiedRequestTimelineRead",
]
