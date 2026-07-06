from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


class DepartmentDistributionItem(BaseModel):
    department: str
    count: int


class DashboardSummary(BaseModel):
    employee_count: int
    pending_leave_requests: int
    new_starters_this_month: int
    open_tasks: int
    department_distribution: list[DepartmentDistributionItem]


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary() -> DashboardSummary:
    return DashboardSummary(
        employee_count=42,
        pending_leave_requests=6,
        new_starters_this_month=3,
        open_tasks=8,
        department_distribution=[
            DepartmentDistributionItem(department="Sales", count=12),
            DepartmentDistributionItem(department="Operations", count=9),
        ],
    )
