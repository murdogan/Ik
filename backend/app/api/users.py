from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import ValidationError

from app.api.auth_dependencies import (
    AuthenticatedSession,
    get_authenticated_request_context,
    get_authorization_service,
    get_user_administration_service,
    require_permission,
)
from app.api.errors import (
    AUTHENTICATION_REQUIRED_RESPONSES,
    ROLE_ASSIGNMENT_CONFLICT_RESPONSES,
    ROLE_ASSIGNMENT_VALIDATION_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
    USER_ADMINISTRATION_AUTHORIZATION_RESPONSES,
    USER_ADMINISTRATION_CONFLICT_RESPONSES,
    USER_ADMINISTRATION_NOT_FOUND_RESPONSES,
    USER_ADMINISTRATION_VALIDATION_RESPONSES,
    user_administration_validation_error,
)
from app.api.openapi import USER_ADMINISTRATION_TAG, with_correlation_response_headers
from app.models.user import UserStatus
from app.platform.audit import AuditContext
from app.platform.pagination import MAX_CURSOR_LENGTH, InvalidCursorError
from app.platform.request_context import RequestContext
from app.platform.responses import (
    DataEnvelope,
    ListEnvelope,
    data_envelope,
    list_envelope,
)
from app.schemas.authorization import RoleSummaryRead, UserRoleReplace
from app.schemas.user_administration import (
    USER_LIST_DEFAULT_LIMIT,
    USER_LIST_MAX_LIMIT,
    USER_SEARCH_MAX_LENGTH,
    USER_SEARCH_MIN_LENGTH,
    UserAdministrationRead,
    UserAdministrationUpdate,
    UserListCursor,
    UserListPagination,
)
from app.services.authorization_service import (
    AuthorizationService,
    RoleReplacementRecord,
)
from app.services.user_administration_service import (
    UserAdministrationAccessDeniedError,
    UserAdministrationRecord,
    UserAdministrationService,
)

router = APIRouter(
    prefix="/api/v1/users",
    tags=[USER_ADMINISTRATION_TAG],
    responses=with_correlation_response_headers(
        {
            **AUTHENTICATION_REQUIRED_RESPONSES,
            **USER_ADMINISTRATION_AUTHORIZATION_RESPONSES,
            **USER_ADMINISTRATION_VALIDATION_RESPONSES,
            **UNEXPECTED_ERROR_RESPONSES,
        }
    ),
)


def get_user_list_pagination(
    request: Request,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=USER_LIST_MAX_LIMIT,
            description="Maximum users in this bounded page.",
        ),
    ] = USER_LIST_DEFAULT_LIMIT,
    cursor: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=MAX_CURSOR_LENGTH,
            description="Opaque continuation cursor from meta.next_cursor.",
        ),
    ] = None,
    search: Annotated[
        str | None,
        Query(
            min_length=USER_SEARCH_MIN_LENGTH,
            max_length=USER_SEARCH_MAX_LENGTH,
            description="Case-insensitive name or email substring search.",
        ),
    ] = None,
    user_status: Annotated[
        UserStatus | None,
        Query(
            alias="status",
            description="Optional exact account-status filter.",
        ),
    ] = None,
) -> UserListPagination:
    bounded_keys = ("limit", "cursor", "search", "status")
    if "offset" in request.query_params or any(
        len(request.query_params.getlist(key)) > 1 for key in bounded_keys
    ):
        raise user_administration_validation_error()
    try:
        decoded_cursor = UserListCursor.from_token(cursor) if cursor is not None else None
        return UserListPagination(
            limit=limit,
            cursor=decoded_cursor,
            search=search,
            status=user_status,
        )
    except (InvalidCursorError, ValidationError) as exc:
        raise user_administration_validation_error() from exc


