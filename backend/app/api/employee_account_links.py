"""HR employee-account linkage and own-scope profile endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import AuthenticatedSession, require_permission
from app.api.dependencies import get_authenticated_tenant_request_context, get_unit_of_work
from app.api.errors import (
    AUTHENTICATION_REQUIRED_RESPONSES,
    AUTHORIZATION_RESPONSES,
    EMPLOYEE_ACCOUNT_LINK_CONFLICT_RESPONSES,
    EMPLOYEE_VALIDATION_RESPONSES,
)
from app.api.openapi import EMPLOYEES_TAG, with_correlation_response_headers
from app.db.session import get_session
from app.platform.db import SqlAlchemyUnitOfWork
from app.platform.errors import ApiErrorResponse
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.employee_account_link import (
    ELIGIBLE_MEMBERSHIP_LIMIT_MAX,
    ELIGIBLE_MEMBERSHIP_SEARCH_MAX_LENGTH,
    EmployeeAccountLinkStateRead,
    EmployeeAccountLinkUpdate,
    EmployeeAccountMembershipRead,
    OwnEmployeeProfileStateRead,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.employee_account_link_commands import EmployeeAccountLinkCommandHandler
from app.services.employee_account_link_service import EmployeeAccountLinkService

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
own_router = APIRouter(
    prefix="/api/v1/me",
    tags=[EMPLOYEES_TAG],
    responses=with_correlation_response_headers(
        {
            **AUTHENTICATION_REQUIRED_RESPONSES,
            **AUTHORIZATION_RESPONSES,
        }
    ),
)

_EMPLOYEE_NOT_FOUND_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {
        "model": ApiErrorResponse,
        "description": "The employee is absent, archived, or outside the authenticated tenant.",
    }
}


def get_employee_account_link_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EmployeeAccountLinkService:
    return EmployeeAccountLinkService(session)


def get_employee_account_link_command_handler(
    service: Annotated[
        EmployeeAccountLinkService,
        Depends(get_employee_account_link_service),
    ],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> EmployeeAccountLinkCommandHandler:
    return EmployeeAccountLinkCommandHandler(
        service=service,
        unit_of_work=unit_of_work,
        audit_recorder=SqlAlchemyAuditRecorder(service.session),
    )


@router.get(
    "/{employee_id}/account-link",
    response_model=DataEnvelope[EmployeeAccountLinkStateRead],
    summary="Read an employee account link",
    description=(
        "Returns the tenant-qualified canonical membership currently linked to one active "
        "employee record. Missing and cross-tenant employee identifiers share one response."
    ),
    responses=with_correlation_response_headers(
        {status.HTTP_200_OK: {}, **_EMPLOYEE_NOT_FOUND_RESPONSES}
    ),
)
async def get_employee_account_link(
    employee_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:update:tenant")),
    ],
    service: Annotated[
        EmployeeAccountLinkService,
        Depends(get_employee_account_link_service),
    ],
) -> DataEnvelope[EmployeeAccountLinkStateRead]:
    _prevent_storage(response)
    state = await service.get_account_link(
        request_context.require_tenant().tenant_id,
        employee_id,
    )
    return data_envelope(state, request_context)


@router.get(
    "/{employee_id}/account-link/eligible-memberships",
    response_model=DataEnvelope[list[EmployeeAccountMembershipRead]],
    summary="Find eligible tenant accounts for an employee link",
    description=(
        "Returns at most twenty same-tenant active canonical memberships that are not linked to "
        "another employee. Global identity identifiers are never exposed."
    ),
    responses=with_correlation_response_headers(
        {status.HTTP_200_OK: {}, **_EMPLOYEE_NOT_FOUND_RESPONSES}
    ),
)
async def list_eligible_employee_memberships(
    employee_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:update:tenant")),
    ],
    service: Annotated[
        EmployeeAccountLinkService,
        Depends(get_employee_account_link_service),
    ],
    q: Annotated[
        str | None,
        Query(max_length=ELIGIBLE_MEMBERSHIP_SEARCH_MAX_LENGTH),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=ELIGIBLE_MEMBERSHIP_LIMIT_MAX)] = (
        ELIGIBLE_MEMBERSHIP_LIMIT_MAX
    ),
) -> DataEnvelope[list[EmployeeAccountMembershipRead]]:
    _prevent_storage(response)
    memberships = await service.list_eligible_memberships(
        request_context.require_tenant().tenant_id,
        employee_id,
        query=q,
        limit=limit,
    )
    return data_envelope(memberships, request_context)


@router.patch(
    "/{employee_id}/account-link",
    response_model=DataEnvelope[EmployeeAccountLinkStateRead],
    summary="Link, relink, or unlink an employee account",
    description=(
        "Atomically changes one tenant employee-to-membership link. Initial links require a null "
        "expected version; relinks and unlinks require the current positive version. Same-target "
        "and already-unlinked retries are idempotent."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **_EMPLOYEE_NOT_FOUND_RESPONSES,
            **EMPLOYEE_ACCOUNT_LINK_CONFLICT_RESPONSES,
        }
    ),
)
async def update_employee_account_link(
    employee_id: UUID,
    payload: EmployeeAccountLinkUpdate,
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
        EmployeeAccountLinkCommandHandler,
        Depends(get_employee_account_link_command_handler),
    ],
) -> DataEnvelope[EmployeeAccountLinkStateRead]:
    _prevent_storage(response)
    state = await handler.update_account_link(
        request_context.require_tenant().tenant_id,
        employee_id,
        payload,
        request_context=request_context,
    )
    return data_envelope(state, request_context)


@own_router.get(
    "/employee-profile",
    response_model=DataEnvelope[OwnEmployeeProfileStateRead],
    summary="Read my linked employee profile",
    description=(
        "Resolves the selected tenant and canonical membership only from the authenticated "
        "request context, then returns a dedicated allowlisted own-profile projection."
    ),
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def get_own_employee_profile(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:read:own")),
    ],
    service: Annotated[
        EmployeeAccountLinkService,
        Depends(get_employee_account_link_service),
    ],
) -> DataEnvelope[OwnEmployeeProfileStateRead]:
    _prevent_storage(response)
    if request_context.actor_id is None:
        raise RuntimeError("Authenticated own-profile context is missing its actor")
    state = await service.get_own_profile(
        request_context.require_tenant().tenant_id,
        request_context.require_membership(),
        request_context.actor_id,
    )
    return data_envelope(state, request_context)


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["own_router", "router"]
