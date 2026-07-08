from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DepartmentDistributionItem(BaseModel):
    department: str
    count: int


class DashboardActivityItem(BaseModel):
    activity_type: str
    entity_type: str
    entity_id: UUID
    title: str
    occurred_at: datetime


class DashboardSummary(BaseModel):
    employee_count: int
    pending_leave_requests: int
    new_starters_this_month: int
    open_tasks: int
    department_distribution: list[DepartmentDistributionItem]
    recent_activity: list[DashboardActivityItem]
