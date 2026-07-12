"""Tenant-visible RBAC catalogs."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.auth_dependencies import (
    AuthenticatedSession,
    get_authenticated_request_context,
    get_authorization_service,
    require_permission,
)
from app.api.errors import (
    AUTHENTICATION_REQUIRED_RESPONSES,
    AUTHORIZATION_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
)
from app.api.openapi import AUTHORIZATION_TAG, with_correlation_response_headers
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.authorization import PermissionRead, RoleRead
from app.services.authorization_service import AuthorizationService

router = APIRouter(
    prefix="/api/v1",
    tags=[AUTHORIZATION_TAG],
    responses=with_correlation_response_headers(
        {
            **AUTHENTICATION_REQUIRED_RESPONSES,
            **AUTHORIZATION_RESPONSES,
            **UNEXPECTED_ERROR_RESPONSES,
        }
    ),
)


@router.get(
    "/roles",
    response_model=DataEnvelope[list[RoleRead]],
    summary="List tenant-assignable system roles",
    description=(
        "Returns only seeded tenant roles and their explicit permission codes. Platform roles "
        "are never exposed through the tenant assignment surface."
    ),
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def list_roles(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("role:read:tenant")),
    ],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> DataEnvelope[list[RoleRead]]:
    _prevent_storage(response)
    roles = await service.list_tenant_roles(
        tenant_id=request_context.require_tenant().tenant_id
    )
    return data_envelope(
        [
            RoleRead(
                id=role.id,
                code=role.code,
                name=role.name,
                description=role.description,
                scope_type=role.scope_type,
                permissions=list(role.permissions),
            )
            for role in roles
        ],
        request_context,
    )


@router.get(
    "/permissions",
    response_model=DataEnvelope[list[PermissionRead]],
    summary="List tenant permission catalog",
    description="Returns the explicit tenant permission vocabulary available to seeded roles.",
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def list_permissions(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("permission:read:tenant")),
    ],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> DataEnvelope[list[PermissionRead]]:
    _prevent_storage(response)
    permissions = await service.list_tenant_permissions(
        tenant_id=request_context.require_tenant().tenant_id
    )
    return data_envelope(
        [
            PermissionRead(
                id=permission.id,
                code=permission.code,
                resource=permission.resource,
                action=permission.action,
                scope=permission.scope,
                description=permission.description,
            )
            for permission in permissions
        ],
        request_context,
    )


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["router"]
