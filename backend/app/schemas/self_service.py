"""Bounded employee self-service home projection."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.announcement import AnnouncementSummaryRead
from app.schemas.employee_document import EmployeeDocumentSummaryRead
from app.schemas.notification import NotificationRead
from app.schemas.request_projection import UnifiedRequestRead


class SelfServiceWorkSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    display_name: str
    employee_number: str
    status: str
    department_name: str | None
    branch_name: str | None
    position_title: str | None
    employment_start_date: date


class SelfServiceLeaveBalance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leave_type_id: UUID
    leave_type_name: str
    period_year: int
    available_days: Decimal


class SelfServiceHomeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work: SelfServiceWorkSummary
    leave_balances: list[SelfServiceLeaveBalance]
    leave_request_path: str
    requests_path: str
    recent_requests: list[UnifiedRequestRead]
    document_summary: EmployeeDocumentSummaryRead
    announcements: list[AnnouncementSummaryRead]
    unread_notification_count: int = Field(ge=0)
    notifications: list[NotificationRead]


__all__ = [
    "SelfServiceHomeRead",
    "SelfServiceLeaveBalance",
    "SelfServiceWorkSummary",
]
