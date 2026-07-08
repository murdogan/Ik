from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_context
from app.core.tenancy import TenantContext
from app.db.session import get_session
from app.schemas.employee import EmployeeCreate, EmployeeRead, EmployeeUpdate
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


@router.get("", response_model=list[EmployeeRead])
async def list_employees(
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[EmployeeService, Depends(get_employee_service)],
) -> list[EmployeeRead]:
    return await service.list_employees(tenant_context.tenant_id)


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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


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


def _employee_not_found_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Employee not found",
    )


def _duplicate_employee_number_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Employee number already exists for this tenant",
    )
