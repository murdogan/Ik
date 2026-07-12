"""Safe read models and cursor state for audit explorers."""

from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.platform.audit import AuditCategory, AuditResult, AuditScopeType
from app.platform.pagination import decode_cursor, encode_cursor

AUDIT_LIST_DEFAULT_LIMIT = 25
AUDIT_LIST_MAX_LIMIT = 100
AUDIT_EVENT_TYPE_MAX_LENGTH = 128

type AuditMetadataScalar = str | int | bool | None
type AuditMetadataValue = AuditMetadataScalar | list[AuditMetadataScalar]


class AuditEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    occurred_at: AwareDatetime
    scope_type: AuditScopeType
    tenant_id: UUID | None
    actor_type: str
    actor_user_id: UUID | None
    impersonator_user_id: UUID | None
    event_type: str
    category: AuditCategory
    severity: str
    resource_type: str | None
    resource_id: UUID | None
    action: str
    result: AuditResult
    request_id: str
    trace_id: str
    session_id: UUID | None
    ip_address: str | None
    user_agent: str | None
    reason: str | None
    support_ticket_id: str | None
    changed_fields: list[str]
    before_data: dict[str, AuditMetadataValue]
    after_data: dict[str, AuditMetadataValue]
    metadata: dict[str, AuditMetadataValue]
    data_classification: str
    visibility_class: str


class AuditListCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    occurred_at: AwareDatetime
    id: UUID
    scope_type: AuditScopeType
    category: str = ""
    event_type: str = ""
    result: str = ""

    def to_token(self) -> str:
        return encode_cursor(
            "audit_events",
            {
                "occurred_at": self.occurred_at.isoformat(),
                "id": str(self.id),
                "scope_type": self.scope_type.value,
                "category": self.category,
                "event_type": self.event_type,
                "result": self.result,
            },
        )

    @classmethod
    def from_token(cls, token: str) -> Self:
        values = decode_cursor(token, expected_resource="audit_events")
        if set(values) != {
            "occurred_at",
            "id",
            "scope_type",
            "category",
            "event_type",
            "result",
        }:
            raise ValueError("Invalid audit cursor fields")
        return cls(
            occurred_at=values["occurred_at"],
            id=values["id"],
            scope_type=values["scope_type"],
            category=values["category"],
            event_type=values["event_type"],
            result=values["result"],
        )


class AuditListPagination(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(default=AUDIT_LIST_DEFAULT_LIMIT, ge=1, le=AUDIT_LIST_MAX_LIMIT)
    cursor: AuditListCursor | None = None
    scope_type: AuditScopeType
    category: AuditCategory | None = None
    event_type: str | None = Field(default=None, min_length=3, max_length=128)
    result: AuditResult | None = None

    def cursor_matches_filters(self) -> bool:
        if self.cursor is None:
            return True
        return (
            self.cursor.scope_type is self.scope_type
            and self.cursor.category == (self.category.value if self.category else "")
            and self.cursor.event_type == (self.event_type or "")
            and self.cursor.result == (self.result.value if self.result else "")
        )

    def next_cursor(self, *, occurred_at: datetime, event_id: UUID) -> str:
        return AuditListCursor(
            occurred_at=occurred_at,
            id=event_id,
            scope_type=self.scope_type,
            category=self.category.value if self.category else "",
            event_type=self.event_type or "",
            result=self.result.value if self.result else "",
        ).to_token()


__all__ = [
    "AUDIT_EVENT_TYPE_MAX_LENGTH",
    "AUDIT_LIST_DEFAULT_LIMIT",
    "AUDIT_LIST_MAX_LIMIT",
    "AuditEventRead",
    "AuditListCursor",
    "AuditListPagination",
]
