"""Authenticated tenant legal-entity and branch/location HTTP contracts."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import ValidationError

from app.api.auth_dependencies import (
    AuthenticatedSession,
    get_authenticated_request_context,
    get_database_runtime,
    require_permission,
)
from app.api.errors import (
    AUTHENTICATION_REQUIRED_RESPONSES,
    ORGANIZATION_AUTHORIZATION_RESPONSES,
    ORGANIZATION_CONFLICT_RESPONSES,
    ORGANIZATION_NOT_FOUND_RESPONSES,
    ORGANIZATION_VALIDATION_RESPONSES,
    TENANT_CLOSED_RESPONSES,
    TENANT_NOT_READY_RESPONSES,
    TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
    organization_pagination_validation_error,
)
from app.api.openapi import ORGANIZATION_TAG, with_correlation_response_headers
from app.db.session import DatabaseRuntime
from app.models.organization import Branch, BranchStatus
from app.platform.pagination import MAX_CURSOR_LENGTH, InvalidCursorError
from app.platform.request_context import RequestContext
from app.platform.responses import (
    DataEnvelope,
    ListEnvelope,
    data_envelope,
    list_envelope,
)
from app.schemas.organization import (
    ORGANIZATION_LIST_DEFAULT_LIMIT,
    ORGANIZATION_LIST_MAX_LIMIT,
    BranchCreate,
    BranchListCursor,
    BranchListPagination,
    BranchRead,
    BranchUpdate,
    LegalEntityCreate,
    LegalEntityListCursor,
    LegalEntityListPagination,
    LegalEntityRead,
    LegalEntityUpdate,
)
from app.services.organization_service import (
    ORGANIZATION_READ_PERMISSION,
    ORGANIZATION_UPDATE_PERMISSION,
    OrganizationAccessDeniedError,
    OrganizationService,
)

_COMMON_RESPONSES = with_correlation_response_headers(
    {
        **AUTHENTICATION_REQUIRED_RESPONSES,
        **ORGANIZATION_AUTHORIZATION_RESPONSES,
        **ORGANIZATION_VALIDATION_RESPONSES,
        **ORGANIZATION_NOT_FOUND_RESPONSES,
        **TENANT_CLOSED_RESPONSES,
        **TENANT_NOT_READY_RESPONSES,
        **UNEXPECTED_ERROR_RESPONSES,
    }
)

legal_entities_router = APIRouter(
    prefix="/api/v1/legal-entities",
    tags=[ORGANIZATION_TAG],
    responses=_COMMON_RESPONSES,
)
branches_router = APIRouter(
    prefix="/api/v1/branches",
    tags=[ORGANIZATION_TAG],
    responses=_COMMON_RESPONSES,
)


def get_organization_service(
    runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> OrganizationService:
    return OrganizationService(session_factory=runtime.session_factory)


def get_legal_entity_list_pagination(
    request: Request,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=ORGANIZATION_LIST_MAX_LIMIT,
            description="Maximum legal entities in this bounded cursor page.",
        ),
    ] = ORGANIZATION_LIST_DEFAULT_LIMIT,
    cursor: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=MAX_CURSOR_LENGTH,
            description="Opaque continuation cursor from meta.next_cursor.",
        ),
    ] = None,
) -> LegalEntityListPagination:
    if "offset" in request.query_params or any(
        len(request.query_params.getlist(key)) > 1 for key in ("limit", "cursor")
    ):
        raise organization_pagination_validation_error()
    try:
        decoded = LegalEntityListCursor.from_token(cursor) if cursor is not None else None
        return LegalEntityListPagination(limit=limit, cursor=decoded)
    except (InvalidCursorError, ValidationError, ValueError) as exc:
        raise organization_pagination_validation_error() from exc


def get_branch_list_pagination(
    request: Request,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=ORGANIZATION_LIST_MAX_LIMIT,
            description="Maximum branches in this bounded cursor page.",
        ),
    ] = ORGANIZATION_LIST_DEFAULT_LIMIT,
    cursor: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=MAX_CURSOR_LENGTH,
            description="Opaque continuation cursor from meta.next_cursor.",
        ),
    ] = None,
    branch_status: Annotated[
        BranchStatus | None,
        Query(alias="status", description="Optional exact branch lifecycle filter."),
    ] = None,
    legal_entity_id: Annotated[
        UUID | None,
        Query(description="Optional current-tenant legal-entity filter."),
    ] = None,
) -> BranchListPagination:
    bounded_keys = ("limit", "cursor", "status", "legal_entity_id")
    if "offset" in request.query_params or any(
        len(request.query_params.getlist(key)) > 1 for key in bounded_keys
    ):
        raise organization_pagination_validation_error()
    try:
        decoded = BranchListCursor.from_token(cursor) if cursor is not None else None
        pagination = BranchListPagination(
            limit=limit,
            cursor=decoded,
            status=branch_status,
            legal_entity_id=legal_entity_id,
        )
        if not pagination.cursor_matches_filters():
            raise ValueError("Branch cursor does not match active filters")
        return pagination
    except (InvalidCursorError, ValidationError, ValueError) as exc:
        raise organization_pagination_validation_error() from exc


@legal_entities_router.get(
    "",
    response_model=ListEnvelope[LegalEntityRead],
    summary="List current-tenant legal entities",
    description=(
        "Returns a bounded cursor page scoped only by the authenticated tenant. Stable legal-"
        "entity codes and the seeded default marker are readable but never act as tenant selectors."
    ),
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def list_legal_entities(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[OrganizationService, Depends(get_organization_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_READ_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
    pagination: Annotated[
        LegalEntityListPagination,
        Depends(get_legal_entity_list_pagination),
    ],
) -> ListEnvelope[LegalEntityRead]:
    _prevent_storage(response)
    page = await service.list_legal_entities(
        request_context=request_context,
        pagination=pagination,
        granted_permissions=authorized.user.permissions,
    )
    return list_envelope(
        [LegalEntityRead.model_validate(entity) for entity in page.items],
        request_context,
        limit=pagination.limit,
        next_cursor=page.next_cursor,
    )


@legal_entities_router.post(
    "",
    response_model=DataEnvelope[LegalEntityRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a current-tenant legal entity",
    description=(
        "Creates an additional active legal entity with a tenant-unique stable code. Tenant and "
        "actor identity come only from the validated bearer session and the write is audited."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_201_CREATED: {},
            **ORGANIZATION_CONFLICT_RESPONSES,
            **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
        }
    ),
)
async def create_legal_entity(
    payload: LegalEntityCreate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[OrganizationService, Depends(get_organization_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_UPDATE_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[LegalEntityRead]:
    _prevent_storage(response)
    entity = await service.create_legal_entity(
        request_context=request_context,
        payload=payload,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(LegalEntityRead.model_validate(entity), request_context)


@legal_entities_router.get(
    "/{legal_entity_id}",
    response_model=DataEnvelope[LegalEntityRead],
    summary="Read a current-tenant legal entity",
    description=(
        "Reads one legal entity only within the authenticated tenant; missing and cross-tenant "
        "identifiers share the same not-found contract."
    ),
    responses=with_correlation_response_headers(
        {status.HTTP_200_OK: {}, **ORGANIZATION_NOT_FOUND_RESPONSES}
    ),
)
async def get_legal_entity(
    legal_entity_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[OrganizationService, Depends(get_organization_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_READ_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[LegalEntityRead]:
    _prevent_storage(response)
    entity = await service.get_legal_entity(
        request_context=request_context,
        legal_entity_id=legal_entity_id,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(LegalEntityRead.model_validate(entity), request_context)


@legal_entities_router.patch(
    "/{legal_entity_id}",
    response_model=DataEnvelope[LegalEntityRead],
    summary="Update a current-tenant legal entity",
    description=(
        "Updates only allowlisted legal-entity settings. The stable code and default marker are "
        "immutable, and the default entity must remain active."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **ORGANIZATION_NOT_FOUND_RESPONSES,
            **ORGANIZATION_CONFLICT_RESPONSES,
            **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
        }
    ),
)
async def update_legal_entity(
    legal_entity_id: UUID,
    payload: LegalEntityUpdate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[OrganizationService, Depends(get_organization_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_UPDATE_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[LegalEntityRead]:
    _prevent_storage(response)
    entity = await service.update_legal_entity(
        request_context=request_context,
        legal_entity_id=legal_entity_id,
        payload=payload,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(LegalEntityRead.model_validate(entity), request_context)


@branches_router.get(
    "",
    response_model=ListEnvelope[BranchRead],
    summary="List current-tenant branches including archived history",
    description=(
        "Returns a bounded cursor page of current-tenant branches. Active and archived records "
        "remain readable, with optional lifecycle and legal-entity filters bound to the cursor."
    ),
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def list_branches(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[OrganizationService, Depends(get_organization_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_READ_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
    pagination: Annotated[BranchListPagination, Depends(get_branch_list_pagination)],
) -> ListEnvelope[BranchRead]:
    _prevent_storage(response)
    page = await service.list_branches(
        request_context=request_context,
        pagination=pagination,
        granted_permissions=authorized.user.permissions,
    )
    return list_envelope(
        [_branch_read(branch) for branch in page.items],
        request_context,
        limit=pagination.limit,
        next_cursor=page.next_cursor,
    )


@branches_router.post(
    "",
    response_model=DataEnvelope[BranchRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a current-tenant branch",
    description=(
        "Creates an active branch under an active current-tenant legal entity. The stable code, "
        "IANA timezone, tenant ownership, RBAC permission, and audit boundary are enforced."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_201_CREATED: {},
            **ORGANIZATION_NOT_FOUND_RESPONSES,
            **ORGANIZATION_CONFLICT_RESPONSES,
            **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
        }
    ),
)
async def create_branch(
    payload: BranchCreate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[OrganizationService, Depends(get_organization_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_UPDATE_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[BranchRead]:
    _prevent_storage(response)
    branch = await service.create_branch(
        request_context=request_context,
        payload=payload,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(_branch_read(branch), request_context)


@branches_router.get(
    "/{branch_id}",
    response_model=DataEnvelope[BranchRead],
    summary="Read a current-tenant branch",
    description=(
        "Reads an active or archived branch only within the authenticated tenant, preserving "
        "historical branch visibility without exposing cross-tenant identifiers."
    ),
    responses=with_correlation_response_headers(
        {status.HTTP_200_OK: {}, **ORGANIZATION_NOT_FOUND_RESPONSES}
    ),
)
async def get_branch(
    branch_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[OrganizationService, Depends(get_organization_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_READ_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[BranchRead]:
    _prevent_storage(response)
    branch = await service.get_branch(
        request_context=request_context,
        branch_id=branch_id,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(_branch_read(branch), request_context)


@branches_router.patch(
    "/{branch_id}",
    response_model=DataEnvelope[BranchRead],
    summary="Update an active current-tenant branch",
    description=(
        "Updates allowlisted location settings while keeping code and legal-entity ownership "
        "stable. Archived branches are terminal historical records and reject updates."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **ORGANIZATION_NOT_FOUND_RESPONSES,
            **ORGANIZATION_CONFLICT_RESPONSES,
            **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
        }
    ),
)
async def update_branch(
    branch_id: UUID,
    payload: BranchUpdate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[OrganizationService, Depends(get_organization_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_UPDATE_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[BranchRead]:
    _prevent_storage(response)
    branch = await service.update_branch(
        request_context=request_context,
        branch_id=branch_id,
        payload=payload,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(_branch_read(branch), request_context)


@branches_router.delete(
    "/{branch_id}",
    response_model=DataEnvelope[BranchRead],
    summary="Archive a current-tenant branch",
    description=(
        "Archives instead of deleting the branch. The row and stable code remain available for "
        "history, while the archived branch can no longer accept new assignments."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **ORGANIZATION_NOT_FOUND_RESPONSES,
            **ORGANIZATION_CONFLICT_RESPONSES,
            **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
        }
    ),
)
async def archive_branch(
    branch_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[OrganizationService, Depends(get_organization_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_UPDATE_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[BranchRead]:
    _prevent_storage(response)
    branch = await service.archive_branch(
        request_context=request_context,
        branch_id=branch_id,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(_branch_read(branch), request_context)


def _branch_read(branch: Branch) -> BranchRead:
    return BranchRead(
        id=branch.id,
        legal_entity_id=branch.legal_entity_id,
        code=branch.code,
        name=branch.name,
        timezone=branch.timezone,
        country_code=branch.country_code,
        city=branch.city,
        address=branch.address,
        status=BranchStatus(branch.status),
        archived_at=branch.archived_at,
        accepts_new_assignments=(
            branch.status == BranchStatus.ACTIVE.value and branch.archived_at is None
        ),
        created_at=branch.created_at,
        updated_at=branch.updated_at,
    )


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["branches_router", "legal_entities_router"]
