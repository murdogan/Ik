"""Fixed-query Employee 360 summaries and redacted product activity."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.employee import Employee
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_profile_change_request import (
    EmployeeProfileChangeRequest,
    EmployeeProfileChangeRequestStatus,
)
from app.models.leave_balance_summary import LeaveBalanceSummary
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.platform.audit import AuditResult, AuditScopeType
from app.schemas.employee_profile_insights import (
    EmployeeDocumentsSummaryRead,
    EmployeeLeaveSummaryRead,
    EmployeeProfileActivityCursor,
    EmployeeProfileActivityKind,
    EmployeeProfileActivityPageRead,
    EmployeeProfileActivityRead,
    EmployeeProfileChangesSummaryRead,
    EmployeeProfileInsightsRead,
)
from app.services.employee_profile_service import EmployeeProfileNotFoundError

_DIRECT_EMPLOYEE_ACTIVITY_KINDS = (
    EmployeeProfileActivityKind.EMPLOYEE_CREATED.value,
    EmployeeProfileActivityKind.EMPLOYEE_UPDATED.value,
    EmployeeProfileActivityKind.EMPLOYEE_LIFECYCLE_CHANGED.value,
    EmployeeProfileActivityKind.EMPLOYEE_ARCHIVED.value,
    EmployeeProfileActivityKind.EMPLOYEE_PERSONAL_PROFILE_UPDATED.value,
    EmployeeProfileActivityKind.EMPLOYEE_EMPLOYMENT_PROFILE_UPDATED.value,
    EmployeeProfileActivityKind.EMPLOYEE_ACCOUNT_LINK_CHANGED.value,
)
_PROFILE_CHANGE_ACTIVITY_KINDS = (
    EmployeeProfileActivityKind.EMPLOYEE_PROFILE_CHANGE_REQUEST_SUBMITTED.value,
    EmployeeProfileActivityKind.EMPLOYEE_PROFILE_CHANGE_REQUEST_APPROVED.value,
    EmployeeProfileActivityKind.EMPLOYEE_PROFILE_CHANGE_REQUEST_REJECTED.value,
    EmployeeProfileActivityKind.EMPLOYEE_PROFILE_CHANGE_REQUEST_CANCELLED.value,
)
_ASSIGNMENT_ACTIVITY_KINDS = (
    EmployeeProfileActivityKind.EMPLOYEE_ASSIGNMENT_CHANGED.value,
    EmployeeProfileActivityKind.REPORTING_LINE_CHANGED.value,
)


class EmployeeProfileInsightsService:
    def __init__(self, session: AsyncSession, *, today: date | None = None) -> None:
        self.session = session
        self.today = today or date.today()

    async def get_employee_profile_insights(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> EmployeeProfileInsightsRead:
        await self._require_employee(tenant_id=tenant_id, employee_id=employee_id)
        activity_cursor = (
            EmployeeProfileActivityCursor.from_token(cursor, employee_id=employee_id)
            if cursor is not None
            else None
        )
        leave, profile_changes = await self._summaries(
            tenant_id=tenant_id,
            employee_id=employee_id,
        )
        activity = await self._activity_page(
            tenant_id=tenant_id,
            employee_id=employee_id,
            limit=limit,
            cursor=activity_cursor,
        )
        return EmployeeProfileInsightsRead(
            documents=EmployeeDocumentsSummaryRead(),
            leave=leave,
            profile_changes=profile_changes,
            activity=activity,
        )

    async def _require_employee(self, *, tenant_id: UUID, employee_id: UUID) -> None:
        employee_exists = await self.session.scalar(
            select(Employee.id).where(
                Employee.tenant_id == tenant_id,
                Employee.id == employee_id,
            )
        )
        if employee_exists is None:
            raise EmployeeProfileNotFoundError

    async def _summaries(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> tuple[EmployeeLeaveSummaryRead, EmployeeProfileChangesSummaryRead]:
        period_year = self.today.year
        remaining_balance = (
            select(
                func.coalesce(
                    func.sum(
                        LeaveBalanceSummary.opening_balance_days
                        - LeaveBalanceSummary.used_days
                        - LeaveBalanceSummary.planned_days
                    ),
                    0.0,
                )
            )
            .where(
                LeaveBalanceSummary.tenant_id == tenant_id,
                LeaveBalanceSummary.employee_id == employee_id,
                LeaveBalanceSummary.period_year == period_year,
            )
            .scalar_subquery()
        )
        pending_leave_requests = (
            select(func.count(LeaveRequest.id))
            .where(
                LeaveRequest.tenant_id == tenant_id,
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == LeaveRequestStatus.PENDING.value,
            )
            .scalar_subquery()
        )
        submitted_profile_change_requests = (
            select(func.count(EmployeeProfileChangeRequest.id))
            .where(
                EmployeeProfileChangeRequest.tenant_id == tenant_id,
                EmployeeProfileChangeRequest.employee_id == employee_id,
                EmployeeProfileChangeRequest.status
                == EmployeeProfileChangeRequestStatus.SUBMITTED.value,
            )
            .scalar_subquery()
        )
        latest_profile_change_status = (
            select(EmployeeProfileChangeRequest.status)
            .where(
                EmployeeProfileChangeRequest.tenant_id == tenant_id,
                EmployeeProfileChangeRequest.employee_id == employee_id,
            )
            .order_by(
                EmployeeProfileChangeRequest.submitted_at.desc(),
                EmployeeProfileChangeRequest.id.desc(),
            )
            .limit(1)
            .scalar_subquery()
        )
        latest_profile_change_submitted_at = (
            select(EmployeeProfileChangeRequest.submitted_at)
            .where(
                EmployeeProfileChangeRequest.tenant_id == tenant_id,
                EmployeeProfileChangeRequest.employee_id == employee_id,
            )
            .order_by(
                EmployeeProfileChangeRequest.submitted_at.desc(),
                EmployeeProfileChangeRequest.id.desc(),
            )
            .limit(1)
            .scalar_subquery()
        )
        row = (
            await self.session.execute(
                select(
                    remaining_balance.label("remaining_balance_days"),
                    pending_leave_requests.label("pending_request_count"),
                    submitted_profile_change_requests.label("submitted_request_count"),
                    latest_profile_change_status.label("latest_status"),
                    latest_profile_change_submitted_at.label("latest_submitted_at"),
                )
            )
        ).one()
        latest_submitted_at = (
            _as_utc(row.latest_submitted_at)
            if row.latest_submitted_at is not None
            else None
        )
        return (
            EmployeeLeaveSummaryRead(
                period_year=period_year,
                remaining_balance_days=float(row.remaining_balance_days),
                pending_request_count=int(row.pending_request_count),
            ),
            EmployeeProfileChangesSummaryRead(
                submitted_request_count=int(row.submitted_request_count),
                latest_status=(
                    EmployeeProfileChangeRequestStatus(row.latest_status)
                    if row.latest_status is not None
                    else None
                ),
                latest_submitted_at=latest_submitted_at,
            ),
        )

    async def _activity_page(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        limit: int,
        cursor: EmployeeProfileActivityCursor | None,
    ) -> EmployeeProfileActivityPageRead:
        profile_change_request_ids = select(EmployeeProfileChangeRequest.id).where(
            EmployeeProfileChangeRequest.tenant_id == tenant_id,
            EmployeeProfileChangeRequest.employee_id == employee_id,
        )
        assignment_ids = select(EmployeeAssignment.id).where(
            EmployeeAssignment.tenant_id == tenant_id,
            EmployeeAssignment.employee_id == employee_id,
        )
        statement = select(
            AuditEvent.id,
            AuditEvent.occurred_at,
            AuditEvent.event_type,
        ).where(
            AuditEvent.scope_type == AuditScopeType.TENANT.value,
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.result == AuditResult.SUCCESS.value,
            or_(
                and_(
                    AuditEvent.resource_type == "employee",
                    AuditEvent.resource_id == employee_id,
                    AuditEvent.event_type.in_(_DIRECT_EMPLOYEE_ACTIVITY_KINDS),
                ),
                and_(
                    AuditEvent.resource_type == "employee_profile_change_request",
                    AuditEvent.resource_id.in_(profile_change_request_ids),
                    AuditEvent.event_type.in_(_PROFILE_CHANGE_ACTIVITY_KINDS),
                ),
                and_(
                    AuditEvent.resource_type == "employee_assignment",
                    AuditEvent.resource_id.in_(assignment_ids),
                    AuditEvent.event_type.in_(_ASSIGNMENT_ACTIVITY_KINDS),
                ),
            ),
        )
        occurred_at_key = self._occurred_at_key()
        if cursor is not None:
            cursor_key = (
                func.julianday(cursor.occurred_at)
                if self._is_sqlite
                else cursor.occurred_at
            )
            statement = statement.where(
                or_(
                    occurred_at_key < cursor_key,
                    and_(
                        occurred_at_key == cursor_key,
                        AuditEvent.id < cursor.id,
                    ),
                )
            )
        rows = list(
            (
                await self.session.execute(
                    statement.order_by(
                        occurred_at_key.desc(),
                        AuditEvent.id.desc(),
                    ).limit(limit + 1)
                )
            ).all()
        )
        items = [
            EmployeeProfileActivityRead(
                id=row.id,
                occurred_at=_as_utc(row.occurred_at),
                kind=EmployeeProfileActivityKind(row.event_type),
            )
            for row in rows[:limit]
        ]
        next_cursor = None
        if len(rows) > limit:
            last_row = rows[limit - 1]
            next_cursor = EmployeeProfileActivityCursor(
                occurred_at=_as_utc(last_row.occurred_at),
                id=last_row.id,
            ).to_token(employee_id=employee_id)
        return EmployeeProfileActivityPageRead(
            items=items,
            limit=limit,
            next_cursor=next_cursor,
        )

    def _occurred_at_key(self):
        if self._is_sqlite:
            return func.julianday(AuditEvent.occurred_at)
        return AuditEvent.occurred_at

    @property
    def _is_sqlite(self) -> bool:
        return self.session.get_bind().dialect.name == "sqlite"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = ["EmployeeProfileInsightsService"]
