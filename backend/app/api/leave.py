"""Phase 6 leave configuration, balances, requests, and approval APIs."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import (
    AuthenticatedSession,
    require_any_permission,
    require_permission,
)
from app.api.compatibility import phase0_plain_cursor_list
from app.api.dependencies import (
    get_authenticated_tenant_request_context,
    get_command_idempotency_service,
    get_idempotency_key,
    get_unit_of_work,
)
from app.api.openapi import (
    LEAVE_APPROVALS_TAG,
    LEAVE_BALANCES_TAG,
    LEAVE_CONFIGURATION_TAG,
    LEAVE_REQUESTS_TAG,
)
from app.db.session import get_session
from app.models.leave_request import LeaveRequestStatus
from app.platform.db import SqlAlchemyUnitOfWork
from app.platform.pagination import MAX_CURSOR_LENGTH, NEXT_CURSOR_HEADER, InvalidCursorError
from app.platform.request_context import RequestContext
from app.schemas.leave import (
    LEAVE_LIST_DEFAULT_LIMIT,
    LEAVE_LIST_MAX_LIMIT,
    ApprovalTaskListCursor,
    ApprovalTaskRead,
    HolidayCalendarCreate,
    HolidayCalendarRead,
    HolidayCalendarUpdate,
    HolidayEntryCreate,
    HolidayEntryListCursor,
    HolidayEntryRead,
    HolidayEntryUpdate,
    LeaveAccessScope,
    LeaveAdjustmentCreate,
    LeaveBalanceRead,
    LeaveLedgerEntryRead,
    LeaveLedgerListCursor,
    LeavePolicyCreate,
    LeavePolicyRead,
    LeaveRequestCreate,
    LeaveRequestDecision,
    LeaveRequestListCursor,
    LeaveRequestListFilters,
    LeaveRequestRead,
    LeaveTypeCreate,
    LeaveTypeRead,
    LeaveTypeUpdate,
    TeamCalendarEntryRead,
)
from app.services.command_idempotency import CommandIdempotencyService
from app.services.leave_commands import LeaveCommandHandler
from app.services.leave_service import LeaveAccessDeniedError, LeaveService, LeaveValidationError

_READ_PERMISSIONS = ("leave:read:own", "leave:read:team", "leave:read:tenant")
_LEAVE_LIST_MAX_OFFSET = 10_000


def get_leave_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LeaveService:
    return LeaveService(session)


def get_leave_command_handler(
    service: Annotated[LeaveService, Depends(get_leave_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
    idempotency: Annotated[
        CommandIdempotencyService, Depends(get_command_idempotency_service)
    ],
) -> LeaveCommandHandler:
    return LeaveCommandHandler(
        service=service,
        unit_of_work=unit_of_work,
        idempotency=idempotency,
    )


def _prevent_leave_response_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


_NO_STORE_DEPENDENCY = [Depends(_prevent_leave_response_storage)]

configuration_router = APIRouter(
    tags=[LEAVE_CONFIGURATION_TAG], dependencies=_NO_STORE_DEPENDENCY
)
balance_router = APIRouter(tags=[LEAVE_BALANCES_TAG], dependencies=_NO_STORE_DEPENDENCY)
request_router = APIRouter(
    prefix="/api/v1/leave-requests",
    tags=[LEAVE_REQUESTS_TAG],
    dependencies=_NO_STORE_DEPENDENCY,
)
approval_router = APIRouter(tags=[LEAVE_APPROVALS_TAG], dependencies=_NO_STORE_DEPENDENCY)


@configuration_router.get(
    "/api/v1/leave-types",
    response_model=list[LeaveTypeRead],
    summary="List leave types",
)
async def list_leave_types(
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession, Depends(require_any_permission(*_READ_PERMISSIONS))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    include_inactive: Annotated[bool, Query()] = False,
    effective_on: Annotated[date | None, Query()] = None,
) -> list[LeaveTypeRead]:
    if include_inactive and "leave:manage:tenant" not in authorized.user.permissions:
        raise LeaveAccessDeniedError
    return await service.list_leave_types(
        request_context.require_tenant().tenant_id,
        include_inactive=include_inactive,
        effective_on=effective_on,
    )


@configuration_router.post(
    "/api/v1/leave-types",
    response_model=LeaveTypeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a leave type",
)
async def create_leave_type(
    payload: LeaveTypeCreate,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:manage:tenant"))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> LeaveTypeRead:
    return await unit_of_work.execute(
        lambda: service.create_leave_type(request_context=request_context, payload=payload)
    )


@configuration_router.patch(
    "/api/v1/leave-types/{leave_type_id}",
    response_model=LeaveTypeRead,
    summary="Update or deactivate a leave type",
)
async def update_leave_type(
    leave_type_id: UUID,
    payload: LeaveTypeUpdate,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:manage:tenant"))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> LeaveTypeRead:
    return await unit_of_work.execute(
        lambda: service.update_leave_type(
            request_context=request_context,
            leave_type_id=leave_type_id,
            payload=payload,
        )
    )


@configuration_router.get(
    "/api/v1/holiday-calendars",
    response_model=list[HolidayCalendarRead],
    summary="List holiday calendars and entries",
)
async def list_holiday_calendars(
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_any_permission("leave:read:tenant", "leave:manage:tenant")),
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    include_inactive: Annotated[bool, Query()] = False,
) -> list[HolidayCalendarRead]:
    if include_inactive and "leave:manage:tenant" not in authorized.user.permissions:
        raise LeaveAccessDeniedError
    return await service.list_holiday_calendars(
        request_context.require_tenant().tenant_id,
        include_inactive=include_inactive,
    )


@configuration_router.get(
    "/api/v1/holiday-calendars/{calendar_id}/holidays",
    response_model=list[HolidayEntryRead],
    summary="List a holiday calendar's dated entries",
    responses={
        status.HTTP_200_OK: {
            "headers": {NEXT_CURSOR_HEADER: {"schema": {"type": "string"}}}
        }
    },
)
async def list_holiday_entries(
    calendar_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_any_permission("leave:read:tenant", "leave:manage:tenant")),
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    include_inactive: Annotated[bool, Query()] = False,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=LEAVE_LIST_MAX_LIMIT)] = LEAVE_LIST_DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)] = None,
) -> list[HolidayEntryRead]:
    if include_inactive and "leave:manage:tenant" not in authorized.user.permissions:
        raise LeaveAccessDeniedError
    try:
        decoded_cursor = (
            HolidayEntryListCursor.from_token(cursor) if cursor is not None else None
        )
    except (InvalidCursorError, ValidationError) as exc:
        raise LeaveValidationError("The holiday entry cursor is invalid") from exc
    page = await service.list_holiday_entry_page(
        tenant_id=request_context.require_tenant().tenant_id,
        calendar_id=calendar_id,
        include_inactive=include_inactive,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        cursor=decoded_cursor,
    )
    return phase0_plain_cursor_list(response, page)


@configuration_router.post(
    "/api/v1/holiday-calendars",
    response_model=HolidayCalendarRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a holiday calendar",
)
async def create_holiday_calendar(
    payload: HolidayCalendarCreate,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:manage:tenant"))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> HolidayCalendarRead:
    return await unit_of_work.execute(
        lambda: service.create_holiday_calendar(
            request_context=request_context, payload=payload
        )
    )


@configuration_router.patch(
    "/api/v1/holiday-calendars/{calendar_id}",
    response_model=HolidayCalendarRead,
    summary="Update or deactivate a holiday calendar",
)
async def update_holiday_calendar(
    calendar_id: UUID,
    payload: HolidayCalendarUpdate,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:manage:tenant"))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> HolidayCalendarRead:
    return await unit_of_work.execute(
        lambda: service.update_holiday_calendar(
            request_context=request_context,
            calendar_id=calendar_id,
            payload=payload,
        )
    )


@configuration_router.post(
    "/api/v1/holiday-calendars/{calendar_id}/holidays",
    response_model=HolidayEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a dated holiday",
)
async def create_holiday_entry(
    calendar_id: UUID,
    payload: HolidayEntryCreate,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:manage:tenant"))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> HolidayEntryRead:
    return await unit_of_work.execute(
        lambda: service.create_holiday_entry(
            request_context=request_context,
            calendar_id=calendar_id,
            payload=payload,
        )
    )


@configuration_router.patch(
    "/api/v1/holiday-calendars/{calendar_id}/holidays/{entry_id}",
    response_model=HolidayEntryRead,
    summary="Update or deactivate a dated holiday",
)
async def update_holiday_entry(
    calendar_id: UUID,
    entry_id: UUID,
    payload: HolidayEntryUpdate,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:manage:tenant"))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> HolidayEntryRead:
    return await unit_of_work.execute(
        lambda: service.update_holiday_entry(
            request_context=request_context,
            calendar_id=calendar_id,
            entry_id=entry_id,
            payload=payload,
        )
    )


@configuration_router.get(
    "/api/v1/leave-policies",
    response_model=list[LeavePolicyRead],
    summary="List immutable leave policy history",
)
async def list_leave_policies(
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:manage:tenant"))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    leave_type_id: Annotated[UUID | None, Query()] = None,
) -> list[LeavePolicyRead]:
    return await service.list_policies(
        request_context.require_tenant().tenant_id,
        leave_type_id=leave_type_id,
    )


@configuration_router.post(
    "/api/v1/leave-policies",
    response_model=LeavePolicyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an effective-dated policy version",
)
async def create_leave_policy(
    payload: LeavePolicyCreate,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:manage:tenant"))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> LeavePolicyRead:
    return await unit_of_work.execute(
        lambda: service.create_policy(request_context=request_context, payload=payload)
    )


@balance_router.get(
    "/api/v1/me/leave-balances",
    response_model=list[LeaveBalanceRead],
    summary="List my derived leave balances",
)
async def list_own_leave_balances(
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:read:own"))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    period_year: Annotated[int | None, Query(ge=1900, le=2200)] = None,
) -> list[LeaveBalanceRead]:
    return await service.list_own_balances(
        request_context=request_context,
        period_year=period_year or date.today().year,
    )


@balance_router.get(
    "/api/v1/employees/{employee_id}/leave-balances",
    response_model=list[LeaveBalanceRead],
    summary="List an employee's derived leave balances",
)
async def list_employee_leave_balances(
    employee_id: UUID,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:read:tenant"))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    period_year: Annotated[int | None, Query(ge=1900, le=2200)] = None,
) -> list[LeaveBalanceRead]:
    return await service.list_balances(
        tenant_id=request_context.require_tenant().tenant_id,
        employee_id=employee_id,
        period_year=period_year or date.today().year,
    )


def _ledger_cursor(token: str | None) -> LeaveLedgerListCursor | None:
    if token is None:
        return None
    try:
        return LeaveLedgerListCursor.from_token(token)
    except (InvalidCursorError, ValidationError) as exc:
        raise LeaveValidationError("The leave balance history cursor is invalid") from exc


@balance_router.get(
    "/api/v1/me/leave-balances/history",
    response_model=list[LeaveLedgerEntryRead],
    summary="List my append-only leave balance history",
    responses={
        status.HTTP_200_OK: {
            "headers": {NEXT_CURSOR_HEADER: {"schema": {"type": "string"}}}
        }
    },
)
async def list_own_leave_history(
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:read:own"))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    limit: Annotated[int, Query(ge=1, le=LEAVE_LIST_MAX_LIMIT)] = LEAVE_LIST_DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)] = None,
    period_year: Annotated[int | None, Query(ge=1900, le=2200)] = None,
) -> list[LeaveLedgerEntryRead]:
    page = await service.list_own_ledger_page(
        request_context=request_context,
        limit=limit,
        cursor=_ledger_cursor(cursor),
        period_year=period_year,
    )
    return phase0_plain_cursor_list(response, page)


@balance_router.get(
    "/api/v1/employees/{employee_id}/leave-balances/history",
    response_model=list[LeaveLedgerEntryRead],
    summary="List an employee's append-only leave balance history",
)
async def list_employee_leave_history(
    employee_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:read:tenant"))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    limit: Annotated[int, Query(ge=1, le=LEAVE_LIST_MAX_LIMIT)] = LEAVE_LIST_DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)] = None,
    period_year: Annotated[int | None, Query(ge=1900, le=2200)] = None,
) -> list[LeaveLedgerEntryRead]:
    page = await service.list_ledger_page(
        tenant_id=request_context.require_tenant().tenant_id,
        employee_id=employee_id,
        limit=limit,
        cursor=_ledger_cursor(cursor),
        period_year=period_year,
    )
    return phase0_plain_cursor_list(response, page)


@balance_router.post(
    "/api/v1/leave-adjustments",
    response_model=LeaveLedgerEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Post a reason-required manual balance adjustment",
)
async def create_leave_adjustment(
    payload: LeaveAdjustmentCreate,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:adjust:tenant"))
    ],
    command_handler: Annotated[LeaveCommandHandler, Depends(get_leave_command_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> LeaveLedgerEntryRead:
    return await command_handler.create_adjustment(
        request_context=request_context,
        payload=payload,
        idempotency_key=idempotency_key,
    )


def _request_cursor(token: str | None) -> LeaveRequestListCursor | None:
    if token is None:
        return None
    try:
        return LeaveRequestListCursor.from_token(token)
    except (InvalidCursorError, ValidationError) as exc:
        raise LeaveValidationError("The leave request cursor is invalid") from exc


@request_router.get(
    "",
    response_model=list[LeaveRequestRead],
    summary="List authorized leave requests",
    responses={
        status.HTTP_200_OK: {
            "headers": {NEXT_CURSOR_HEADER: {"schema": {"type": "string"}}}
        }
    },
)
async def list_leave_requests(
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession, Depends(require_any_permission(*_READ_PERMISSIONS))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    status_filter: Annotated[LeaveRequestStatus | None, Query(alias="status")] = None,
    scope: Annotated[LeaveAccessScope | None, Query()] = None,
    employee_id: Annotated[UUID | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=LEAVE_LIST_MAX_LIMIT)] = LEAVE_LIST_DEFAULT_LIMIT,
    offset: Annotated[
        int,
        Query(
            ge=0,
            le=_LEAVE_LIST_MAX_OFFSET,
            deprecated=True,
            description="Bounded compatibility offset; prefer X-Next-Cursor.",
        ),
    ] = 0,
    cursor: Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)] = None,
) -> list[LeaveRequestRead]:
    try:
        filters = LeaveRequestListFilters(
            status=status_filter,
            scope=scope,
            employee_id=employee_id,
            start_date=start_date,
            end_date=end_date,
        )
    except ValidationError as exc:
        raise LeaveValidationError("The leave request filters are invalid") from exc
    decoded_cursor = _request_cursor(cursor)
    if decoded_cursor is not None and offset:
        raise LeaveValidationError("Cursor pagination requires offset=0")
    page = await service.list_request_page(
        request_context=request_context,
        permissions=authorized.user.permissions,
        filters=filters,
        limit=limit,
        offset=offset,
        cursor=decoded_cursor,
    )
    return phase0_plain_cursor_list(response, page)


@request_router.post(
    "",
    response_model=LeaveRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Submit my leave request",
)
async def create_leave_request(
    payload: LeaveRequestCreate,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("leave:create:own"))
    ],
    command_handler: Annotated[LeaveCommandHandler, Depends(get_leave_command_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> LeaveRequestRead:
    return await command_handler.create_request(
        request_context=request_context,
        payload=payload,
        permissions=authorized.user.permissions,
        idempotency_key=idempotency_key,
    )


@request_router.get(
    "/{request_id}",
    response_model=LeaveRequestRead,
    summary="Read an authorized leave request and timeline",
)
async def read_leave_request(
    request_id: UUID,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession, Depends(require_any_permission(*_READ_PERMISSIONS))
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    scope: Annotated[LeaveAccessScope | None, Query()] = None,
) -> LeaveRequestRead:
    return await service.get_request(
        request_context=request_context,
        permissions=authorized.user.permissions,
        request_id=request_id,
        scope=scope,
    )


async def _decide(
    *,
    action: str,
    request_id: UUID,
    payload: LeaveRequestDecision,
    request_context: RequestContext,
    authorized: AuthenticatedSession,
    command_handler: LeaveCommandHandler,
    idempotency_key: str | None,
) -> LeaveRequestRead:
    return await command_handler.decide_request(
        request_context=request_context,
        request_id=request_id,
        action=action,
        payload=payload,
        permissions=authorized.user.permissions,
        idempotency_key=idempotency_key,
    )


@request_router.post(
    "/{request_id}/approve",
    response_model=LeaveRequestRead,
    summary="Approve a current team leave request",
)
async def approve_leave_request(
    request_id: UUID,
    payload: LeaveRequestDecision,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_any_permission("leave:approve:team", "leave:manage:tenant")),
    ],
    command_handler: Annotated[LeaveCommandHandler, Depends(get_leave_command_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> LeaveRequestRead:
    return await _decide(
        action="approve",
        request_id=request_id,
        payload=payload,
        request_context=request_context,
        authorized=authorized,
        command_handler=command_handler,
        idempotency_key=idempotency_key,
    )


@request_router.post(
    "/{request_id}/reject",
    response_model=LeaveRequestRead,
    summary="Reject a current team leave request",
)
async def reject_leave_request(
    request_id: UUID,
    payload: LeaveRequestDecision,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_any_permission("leave:approve:team", "leave:manage:tenant")),
    ],
    command_handler: Annotated[LeaveCommandHandler, Depends(get_leave_command_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> LeaveRequestRead:
    return await _decide(
        action="reject",
        request_id=request_id,
        payload=payload,
        request_context=request_context,
        authorized=authorized,
        command_handler=command_handler,
        idempotency_key=idempotency_key,
    )


@request_router.post(
    "/{request_id}/cancel",
    response_model=LeaveRequestRead,
    summary="Cancel my or an HR-managed leave request",
)
async def cancel_leave_request(
    request_id: UUID,
    payload: LeaveRequestDecision,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_any_permission("leave:cancel:own", "leave:manage:tenant")),
    ],
    command_handler: Annotated[LeaveCommandHandler, Depends(get_leave_command_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> LeaveRequestRead:
    return await _decide(
        action="cancel",
        request_id=request_id,
        payload=payload,
        request_context=request_context,
        authorized=authorized,
        command_handler=command_handler,
        idempotency_key=idempotency_key,
    )


@approval_router.get(
    "/api/v1/approval-tasks",
    response_model=list[ApprovalTaskRead],
    summary="List current manager leave approval tasks",
    responses={
        status.HTTP_200_OK: {
            "headers": {NEXT_CURSOR_HEADER: {"schema": {"type": "string"}}}
        }
    },
)
async def list_approval_tasks(
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_any_permission("leave:approve:team", "leave:manage:tenant")),
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    limit: Annotated[int, Query(ge=1, le=LEAVE_LIST_MAX_LIMIT)] = LEAVE_LIST_DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)] = None,
) -> list[ApprovalTaskRead]:
    try:
        decoded_cursor = (
            ApprovalTaskListCursor.from_token(cursor) if cursor is not None else None
        )
    except (InvalidCursorError, ValidationError) as exc:
        raise LeaveValidationError("The approval task cursor is invalid") from exc
    page = await service.list_approval_tasks(
        request_context=request_context,
        permissions=authorized.user.permissions,
        limit=limit,
        cursor=decoded_cursor,
    )
    return phase0_plain_cursor_list(response, page)


@approval_router.get(
    "/api/v1/team-calendar",
    response_model=list[TeamCalendarEntryRead],
    summary="List approved leave in current manager scope",
)
async def list_team_calendar(
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_any_permission("leave:read:team", "leave:read:tenant")),
    ],
    service: Annotated[LeaveService, Depends(get_leave_service)],
    start_date: Annotated[date, Query()],
    end_date: Annotated[date, Query()],
    scope: Annotated[LeaveAccessScope | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> list[TeamCalendarEntryRead]:
    return await service.list_team_calendar(
        request_context=request_context,
        permissions=authorized.user.permissions,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        scope=scope,
    )


__all__ = [
    "approval_router",
    "balance_router",
    "configuration_router",
    "request_router",
]
