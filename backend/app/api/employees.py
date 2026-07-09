from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_context
from app.api.errors import ApiError
from app.core.tenancy import TenantContext
from app.db.session import get_session
from app.models.employee import EmployeeStatus
from app.schemas.employee import (
    EMPLOYEE_LIST_DEFAULT_LIMIT,
    EMPLOYEE_LIST_MAX_LIMIT,
    EmployeeCreate,
    EmployeeListFilters,
    EmployeeListPagination,
    EmployeeRead,
    EmployeeUpdate,
)
from app.services.employee_service import (
    DuplicateEmployeeNumberError,
    EmployeeDateRangeError,
    EmployeeNotFoundError,
    EmployeeService,
)

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


def get_employee_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EmployeeService:
    return EmployeeService(session=session)


def get_employee_list_filters(
    department: Annotated[
        str | None,
        Query(description="Exact department filter. Case-insensitive."),
    ] = None,
    status_filter: Annotated[
        EmployeeStatus | None,
        Query(alias="status", description="Employment lifecycle status filter."),
    ] = None,
    q: Annotated[
        str | None,
        Query(
            description="Case-insensitive search over employee_number and email.",
            max_length=320,
        ),
    ] = None,
) -> EmployeeListFilters:
    return EmployeeListFilters(department=department, status=status_filter, q=q)


def get_employee_list_pagination(
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=EMPLOYEE_LIST_MAX_LIMIT,
            description="Maximum employees to return. Bounded to protect large tenant lists.",
        ),
    ] = EMPLOYEE_LIST_DEFAULT_LIMIT,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of matching employees to skip before returning results."),
    ] = 0,
) -> EmployeeListPagination:
    return EmployeeListPagination(limit=limit, offset=offset)


@router.get("", response_model=list[EmployeeRead])
async def list_employees(
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[EmployeeService, Depends(get_employee_service)],
    filters: Annotated[EmployeeListFilters, Depends(get_employee_list_filters)],
    pagination: Annotated[EmployeeListPagination, Depends(get_employee_list_pagination)],
) -> list[EmployeeRead]:
    return await service.list_employees(tenant_context.tenant_id, filters, pagination)


@router.post("", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: EmployeeCreate,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[EmployeeService, Depends(get_employee_service)],
) -> EmployeeRead:
    try:
        return await service.create_employee(tenant_context.tenant_id, payload)
    except DuplicateEmployeeNumberError as exc:
        raise _duplicate_employee_number_error() from exc


@router.get("/{employee_id}", response_model=EmployeeRead)
async def get_employee(
    employee_id: UUID,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[EmployeeService, Depends(get_employee_service)],
) -> EmployeeRead:
    try:
        return await service.get_employee(tenant_context.tenant_id, employee_id)
    except EmployeeNotFoundError as exc:
        raise _employee_not_found_error() from exc


@router.patch("/{employee_id}", response_model=EmployeeRead)
async def update_employee(
    employee_id: UUID,
    payload: EmployeeUpdate,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[EmployeeService, Depends(get_employee_service)],
) -> EmployeeRead:
    try:
        return await service.update_employee(tenant_context.tenant_id, employee_id, payload)
    except EmployeeNotFoundError as exc:
        raise _employee_not_found_error() from exc
    except DuplicateEmployeeNumberError as exc:
        raise _duplicate_employee_number_error() from exc
    except EmployeeDateRangeError as exc:
        raise _employee_date_range_error(exc) from exc


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    employee_id: UUID,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[EmployeeService, Depends(get_employee_service)],
) -> Response:
    try:
        await service.delete_employee(tenant_context.tenant_id, employee_id)
    except EmployeeNotFoundError as exc:
        raise _employee_not_found_error() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _employee_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="employee_not_found",
        message="Employee not found",
    )


def _duplicate_employee_number_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="employee_number_conflict",
        message="Employee number already exists for this tenant",
    )


def _employee_date_range_error(exc: EmployeeDateRangeError) -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="employee_invalid_date_range",
        message=str(exc),
    )
