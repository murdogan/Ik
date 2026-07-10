from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_messages import (
    LEAVE_END_DATE_MUST_BE_DATE_MESSAGE,
    LEAVE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE,
    LEAVE_END_DATE_REQUIRED_MESSAGE,
    LEAVE_REQUEST_FILTER_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE,
    LEAVE_REQUEST_ONLY_PENDING_CAN_BE_DECIDED_MESSAGE,
    LEAVE_START_DATE_MUST_BE_DATE_MESSAGE,
    LEAVE_START_DATE_REQUIRED_MESSAGE,
)
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
        _validate_filter_date_range(filters)
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
                LeaveRequest.id.asc(),
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
            raise LeaveRequestTransitionError(LEAVE_REQUEST_ONLY_PENDING_CAN_BE_DECIDED_MESSAGE)

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


def _validate_date_order(start_date: object, end_date: object) -> None:
    start_date = _required_leave_date(
        start_date,
        missing_message=LEAVE_START_DATE_REQUIRED_MESSAGE,
        invalid_message=LEAVE_START_DATE_MUST_BE_DATE_MESSAGE,
    )
    end_date = _required_leave_date(
        end_date,
        missing_message=LEAVE_END_DATE_REQUIRED_MESSAGE,
        invalid_message=LEAVE_END_DATE_MUST_BE_DATE_MESSAGE,
    )
    if end_date < start_date:
        raise LeaveRequestDateRangeError(LEAVE_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE)


def _validate_filter_date_range(filters: LeaveRequestListFilters) -> None:
    start_date = _optional_leave_date(
        filters.start_date,
        invalid_message=LEAVE_START_DATE_MUST_BE_DATE_MESSAGE,
    )
    end_date = _optional_leave_date(
        filters.end_date,
        invalid_message=LEAVE_END_DATE_MUST_BE_DATE_MESSAGE,
    )
    if start_date is not None and end_date is not None and end_date < start_date:
        raise LeaveRequestDateRangeError(
            LEAVE_REQUEST_FILTER_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE
        )


def _required_leave_date(
    value: object,
    *,
    missing_message: str,
    invalid_message: str,
) -> date:
    if value is None:
        raise LeaveRequestDateRangeError(missing_message)
    if isinstance(value, datetime) or not isinstance(value, date):
        raise LeaveRequestDateRangeError(invalid_message)
    return value


def _optional_leave_date(
    value: object,
    *,
    invalid_message: str,
) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise LeaveRequestDateRangeError(invalid_message)
    return value


def _status_value(status: LeaveRequestStatus | str | None) -> str | None:
    if isinstance(status, LeaveRequestStatus):
        return status.value
    return status
