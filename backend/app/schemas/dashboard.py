from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class DepartmentDistributionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department: str = Field(min_length=1, max_length=200)
    count: int = Field(ge=0)


class DashboardActivityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_type: Literal[
        "employee.created",
        "employee.updated",
        "employee.lifecycle.changed",
        "leave.requested",
        "leave.approved",
        "leave.rejected",
        "leave.cancelled",
    ]
    entity_type: Literal["employee", "leave_request"]
    entity_id: UUID
    title: str = Field(min_length=1, max_length=120)
    occurred_at: AwareDatetime


class DashboardSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["tenant", "team", "own"] = "tenant"
    active_employee_count: int = Field(ge=0)
    pending_leave_count: int = Field(ge=0)
    employee_count: int = Field(ge=0)
    pending_leave_requests: int = Field(ge=0)
    new_starters_this_month: int = Field(ge=0)
    terminated_this_month: int = Field(default=0, ge=0)
    missing_document_count: int = Field(default=0, ge=0)
    expiring_document_count: int = Field(default=0, ge=0)
    open_tasks: int = Field(ge=0)
    department_distribution: list[DepartmentDistributionItem] = Field(max_length=20)
    recent_activity: list[DashboardActivityItem] = Field(max_length=20)
