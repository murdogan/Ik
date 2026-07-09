from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, EmployeeStatus
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.schemas.dashboard import (
    DashboardActivityItem,
    DashboardSummary,
    DepartmentDistributionItem,
)

CURRENT_EMPLOYEE_STATUSES = [
    EmployeeStatus.ACTIVE.value,
    EmployeeStatus.ON_LEAVE.value,
]

LEAVE_ACTIVITY_BY_STATUS = {
    LeaveRequestStatus.PENDING.value: "leave.requested",
    LeaveRequestStatus.APPROVED.value: "leave.approved",
    LeaveRequestStatus.REJECTED.value: "leave.rejected",
    LeaveRequestStatus.CANCELLED.value: "leave.cancelled",
}


class DashboardService:
    def __init__(
        self,
        session: AsyncSession,
        today: date | None = None,
        recent_activity_limit: int = 5,
    ) -> None:
        self.session = session
        self.today = today or date.today()
        self.recent_activity_limit = max(recent_activity_limit, 0)

    async def get_summary(self, tenant_id: UUID) -> DashboardSummary:
        active_employee_count = await self._count_active_employees(tenant_id)
        employee_count = await self._count_current_employees(tenant_id)
        pending_leave_count = await self._count_pending_leave_requests(tenant_id)
        new_starters_this_month = await self._count_new_starters_this_month(tenant_id)
        department_distribution = await self._department_distribution(tenant_id)
        recent_activity = await self._recent_activity(tenant_id)

        return DashboardSummary(
            active_employee_count=active_employee_count,
            pending_leave_count=pending_leave_count,
            employee_count=employee_count,
            pending_leave_requests=pending_leave_count,
            new_starters_this_month=new_starters_this_month,
            open_tasks=0,
            department_distribution=department_distribution,
            recent_activity=recent_activity,
        )

    async def _count_active_employees(self, tenant_id: UUID) -> int:
        return await self._scalar_count(_active_employee_count_statement(tenant_id))

    async def _count_current_employees(self, tenant_id: UUID) -> int:
        return await self._scalar_count(_current_employee_count_statement(tenant_id))

    async def _count_pending_leave_requests(self, tenant_id: UUID) -> int:
        return await self._scalar_count(_pending_leave_count_statement(tenant_id))

    async def _count_new_starters_this_month(self, tenant_id: UUID) -> int:
        start_date, end_date = _month_window(self.today)
        return await self._scalar_count(
            _new_starters_count_statement(
                tenant_id=tenant_id,
                start_date=start_date,
                end_date=end_date,
            )
        )

    async def _department_distribution(self, tenant_id: UUID) -> list[DepartmentDistributionItem]:
        rows = (
            await self.session.execute(_department_distribution_statement(tenant_id))
        ).mappings().all()
        return [_department_distribution_item(row) for row in rows]

    async def _recent_activity(self, tenant_id: UUID) -> list[DashboardActivityItem]:
        if self.recent_activity_limit == 0:
            return []

        activity = [
            *await self._recent_employee_activity(tenant_id),
            *await self._recent_leave_activity(tenant_id),
        ]
        return sorted(activity, key=_activity_timestamp, reverse=True)[
            : self.recent_activity_limit
        ]

    async def _recent_employee_activity(self, tenant_id: UUID) -> list[DashboardActivityItem]:
        rows = (
            await self.session.execute(
                _recent_employee_activity_statement(
                    tenant_id=tenant_id,
                    limit=self.recent_activity_limit,
                )
            )
        ).mappings().all()
        activity_items = []
        for row in rows:
            activity_item = _employee_activity_item(row)
            if activity_item is not None:
                activity_items.append(activity_item)
        return activity_items

    async def _recent_leave_activity(self, tenant_id: UUID) -> list[DashboardActivityItem]:
        rows = (
            await self.session.execute(
                _recent_leave_activity_statement(
                    tenant_id=tenant_id,
                    limit=self.recent_activity_limit,
                )
            )
        ).mappings().all()
        activity_items = []
        for row in rows:
            activity_item = _leave_activity_item(row)
            if activity_item is not None:
                activity_items.append(activity_item)
        return activity_items

    async def _scalar_count(self, statement) -> int:
        value = await self.session.scalar(statement)
        return int(value or 0)


