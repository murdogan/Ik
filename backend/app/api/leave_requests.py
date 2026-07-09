from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_context
from app.api.errors import ApiError
from app.core.tenancy import TenantContext
from app.db.session import get_session
from app.models.leave_request import LeaveRequestStatus
from app.schemas.leave_request import (
    LEAVE_REQUEST_LIST_DEFAULT_LIMIT,
    LEAVE_REQUEST_LIST_MAX_LIMIT,
    LeaveRequestCreate,
    LeaveRequestDecision,
    LeaveRequestListFilters,
    LeaveRequestListPagination,
    LeaveRequestRead,
)
from app.services.leave_request_service import (
    LeaveRequestDateRangeError,
    LeaveRequestEmployeeNotFoundError,
    LeaveRequestNotFoundError,
    LeaveRequestService,
    LeaveRequestTransitionError,
    LeaveRequestUserNotFoundError,
)

router = APIRouter(prefix="/api/v1/leave-requests", tags=["leave-requests"])


def get_leave_request_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LeaveRequestService:
    return LeaveRequestService(session=session)


def get_leave_request_list_filters(
    status_filter: Annotated[
        LeaveRequestStatus | None,
        Query(alias="status", description="Leave request workflow status filter."),
    ] = None,
    employee_id: Annotated[
        UUID | None,
        Query(description="Employee id filter. Always applied within the current tenant."),
    ] = None,
    start_date: Annotated[
        date | None,
        Query(description="Inclusive date-window start for overlapping leave requests."),
    ] = None,
    end_date: Annotated[
        date | None,
        Query(description="Inclusive date-window end for overlapping leave requests."),
    ] = None,
) -> LeaveRequestListFilters:
    if start_date is not None and end_date is not None and end_date < start_date:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="leave_request_invalid_date_range",
            message="Leave request end_date filter must be on or after start_date",
        )
    return LeaveRequestListFilters(
        status=status_filter,
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
    )


def get_leave_request_list_pagination(
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=LEAVE_REQUEST_LIST_MAX_LIMIT,
            description=(
                "Maximum leave requests to return. Bounded to protect large tenant lists."
            ),
        ),
    ] = LEAVE_REQUEST_LIST_DEFAULT_LIMIT,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of matching leave requests to skip before returning results.",
        ),
    ] = 0,
) -> LeaveRequestListPagination:
    return LeaveRequestListPagination(limit=limit, offset=offset)


@router.get("", response_model=list[LeaveRequestRead])
async def list_leave_requests(
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[LeaveRequestService, Depends(get_leave_request_service)],
    filters: Annotated[LeaveRequestListFilters, Depends(get_leave_request_list_filters)],
    pagination: Annotated[LeaveRequestListPagination, Depends(get_leave_request_list_pagination)],
) -> list[LeaveRequestRead]:
    return await service.list_leave_requests(tenant_context.tenant_id, filters, pagination)


@router.post("", response_model=LeaveRequestRead, status_code=status.HTTP_201_CREATED)
async def create_leave_request(
    payload: LeaveRequestCreate,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[LeaveRequestService, Depends(get_leave_request_service)],
) -> LeaveRequestRead:
    try:
        return await service.create_leave_request(tenant_context.tenant_id, payload)
    except LeaveRequestEmployeeNotFoundError as exc:
        raise _employee_not_found_error() from exc
    except LeaveRequestUserNotFoundError as exc:
        raise _user_not_found_error() from exc
    except LeaveRequestDateRangeError as exc:
        raise _leave_request_date_range_error(exc) from exc


@router.post("/{leave_request_id}/approve", response_model=LeaveRequestRead)
async def approve_leave_request(
    leave_request_id: UUID,
    payload: LeaveRequestDecision,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[LeaveRequestService, Depends(get_leave_request_service)],
) -> LeaveRequestRead:
    try:
        return await service.approve_leave_request(
            tenant_context.tenant_id,
            leave_request_id,
            payload,
        )
    except LeaveRequestNotFoundError as exc:
        raise _leave_request_not_found_error() from exc
    except LeaveRequestUserNotFoundError as exc:
        raise _user_not_found_error() from exc
    except LeaveRequestTransitionError as exc:
        raise _leave_request_transition_error(exc) from exc


@router.post("/{leave_request_id}/reject", response_model=LeaveRequestRead)
async def reject_leave_request(
    leave_request_id: UUID,
    payload: LeaveRequestDecision,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[LeaveRequestService, Depends(get_leave_request_service)],
) -> LeaveRequestRead:
    try:
        return await service.reject_leave_request(
            tenant_context.tenant_id,
            leave_request_id,
            payload,
        )
    except LeaveRequestNotFoundError as exc:
        raise _leave_request_not_found_error() from exc
    except LeaveRequestUserNotFoundError as exc:
        raise _user_not_found_error() from exc
    except LeaveRequestTransitionError as exc:
        raise _leave_request_transition_error(exc) from exc


@router.post("/{leave_request_id}/cancel", response_model=LeaveRequestRead)
async def cancel_leave_request(
    leave_request_id: UUID,
    payload: LeaveRequestDecision,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[LeaveRequestService, Depends(get_leave_request_service)],
) -> LeaveRequestRead:
    try:
        return await service.cancel_leave_request(
            tenant_context.tenant_id,
            leave_request_id,
            payload,
        )
    except LeaveRequestNotFoundError as exc:
        raise _leave_request_not_found_error() from exc
    except LeaveRequestUserNotFoundError as exc:
        raise _user_not_found_error() from exc
    except LeaveRequestTransitionError as exc:
        raise _leave_request_transition_error(exc) from exc


def _leave_request_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="leave_request_not_found",
        message="Leave request not found",
    )


def _employee_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="employee_not_found",
        message="Employee not found",
    )


def _user_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="user_not_found",
        message="User not found",
    )


def _leave_request_date_range_error(exc: LeaveRequestDateRangeError) -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="leave_request_invalid_date_range",
        message=str(exc),
    )


def _leave_request_transition_error(exc: LeaveRequestTransitionError) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="leave_request_transition_conflict",
        message=str(exc),
    )
