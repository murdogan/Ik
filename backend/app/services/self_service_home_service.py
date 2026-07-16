"""Task-focused bounded composition for the employee self-service landing page."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.employee import Employee
from app.models.employee_account_link import EmployeeAccountLink
from app.models.employee_assignment import EmployeeAssignment
from app.models.organization import Branch
from app.models.position import Position
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.platform.request_context import RequestContext
from app.schemas.self_service import (
    SelfServiceHomeRead,
    SelfServiceLeaveBalance,
    SelfServiceWorkSummary,
)
from app.services.announcement_service import AnnouncementService
from app.services.employee_document_service import EmployeeDocumentQueryService
from app.services.leave_service import LeaveService
from app.services.notification_service import NotificationService
from app.services.phase7_access import (
    Phase7ConflictError,
    Phase7FeatureUnavailableError,
    require_phase7_feature,
)
from app.services.request_projection_service import RequestProjectionService

_RECENT_REQUEST_LIMIT = 6
_RECENT_ANNOUNCEMENT_LIMIT = 4
_RECENT_NOTIFICATION_LIMIT = 5


class SelfServiceHomeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self,
        *,
        request_context: RequestContext,
    ) -> SelfServiceHomeRead:
        tenant_id = request_context.require_tenant().tenant_id
        actor_id = request_context.actor_id
        if actor_id is None:
            raise RuntimeError("Self-service home requires an actor")
        await require_phase7_feature(
            self.session,
            tenant_id=tenant_id,
            feature=FeatureFlagKey.SELF_SERVICE,
        )
        employee, _assignment, department, branch, position = await self._work_row(
            tenant_id=tenant_id,
            membership_id=request_context.require_membership(),
        )
        balances = await LeaveService(self.session).list_balances(
            tenant_id=tenant_id,
            employee_id=employee.id,
            period_year=date.today().year,
        )
        request_page = await RequestProjectionService(self.session).list_page(
            tenant_id=tenant_id,
            actor_id=actor_id,
            membership_id=request_context.require_membership(),
            permissions=("request:read:own", "leave:read:own"),
            limit=_RECENT_REQUEST_LIMIT,
            cursor=None,
            kind=None,
            status=None,
        )
        document_summary = await EmployeeDocumentQueryService(self.session).summary(
            tenant_id=tenant_id,
            employee_id=employee.id,
            own_only=True,
        )
        announcements = await AnnouncementService(self.session).list_page(
            tenant_id=tenant_id,
            actor_id=actor_id,
            manage=False,
            status=None,
            limit=_RECENT_ANNOUNCEMENT_LIMIT,
            cursor=None,
        )
        notification_items = []
        unread_count = 0
        try:
            notifications = await NotificationService(self.session).list_page(
                tenant_id=tenant_id,
                actor_id=actor_id,
                limit=_RECENT_NOTIFICATION_LIMIT,
                cursor=None,
                unread_only=False,
            )
            notification_items = notifications.items
            unread_count = notifications.unread_count
        except Phase7FeatureUnavailableError:
            pass
        return SelfServiceHomeRead(
            work=SelfServiceWorkSummary(
                employee_id=employee.id,
                display_name=f"{employee.first_name} {employee.last_name}".strip(),
                employee_number=employee.employee_number,
                status=employee.status,
                department_name=department.name if department is not None else None,
                branch_name=branch.name if branch is not None else None,
                position_title=position.title if position is not None else None,
                employment_start_date=employee.employment_start_date,
            ),
            leave_balances=[
                SelfServiceLeaveBalance(
                    leave_type_id=balance.leave_type_id,
                    leave_type_name=balance.leave_type_name,
                    period_year=balance.period_year,
                    available_days=balance.available_days,
                )
                for balance in balances
            ],
            leave_request_path="/leave",
            requests_path="/requests",
            recent_requests=request_page.items,
            document_summary=document_summary,
            announcements=announcements.items,
            unread_notification_count=unread_count,
            notifications=notification_items,
        )

    async def _work_row(self, *, tenant_id: UUID, membership_id: UUID):
        current = date.today()
        row = (
            await self.session.execute(
                select(Employee, EmployeeAssignment, Department, Branch, Position)
                .join(
                    EmployeeAccountLink,
                    and_(
                        EmployeeAccountLink.tenant_id == Employee.tenant_id,
                        EmployeeAccountLink.employee_id == Employee.id,
                    ),
                )
                .outerjoin(
                    EmployeeAssignment,
                    and_(
                        EmployeeAssignment.tenant_id == Employee.tenant_id,
                        EmployeeAssignment.employee_id == Employee.id,
                        EmployeeAssignment.effective_from <= current,
                        or_(
                            EmployeeAssignment.effective_to.is_(None),
                            EmployeeAssignment.effective_to > current,
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
                .outerjoin(
                    Branch,
                    and_(
                        Branch.tenant_id == EmployeeAssignment.tenant_id,
                        Branch.id == EmployeeAssignment.branch_id,
                    ),
                )
                .outerjoin(
                    Position,
                    and_(
                        Position.tenant_id == EmployeeAssignment.tenant_id,
                        Position.id == EmployeeAssignment.position_id,
                    ),
                )
                .where(
                    Employee.tenant_id == tenant_id,
                    EmployeeAccountLink.membership_id == membership_id,
                    Employee.archived_at.is_(None),
                )
                .order_by(
                    EmployeeAssignment.effective_from.desc(),
                    EmployeeAssignment.id.desc(),
                )
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            raise Phase7ConflictError
        return row


__all__ = ["SelfServiceHomeService"]