def _month_window(today: date) -> tuple[date, date]:
    start_date = date(today.year, today.month, 1)
    if today.month == 12:
        return start_date, date(today.year + 1, 1, 1)
    return start_date, date(today.year, today.month + 1, 1)


def _active_employee_count_statement(tenant_id: UUID):
    return (
        select(func.count(Employee.id))
        .where(Employee.tenant_id == tenant_id)
        .where(Employee.status == EmployeeStatus.ACTIVE.value)
    )


def _current_employee_count_statement(tenant_id: UUID):
    return (
        select(func.count(Employee.id))
        .where(Employee.tenant_id == tenant_id)
        .where(Employee.status.in_(CURRENT_EMPLOYEE_STATUSES))
    )


def _pending_leave_count_statement(tenant_id: UUID):
    return (
        select(func.count(LeaveRequest.id))
        .where(LeaveRequest.tenant_id == tenant_id)
        .where(LeaveRequest.status == LeaveRequestStatus.PENDING.value)
    )


def _new_starters_count_statement(tenant_id: UUID, start_date: date, end_date: date):
    return (
        select(func.count(Employee.id))
        .where(Employee.tenant_id == tenant_id)
        .where(Employee.status.in_(CURRENT_EMPLOYEE_STATUSES))
        .where(Employee.employment_start_date >= start_date)
        .where(Employee.employment_start_date < end_date)
    )


def _department_distribution_statement(tenant_id: UUID):
    department_label = _department_label()
    employee_count = func.count(Employee.id)
    return (
        select(
            department_label.label("department"),
            employee_count.label("employee_count"),
        )
        .where(Employee.tenant_id == tenant_id)
        .where(Employee.status.in_(CURRENT_EMPLOYEE_STATUSES))
        .group_by(department_label)
        .order_by(employee_count.desc(), department_label.asc())
    )


def _department_label():
    return func.coalesce(
        func.nullif(func.trim(Employee.department), ""),
        "Unassigned",
    )


def _recent_employee_activity_statement(tenant_id: UUID, limit: int):
    return (
        select(
            Employee.id.label("entity_id"),
            Employee.first_name,
            Employee.last_name,
            Employee.created_at.label("occurred_at"),
        )
        .where(Employee.tenant_id == tenant_id)
        .order_by(Employee.created_at.desc())
        .limit(limit)
    )


def _recent_leave_activity_statement(tenant_id: UUID, limit: int):
    return (
        select(
            LeaveRequest.id.label("entity_id"),
            LeaveRequest.status,
            LeaveRequest.leave_type,
            LeaveRequest.created_at.label("occurred_at"),
            Employee.first_name,
            Employee.last_name,
        )
        .join(Employee, Employee.id == LeaveRequest.employee_id)
        .where(LeaveRequest.tenant_id == tenant_id)
        .where(Employee.tenant_id == tenant_id)
        .order_by(LeaveRequest.created_at.desc())
        .limit(limit)
    )


def _department_distribution_item(row) -> DepartmentDistributionItem:
    return DepartmentDistributionItem(
        department=row["department"],
        count=row["employee_count"],
    )


def _employee_activity_item(row) -> DashboardActivityItem | None:
    occurred_at = row["occurred_at"]
    if not isinstance(occurred_at, datetime):
        return None
    return DashboardActivityItem(
        activity_type="employee.created",
        entity_type="employee",
        entity_id=row["entity_id"],
        title=f"{row['first_name']} {row['last_name']} employee profile created",
        occurred_at=occurred_at,
    )


def _leave_activity_item(row) -> DashboardActivityItem | None:
    activity_type = LEAVE_ACTIVITY_BY_STATUS.get(row["status"])
    occurred_at = row["occurred_at"]
    if activity_type is None or not isinstance(occurred_at, datetime):
        return None
    return DashboardActivityItem(
        activity_type=activity_type,
        entity_type="leave_request",
        entity_id=row["entity_id"],
        title=(
            f"{row['first_name']} {row['last_name']} "
            f"{row['leave_type']} leave request {row['status']}"
        ),
        occurred_at=occurred_at,
    )


def _activity_timestamp(activity: DashboardActivityItem) -> float:
    return activity.occurred_at.timestamp()
