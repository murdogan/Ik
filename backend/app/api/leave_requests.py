from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_context
from app.core.tenancy import TenantContext
from app.db.session import get_session
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestDecision, LeaveRequestRead
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


@router.get("", response_model=list[LeaveRequestRead])
async def list_leave_requests(
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[LeaveRequestService, Depends(get_leave_request_service)],
) -> list[LeaveRequestRead]:
    return await service.list_leave_requests(tenant_context.tenant_id)


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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


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


def _leave_request_not_found_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Leave request not found",
    )


def _employee_not_found_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Employee not found",
    )


def _user_not_found_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User not found",
    )


def _leave_request_transition_error(exc: LeaveRequestTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(exc),
    )
