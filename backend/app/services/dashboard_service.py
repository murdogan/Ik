from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import and_, func, select
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


@dataclass(frozen=True)
class _DashboardCounts:
    active_employee_count: int
    employee_count: int
    pending_leave_count: int
    new_starters_this_month: int


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
        counts = await _query_dashboard_counts(
            session=self.session,
            tenant_id=tenant_id,
            today=self.today,
        )
        department_distribution = await _query_department_distribution(
            session=self.session,
            tenant_id=tenant_id,
        )
        recent_activity = await _query_recent_activity(
            session=self.session,
            tenant_id=tenant_id,
            limit=self.recent_activity_limit,
        )

        return _dashboard_summary(
            counts=counts,
            department_distribution=department_distribution,
            recent_activity=recent_activity,
        )


def _month_window(today: date) -> tuple[date, date]:
    start_date = date(today.year, today.month, 1)
    if today.month == 12:
        return start_date, date(today.year + 1, 1, 1)
    return start_date, date(today.year, today.month + 1, 1)


async def _query_dashboard_counts(
    session: AsyncSession,
    tenant_id: UUID,
    today: date,
) -> _DashboardCounts:
    start_date, end_date = _month_window(today)
    result = await session.execute(
        _dashboard_counts_statement(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
        )
    )
    row = result.mappings().one()
    return _DashboardCounts(
        active_employee_count=int(row["active_employee_count"] or 0),
        employee_count=int(row["employee_count"] or 0),
        pending_leave_count=int(row["pending_leave_count"] or 0),
        new_starters_this_month=int(row["new_starters_this_month"] or 0),
    )


async def _query_department_distribution(
    session: AsyncSession,
    tenant_id: UUID,
) -> list[DepartmentDistributionItem]:
    rows = await _mapped_rows(session, _department_distribution_statement(tenant_id))
    return [_department_distribution_item(row) for row in rows]


async def _query_recent_activity(
    session: AsyncSession,
    tenant_id: UUID,
    limit: int,
) -> list[DashboardActivityItem]:
    if limit == 0:
        return []

    activity = [
        *await _query_recent_employee_activity(
            session=session,
            tenant_id=tenant_id,
            limit=limit,
        ),
        *await _query_recent_leave_activity(
            session=session,
            tenant_id=tenant_id,
            limit=limit,
        ),
    ]
    return _latest_activity(activity, limit)


async def _query_recent_employee_activity(
    session: AsyncSession,
    tenant_id: UUID,
    limit: int,
) -> list[DashboardActivityItem]:
    rows = await _query_recent_employee_activity_rows(
        session=session,
        tenant_id=tenant_id,
        limit=limit,
    )
    return _activity_items(rows, _employee_activity_item)


async def _query_recent_leave_activity(
    session: AsyncSession,
    tenant_id: UUID,
    limit: int,
) -> list[DashboardActivityItem]:
    rows = await _query_recent_leave_activity_rows(
        session=session,
        tenant_id=tenant_id,
        limit=limit,
    )
    return _activity_items(rows, _leave_activity_item)


async def _query_recent_employee_activity_rows(
    session: AsyncSession,
    tenant_id: UUID,
    limit: int,
):
    return await _mapped_rows(
        session,
        _recent_employee_activity_statement(
            tenant_id=tenant_id,
            limit=limit,
        ),
    )


async def _query_recent_leave_activity_rows(
    session: AsyncSession,
    tenant_id: UUID,
    limit: int,
):
    return await _mapped_rows(
        session,
        _recent_leave_activity_statement(
            tenant_id=tenant_id,
            limit=limit,
        ),
    )


async def _mapped_rows(session: AsyncSession, statement):
    return (await session.execute(statement)).mappings().all()


def _dashboard_summary(
    counts: _DashboardCounts,
    department_distribution: list[DepartmentDistributionItem],
    recent_activity: list[DashboardActivityItem],
) -> DashboardSummary:
    return DashboardSummary(
        active_employee_count=counts.active_employee_count,
        pending_leave_count=counts.pending_leave_count,
        employee_count=counts.employee_count,
        pending_leave_requests=counts.pending_leave_count,
        new_starters_this_month=counts.new_starters_this_month,
        open_tasks=0,
        department_distribution=department_distribution,
        recent_activity=recent_activity,
    )


def _activity_items(rows, mapper) -> list[DashboardActivityItem]:
    activity_items = []
    for row in rows:
        activity_item = mapper(row)
        if activity_item is not None:
            activity_items.append(activity_item)
    return activity_items


def _latest_activity(
    activity: list[DashboardActivityItem],
    limit: int,
) -> list[DashboardActivityItem]:
    return sorted(activity, key=_activity_timestamp, reverse=True)[:limit]


def _dashboard_counts_statement(tenant_id: UUID, start_date: date, end_date: date):
    current_employee = Employee.status.in_(CURRENT_EMPLOYEE_STATUSES)
    pending_leave_count = (
        select(func.count())
        .select_from(LeaveRequest)
        .where(LeaveRequest.tenant_id == tenant_id)
        .where(LeaveRequest.status == LeaveRequestStatus.PENDING.value)
        .scalar_subquery()
    )
    return (
        select(
            func.count()
            .filter(Employee.status == EmployeeStatus.ACTIVE.value)
            .label("active_employee_count"),
            func.count().filter(current_employee).label("employee_count"),
            pending_leave_count.label("pending_leave_count"),
            func.count()
            .filter(
                and_(
                    current_employee,
                    Employee.employment_start_date >= start_date,
                    Employee.employment_start_date < end_date,
                )
            )
            .label("new_starters_this_month"),
        )
        .select_from(Employee)
        .where(Employee.tenant_id == tenant_id)
        .where(Employee.archived_at.is_(None))
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
        .where(Employee.archived_at.is_(None))
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
        .where(Employee.archived_at.is_(None))
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
