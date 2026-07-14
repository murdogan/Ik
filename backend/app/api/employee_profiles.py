"""Authenticated Employee 360 aggregate and focused profile updates."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import AuthenticatedSession, require_permission
from app.api.dependencies import (
    get_authenticated_tenant_request_context,
    get_unit_of_work,
)
from app.api.errors import (
    AUTHENTICATION_REQUIRED_RESPONSES,
    AUTHORIZATION_RESPONSES,
    EMPLOYEE_COMMAND_CONFLICT_RESPONSES,
    EMPLOYEE_VALIDATION_RESPONSES,
)
from app.api.openapi import EMPLOYEES_TAG, with_correlation_response_headers
from app.db.session import get_session
from app.platform.db import SqlAlchemyUnitOfWork
from app.platform.errors import ApiErrorResponse
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.employee_profile import (
    EmployeeEmploymentProfileMutationRead,
    EmployeeEmploymentProfileUpdate,
    EmployeePersonalProfileMutationRead,
    EmployeePersonalProfileUpdate,
    EmployeeProfileRead,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.employee_profile_commands import EmployeeProfileCommandHandler
from app.services.employee_profile_service import EmployeeProfileService

router = APIRouter(
    prefix="/api/v1/employees",
    tags=[EMPLOYEES_TAG],
    responses=with_correlation_response_headers(
        {
            **AUTHENTICATION_REQUIRED_RESPONSES,
            **AUTHORIZATION_RESPONSES,
            **EMPLOYEE_VALIDATION_RESPONSES,
        }
    ),
)

_PROFILE_NOT_FOUND_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {
        "model": ApiErrorResponse,
        "description": "The employee is absent or outside the authenticated tenant.",
    }
}


def get_employee_profile_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EmployeeProfileService:
    return EmployeeProfileService(session)


def get_employee_profile_command_handler(
    service: Annotated[
        EmployeeProfileService,
        Depends(get_employee_profile_service),
    ],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> EmployeeProfileCommandHandler:
    return EmployeeProfileCommandHandler(
        service=service,
        unit_of_work=unit_of_work,
        audit_recorder=SqlAlchemyAuditRecorder(service.session),
    )


@router.get(
    "/{employee_id}/profile",
    response_model=DataEnvelope[EmployeeProfileRead],
    summary="Read Employee 360 profile",
    description=(
        "Returns tenant-scoped core identity, focused personal and employment sections, and "
        "read-only current organization plus bounded assignment history from Phase 3. Missing and "
        "cross-tenant employee identifiers use the same not-found response. Authorized HR users "
        "may read retained archived records by direct URL; archived profiles are immutable."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **_PROFILE_NOT_FOUND_RESPONSES,
        }
    ),
)
async def get_employee_profile(
    employee_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:read:tenant")),
    ],
    service: Annotated[
        EmployeeProfileService,
        Depends(get_employee_profile_service),
    ],
) -> DataEnvelope[EmployeeProfileRead]:
    _prevent_storage(response)
    profile = await service.get_employee_profile(
        request_context.require_tenant().tenant_id,
        employee_id,
    )
    return data_envelope(profile, request_context)


@router.patch(
    "/{employee_id}/profile/personal",
    response_model=DataEnvelope[EmployeePersonalProfileMutationRead],
    summary="Update employee personal profile",
    description=(
        "Atomically updates approved personal fields and optional core name/work-email fields. "
        "An expected section version is mandatory; core fields additionally require the "
        "employee version. Stale writes fail without partial persistence or audit."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **_PROFILE_NOT_FOUND_RESPONSES,
            **EMPLOYEE_COMMAND_CONFLICT_RESPONSES,
        }
    ),
)
async def update_employee_personal_profile(
    employee_id: UUID,
    payload: EmployeePersonalProfileUpdate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:update:tenant")),
    ],
    handler: Annotated[
        EmployeeProfileCommandHandler,
        Depends(get_employee_profile_command_handler),
    ],
) -> DataEnvelope[EmployeePersonalProfileMutationRead]:
    _prevent_storage(response)
    updated = await handler.update_personal_profile(
        request_context.require_tenant().tenant_id,
        employee_id,
        payload,
        request_context=request_context,
    )
    return data_envelope(updated, request_context)


@router.patch(
    "/{employee_id}/profile/employment",
    response_model=DataEnvelope[EmployeeEmploymentProfileMutationRead],
    summary="Update employee employment profile",
    description=(
        "Atomically updates approved contract/work codes and optional compatibility start date. "
        "An expected section version is mandatory; start-date changes additionally require "
        "the employee version. Lifecycle status and end-date actions are outside this surface."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **_PROFILE_NOT_FOUND_RESPONSES,
            **EMPLOYEE_COMMAND_CONFLICT_RESPONSES,
        }
    ),
)
async def update_employee_employment_profile(
    employee_id: UUID,
    payload: EmployeeEmploymentProfileUpdate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:update:tenant")),
    ],
    handler: Annotated[
        EmployeeProfileCommandHandler,
        Depends(get_employee_profile_command_handler),
    ],
) -> DataEnvelope[EmployeeEmploymentProfileMutationRead]:
    _prevent_storage(response)
    updated = await handler.update_employment_profile(
        request_context.require_tenant().tenant_id,
        employee_id,
        payload,
        request_context=request_context,
    )
    return data_envelope(updated, request_context)


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


__all__ = ["router"]
