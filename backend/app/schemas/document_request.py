"""Fixed employee document-request command and read contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.document_request import (
    EmployeeDocumentRequestStatus,
    EmployeeDocumentRequestType,
)

DOCUMENT_REQUEST_LIST_DEFAULT_LIMIT = 30
DOCUMENT_REQUEST_LIST_MAX_LIMIT = 100


class EmployeeDocumentRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_type: EmployeeDocumentRequestType


class EmployeeDocumentRequestDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized or any(ord(character) < 32 for character in normalized):
            raise ValueError("A plain-text resolution reason is required")
        return normalized


class EmployeeDocumentRequestTimelineRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EmployeeDocumentRequestStatus
    status: EmployeeDocumentRequestStatus
    occurred_at: datetime


class EmployeeDocumentRequestRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    employee_id: UUID
    employee_name: str | None = None
    request_type: EmployeeDocumentRequestType
    status: EmployeeDocumentRequestStatus
    version: int = Field(ge=1)
    resolution_reason: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime
    timeline: list[EmployeeDocumentRequestTimelineRead] = Field(default_factory=list)


__all__ = [
    "DOCUMENT_REQUEST_LIST_DEFAULT_LIMIT",
    "DOCUMENT_REQUEST_LIST_MAX_LIMIT",
    "EmployeeDocumentRequestCreate",
    "EmployeeDocumentRequestDecision",
    "EmployeeDocumentRequestRead",
    "EmployeeDocumentRequestTimelineRead",
]
