"""Bounded role-aware dashboard metrics and allowlisted audit-derived activity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import and_, exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_document import DocumentProcessingState, DocumentType, EmployeeDocument
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.schemas.dashboard import (
    DashboardActivityItem,
    DashboardSummary,
    DepartmentDistributionItem,
)

_CURRENT_STATUSES = (EmployeeStatus.ACTIVE.value, EmployeeStatus.ON_LEAVE.value)
_AUDIT_ACTIVITY = {
    "employee.created": ("employee.created", "Employee record created"),
    "employee.updated": ("employee.updated", "Employee record updated"),
    "employee.lifecycle.changed": (
        "employee.lifecycle.changed",
        "Employee lifecycle updated",
    ),
    # Preserve the established dashboard activity values while sourcing them from audit facts.
    "leave_request.submitted": ("leave.requested", "Leave request submitted"),
    "leave_request.approved": ("leave.approved", "Leave request approved"),
    "leave_request.rejected": ("leave.rejected", "Leave request rejected"),
    "leave_request.cancelled": ("leave.cancelled", "Leave request cancelled"),
}
_EMPLOYEE_ACTIVITY_TYPES = (
    "employee.created",
    "employee.updated",
    "employee.lifecycle.changed",
)
_LEAVE_ACTIVITY_TYPES = (
    "leave_request.submitted",
    "leave_request.approved",
    "leave_request.rejected",
    "leave_request.cancelled",
)


@dataclass(frozen=True, slots=True)
class _DashboardScope:
    value: str
    manager_user_id: UUID | None = None


class DashboardService:
    def __init__(
        self,
        session: AsyncSession,
        today: date | None = None,
        recent_activity_limit: int = 5,
        document_expiring_days: int = 30,
    ) -> None:
        self.session = session
        self.today = today or date.today()
        self.recent_activity_limit = min(max(recent_activity_limit, 0), 20)
        self.document_expiring_days = document_expiring_days

    async def get_summary(
        self,
        tenant_id: UUID,
        *,
        actor_id: UUID,
        permissions: tuple[str, ...],
    ) -> DashboardSummary:
        scope = _dashboard_scope(actor_id=actor_id, permissions=permissions)
        if scope.value == "own":
            return _empty_summary()
        start_date, end_date = _month_window(self.today)
        employee_scope = _employee_scope_predicate(
            tenant_id=tenant_id,
            employee_id=Employee.id,
            scope=scope,
            effective_on=self.today,
        )
        row = (
            await self.session.execute(
                select(
                    func.count()
                    .filter(Employee.status == EmployeeStatus.ACTIVE.value)
                    .label("active_count"),
                    func.count().filter(Employee.status.in_(_CURRENT_STATUSES)).label("headcount"),
                    func.count()
                    .filter(
                        and_(
                            Employee.status.in_(_CURRENT_STATUSES),
                            Employee.employment_start_date >= start_date,
                            Employee.employment_start_date < end_date,
                        )
                    )
                    .label("starters"),
                    func.count()
                    .filter(
                        and_(
                            Employee.status == EmployeeStatus.TERMINATED.value,
                            Employee.employment_end_date >= start_date,
                            Employee.employment_end_date < end_date,
                        )
                    )
                    .label("terminated"),
                )
                .select_from(Employee)
                .where(
                    Employee.tenant_id == tenant_id,
                    Employee.archived_at.is_(None),
                    employee_scope,
                )
            )
        ).mappings().one()
        pending_leave = await self.session.scalar(
            select(func.count())
            .select_from(LeaveRequest)
            .where(
                LeaveRequest.tenant_id == tenant_id,
                LeaveRequest.status == LeaveRequestStatus.PENDING.value,
                _employee_scope_predicate(
                    tenant_id=tenant_id,
                    employee_id=LeaveRequest.employee_id,
                    scope=scope,
                    effective_on=self.today,
                ),
            )
        )
        missing_documents, expiring_documents = await _document_counts(
            self.session,
            tenant_id=tenant_id,
            scope=scope,
            effective_on=self.today,
            expiring_on=self.today + timedelta(days=self.document_expiring_days),
        )
        distribution = await _department_distribution(
            self.session,
            tenant_id=tenant_id,
            scope=scope,
            effective_on=self.today,
        )
        activity = await _recent_activity(
            self.session,
            tenant_id=tenant_id,
            scope=scope,
            effective_on=self.today,
            limit=self.recent_activity_limit,
        )
        return DashboardSummary(
            scope=scope.value,
            active_employee_count=int(row["active_count"] or 0),
            pending_leave_count=int(pending_leave or 0),
            employee_count=int(row["headcount"] or 0),
            pending_leave_requests=int(pending_leave or 0),
            new_starters_this_month=int(row["starters"] or 0),
            terminated_this_month=int(row["terminated"] or 0),
            missing_document_count=missing_documents,
            expiring_document_count=expiring_documents,
            open_tasks=int(pending_leave or 0),
            department_distribution=distribution,
            recent_activity=activity,
        )


async def _document_counts(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    scope: _DashboardScope,
    effective_on: date,
    expiring_on: date,
) -> tuple[int, int]:
    available_document = exists(
        select(EmployeeDocument.id).where(
            EmployeeDocument.tenant_id == tenant_id,
            EmployeeDocument.employee_id == Employee.id,
            EmployeeDocument.document_type_id == DocumentType.id,
            EmployeeDocument.processing_state == DocumentProcessingState.AVAILABLE.value,
            EmployeeDocument.archived_at.is_(None),
        )
    )
    best_expiry = (
        select(EmployeeDocument.expires_on)
        .where(
            EmployeeDocument.tenant_id == tenant_id,
            EmployeeDocument.employee_id == Employee.id,
            EmployeeDocument.document_type_id == DocumentType.id,
            EmployeeDocument.processing_state == DocumentProcessingState.AVAILABLE.value,
            EmployeeDocument.archived_at.is_(None),
        )
        .order_by(
            EmployeeDocument.expires_on.desc().nulls_first(),
            EmployeeDocument.created_at.desc(),
            EmployeeDocument.id.desc(),
        )
        .limit(1)
        .correlate(Employee, DocumentType)
        .scalar_subquery()
    )
    row = (
        await session.execute(
            select(
                func.count().filter(~available_document).label("missing"),
                func.count()
                .filter(
                    best_expiry.is_not(None),
                    best_expiry >= effective_on,
                    best_expiry <= expiring_on,
                )
                .label("expiring"),
            )
            .select_from(Employee)
            .join(DocumentType, DocumentType.tenant_id == Employee.tenant_id)
            .where(
                Employee.tenant_id == tenant_id,
                Employee.archived_at.is_(None),
                Employee.status.in_(_CURRENT_STATUSES),
                DocumentType.required.is_(True),
                DocumentType.archived_at.is_(None),
                _employee_scope_predicate(
                    tenant_id=tenant_id,
                    employee_id=Employee.id,
                    scope=scope,
                    effective_on=effective_on,
                ),
            )
        )
    ).mappings().one()
    return int(row["missing"] or 0), int(row["expiring"] or 0)


async def _department_distribution(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    scope: _DashboardScope,
    effective_on: date,
) -> list[DepartmentDistributionItem]:
    department_label = func.coalesce(
        func.nullif(func.trim(Department.name), ""),
        func.nullif(func.trim(Employee.department), ""),
        "Unassigned",
    )
    statement = (
        select(
            department_label.label("department"),
            func.count(Employee.id).label("employee_count"),
        )
        .select_from(Employee)
        .outerjoin(
            EmployeeAssignment,
            and_(
                Employee.tenant_id == EmployeeAssignment.tenant_id,
                Employee.id == EmployeeAssignment.employee_id,
                EmployeeAssignment.effective_from <= effective_on,
                or_(
                    EmployeeAssignment.effective_to.is_(None),
                    EmployeeAssignment.effective_to > effective_on,
                ),
            ),
        )
        .outerjoin(
            Department,
            and_(
                Department.tenant_id == EmployeeAssignment.tenant_id,
                Department.id == EmployeeAssignment.department_id,
            ),
        )
        .where(
            Employee.tenant_id == tenant_id,
            Employee.archived_at.is_(None),
            Employee.status.in_(_CURRENT_STATUSES),
        )
        .group_by(department_label)
        .order_by(func.count(Employee.id).desc(), department_label.asc())
        .limit(20)
    )
    if scope.value == "team":
        statement = statement.where(EmployeeAssignment.manager_user_id == scope.manager_user_id)
    rows = (await session.execute(statement)).all()
    return [
        DepartmentDistributionItem(department=name, count=int(count))
        for name, count in rows
    ]


async def _recent_activity(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    scope: _DashboardScope,
    effective_on: date,
    limit: int,
) -> list[DashboardActivityItem]:
    if limit == 0:
        return []
    statement = select(
        AuditEvent.event_type,
        AuditEvent.resource_type,
        AuditEvent.resource_id,
        AuditEvent.occurred_at,
    ).where(
        AuditEvent.tenant_id == tenant_id,
        AuditEvent.event_type.in_(tuple(_AUDIT_ACTIVITY)),
        AuditEvent.resource_id.is_not(None),
        AuditEvent.result == "success",
        or_(
            and_(
                AuditEvent.event_type.in_(_EMPLOYEE_ACTIVITY_TYPES),
                AuditEvent.resource_type == "employee",
            ),
            and_(
                AuditEvent.event_type.in_(_LEAVE_ACTIVITY_TYPES),
                AuditEvent.resource_type == "leave_request",
            ),
        ),
    )
    if scope.value == "team":
        statement = statement.where(
            or_(
                and_(
                    AuditEvent.resource_type == "employee",
                    _employee_scope_predicate(
                        tenant_id=tenant_id,
                        employee_id=AuditEvent.resource_id,
                        scope=scope,
                        effective_on=effective_on,
                    ),
                ),
                and_(
                    AuditEvent.resource_type == "leave_request",
                    exists(
                        select(LeaveRequest.id).where(
                            LeaveRequest.tenant_id == tenant_id,
                            LeaveRequest.id == AuditEvent.resource_id,
                            _employee_scope_predicate(
                                tenant_id=tenant_id,
                                employee_id=LeaveRequest.employee_id,
                                scope=scope,
                                effective_on=effective_on,
                            ),
                        )
                    ),
                ),
            )
        )
    events = (
        await session.execute(
            statement.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(limit)
        )
    ).all()
    return [
        DashboardActivityItem(
            activity_type=_AUDIT_ACTIVITY[event_type][0],
            entity_type=resource_type,
            entity_id=resource_id,
            title=_AUDIT_ACTIVITY[event_type][1],
            occurred_at=occurred_at,
        )
        for event_type, resource_type, resource_id, occurred_at in events
        if resource_id is not None
    ]


def _employee_scope_predicate(
    *,
    tenant_id: UUID,
    employee_id,
    scope: _DashboardScope,
    effective_on: date,
):
    if scope.value == "tenant":
        return literal(True)
    if scope.manager_user_id is None:
        return literal(False)
    return exists(
        select(EmployeeAssignment.id).where(
            EmployeeAssignment.tenant_id == tenant_id,
            EmployeeAssignment.employee_id == employee_id,
            EmployeeAssignment.manager_user_id == scope.manager_user_id,
            EmployeeAssignment.effective_from <= effective_on,
            or_(
                EmployeeAssignment.effective_to.is_(None),
                EmployeeAssignment.effective_to > effective_on,
            ),
        )
    )


def _dashboard_scope(*, actor_id: UUID, permissions: tuple[str, ...]) -> _DashboardScope:
    if "dashboard:read:tenant" in permissions:
        return _DashboardScope("tenant")
    if "dashboard:read:team" in permissions:
        return _DashboardScope("team", actor_id)
    return _DashboardScope("own")


def _month_window(today: date) -> tuple[date, date]:
    start = date(today.year, today.month, 1)
    end = (
        date(today.year + 1, 1, 1)
        if today.month == 12
        else date(today.year, today.month + 1, 1)
    )
    return start, end


def _empty_summary() -> DashboardSummary:
    return DashboardSummary(
        scope="own",
        active_employee_count=0,
        pending_leave_count=0,
        employee_count=0,
        pending_leave_requests=0,
        new_starters_this_month=0,
        terminated_this_month=0,
        missing_document_count=0,
        expiring_document_count=0,
        open_tasks=0,
        department_distribution=[],
        recent_activity=[],
    )


__all__ = ["DashboardService"]