@router.get(
    "",
    response_model=ListEnvelope[UserAdministrationRead],
    summary="List users in the authenticated tenant",
    description=(
        "Lists a bounded cursor page using an explicit single-query projection. Optional name "
        "or email substring search and exact status filtering are tenant-scoped and backed by "
        "dedicated search/order indexes. Tenant and actor come only from the authenticated "
        "RequestContext."
    ),
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def list_users(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[
        UserAdministrationService,
        Depends(get_user_administration_service),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                "user:read:tenant",
                denied_error=UserAdministrationAccessDeniedError,
            )
        ),
    ],
    pagination: Annotated[UserListPagination, Depends(get_user_list_pagination)],
) -> ListEnvelope[UserAdministrationRead]:
    _prevent_storage(response)
    page = await service.list_users(
        request_context=request_context,
        pagination=pagination,
        granted_permissions=authorized.user.permissions,
    )
    return list_envelope(
        [_user_read(user) for user in page.items],
        request_context,
        limit=pagination.limit,
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{user_id}",
    response_model=DataEnvelope[UserAdministrationRead],
    summary="Read one user in the authenticated tenant",
    description=(
        "Returns an allowlisted account projection only when the target belongs to the tenant "
        "derived from the authenticated RequestContext. Missing and cross-tenant identifiers "
        "share the same not-found response."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **USER_ADMINISTRATION_NOT_FOUND_RESPONSES,
        }
    ),
)
async def get_user(
    user_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[
        UserAdministrationService,
        Depends(get_user_administration_service),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                "user:read:tenant",
                denied_error=UserAdministrationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[UserAdministrationRead]:
    _prevent_storage(response)
    user = await service.get_user(
        request_context=request_context,
        user_id=user_id,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(_user_read(user), request_context)


@router.patch(
    "/{user_id}",
    response_model=DataEnvelope[UserAdministrationRead],
    summary="Update one user in the authenticated tenant",
    description=(
        "Updates only full_name and status. Tenant, actor, email, invitation capability, and "
        "authorization fields are rejected from the payload. Status transitions preserve "
        "activation invariants and revoke live credentials when an account is locked or "
        "disabled."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **USER_ADMINISTRATION_NOT_FOUND_RESPONSES,
            **USER_ADMINISTRATION_CONFLICT_RESPONSES,
        }
    ),
)
async def update_user(
    user_id: UUID,
    payload: UserAdministrationUpdate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[
        UserAdministrationService,
        Depends(get_user_administration_service),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                "user:update:tenant",
                denied_error=UserAdministrationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[UserAdministrationRead]:
    _prevent_storage(response)
    user = await service.update_user(
        request_context=request_context,
        user_id=user_id,
        update=payload,
        granted_permissions=authorized.user.permissions,
        audit_context=AuditContext.from_request_context(request_context),
    )
    return data_envelope(_user_read(user), request_context)


@router.put(
    "/{user_id}/roles",
    response_model=DataEnvelope[UserAdministrationRead],
    summary="Replace one tenant user's role assignments",
    description=(
        "Atomically replaces the complete active tenant-role set. Platform roles and "
        "cross-tenant targets fail closed; an actual change increments permission_version so "
        "previously issued access credentials stop authorizing immediately."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **USER_ADMINISTRATION_NOT_FOUND_RESPONSES,
            **ROLE_ASSIGNMENT_VALIDATION_RESPONSES,
            **ROLE_ASSIGNMENT_CONFLICT_RESPONSES,
        }
    ),
)
async def replace_user_roles(
    user_id: UUID,
    payload: UserRoleReplace,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                "role:assign:tenant",
                denied_error=UserAdministrationAccessDeniedError,
            )
        ),
    ],
    service: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> DataEnvelope[UserAdministrationRead]:
    _prevent_storage(response)
    user = await service.replace_user_roles(
        tenant_id=request_context.require_tenant().tenant_id,
        actor_id=authorized.user.id,
        user_id=user_id,
        role_ids=tuple(payload.role_ids),
        actor_session_id=request_context.session_id,
        audit_context=AuditContext.from_request_context(request_context),
    )
    return data_envelope(_user_read(user), request_context)


def _user_read(
    user: UserAdministrationRecord | RoleReplacementRecord,
) -> UserAdministrationRead:
    return UserAdministrationRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        status=user.status,
        roles=[
            RoleSummaryRead(
                id=role.id,
                code=role.code,
                name=role.name,
                scope_type=role.scope_type,
            )
            for role in user.roles
        ],
        permission_version=user.permission_version,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["router"]
