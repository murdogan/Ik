from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.user import User
from app.schemas.leave_request import (
    LeaveRequestCreate,
    LeaveRequestDecision,
    LeaveRequestListFilters,
    LeaveRequestListPagination,
)


class LeaveRequestNotFoundError(Exception):
    pass


class LeaveRequestEmployeeNotFoundError(Exception):
    pass


class LeaveRequestUserNotFoundError(Exception):
    pass


class LeaveRequestDateRangeError(ValueError):
    pass


class LeaveRequestTransitionError(ValueError):
    pass


class LeaveRequestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_leave_requests(
        self,
        tenant_id: UUID,
        filters: LeaveRequestListFilters | None = None,
        pagination: LeaveRequestListPagination | None = None,
    ) -> list[LeaveRequest]:
        filters = filters or LeaveRequestListFilters()
        pagination = pagination or LeaveRequestListPagination()
        statement = select(LeaveRequest).where(LeaveRequest.tenant_id == tenant_id)

        if filters.status is not None:
            statement = statement.where(LeaveRequest.status == _status_value(filters.status))
        if filters.employee_id is not None:
            statement = statement.where(LeaveRequest.employee_id == filters.employee_id)
        if filters.start_date is not None:
            statement = statement.where(LeaveRequest.end_date >= filters.start_date)
        if filters.end_date is not None:
            statement = statement.where(LeaveRequest.start_date <= filters.end_date)

        statement = (
            statement.order_by(
                LeaveRequest.created_at.desc(),
                LeaveRequest.start_date.asc(),
            )
            .offset(pagination.offset)
            .limit(pagination.limit)
        )
        return list(await self.session.scalars(statement))

    async def create_leave_request(
        self,
        tenant_id: UUID,
        payload: LeaveRequestCreate,
    ) -> LeaveRequest:
        _validate_date_order(payload.start_date, payload.end_date)
        await self._ensure_employee_in_tenant(tenant_id, payload.employee_id)
        await self._ensure_user_in_tenant(tenant_id, payload.requested_by_user_id)

        leave_request = LeaveRequest(
            id=uuid4(),
            tenant_id=tenant_id,
            employee_id=payload.employee_id,
            leave_type=payload.leave_type,
            start_date=payload.start_date,
            end_date=payload.end_date,
            status=LeaveRequestStatus.PENDING.value,
            requested_by_user_id=payload.requested_by_user_id,
        )
        self.session.add(leave_request)
        await self.session.commit()
        await self.session.refresh(leave_request)
        return leave_request

    async def approve_leave_request(
        self,
        tenant_id: UUID,
        leave_request_id: UUID,
        payload: LeaveRequestDecision,
    ) -> LeaveRequest:
        return await self._decide_leave_request(
            tenant_id=tenant_id,
            leave_request_id=leave_request_id,
            target_status=LeaveRequestStatus.APPROVED,
            payload=payload,
        )

    async def reject_leave_request(
        self,
        tenant_id: UUID,
        leave_request_id: UUID,
        payload: LeaveRequestDecision,
    ) -> LeaveRequest:
        return await self._decide_leave_request(
            tenant_id=tenant_id,
            leave_request_id=leave_request_id,
            target_status=LeaveRequestStatus.REJECTED,
            payload=payload,
        )

    async def cancel_leave_request(
        self,
        tenant_id: UUID,
        leave_request_id: UUID,
        payload: LeaveRequestDecision,
    ) -> LeaveRequest:
        return await self._decide_leave_request(
            tenant_id=tenant_id,
            leave_request_id=leave_request_id,
            target_status=LeaveRequestStatus.CANCELLED,
            payload=payload,
        )

    async def _decide_leave_request(
        self,
        tenant_id: UUID,
        leave_request_id: UUID,
        target_status: LeaveRequestStatus,
        payload: LeaveRequestDecision,
    ) -> LeaveRequest:
        leave_request = await self._get_leave_request(tenant_id, leave_request_id)
        if leave_request.status != LeaveRequestStatus.PENDING.value:
            raise LeaveRequestTransitionError("Only pending leave requests can be decided")

        await self._ensure_user_in_tenant(tenant_id, payload.decided_by_user_id)
        leave_request.status = target_status.value
        leave_request.decided_by_user_id = payload.decided_by_user_id
        leave_request.decision_note = payload.decision_note

        await self.session.commit()
        await self.session.refresh(leave_request)
        return leave_request

    async def _get_leave_request(self, tenant_id: UUID, leave_request_id: UUID) -> LeaveRequest:
        statement = (
            select(LeaveRequest)
            .where(LeaveRequest.tenant_id == tenant_id)
            .where(LeaveRequest.id == leave_request_id)
        )
        leave_request = await self.session.scalar(statement)
        if leave_request is None:
            raise LeaveRequestNotFoundError
        return leave_request

    async def _ensure_employee_in_tenant(self, tenant_id: UUID, employee_id: UUID) -> None:
        statement = (
            select(Employee.id)
            .where(Employee.tenant_id == tenant_id)
            .where(Employee.id == employee_id)
        )
        if await self.session.scalar(statement) is None:
            raise LeaveRequestEmployeeNotFoundError

    async def _ensure_user_in_tenant(self, tenant_id: UUID, user_id: UUID) -> None:
        statement = select(User.id).where(User.tenant_id == tenant_id).where(User.id == user_id)
        if await self.session.scalar(statement) is None:
            raise LeaveRequestUserNotFoundError


def _validate_date_order(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise LeaveRequestDateRangeError("Leave end date must be on or after start date")


def _status_value(status: LeaveRequestStatus | str | None) -> str | None:
    if isinstance(status, LeaveRequestStatus):
        return status.value
    return status
