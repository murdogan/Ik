from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import ValidationError

from app.api.dependencies import (
    get_platform_request_context,
    get_platform_tenant_query_service,
    get_tenant_command_handler,
    get_tenant_feature_service,
)
from app.api.errors import (
    PLATFORM_AUTHORIZATION_RESPONSES,
    PLATFORM_TENANT_VALIDATION_RESPONSES,
    TENANT_CREATE_CONFLICT_RESPONSES,
    TENANT_NOT_FOUND_RESPONSES,
    TENANT_UPDATE_CONFLICT_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
    platform_tenant_pagination_validation_error,
)
from app.api.openapi import PLATFORM_TENANTS_TAG, with_correlation_response_headers
from app.models.tenant import Tenant
from app.modules.core.domain.tenant import health_for_status
from app.platform.pagination import MAX_CURSOR_LENGTH, InvalidCursorError
from app.platform.request_context import RequestContext
from app.platform.responses import (
    DataEnvelope,
    ListEnvelope,
    data_envelope,
    list_envelope,
)
from app.schemas.tenant import (
    TENANT_LIST_DEFAULT_LIMIT,
    TENANT_LIST_MAX_LIMIT,
    TenantFeatureFlagRead,
    TenantFeaturesRead,
    TenantFeaturesUpdate,
    TenantListCursor,
    TenantListPagination,
    TenantPlatformCreate,
    TenantPlatformRead,
    TenantPlatformUpdate,
)
from app.services.platform_tenant_queries import (
    PlatformTenantMetadata,
    PlatformTenantQueryService,
)
from app.services.tenant_commands import TenantCommandHandler
from app.services.tenant_feature_service import (
    TenantFeatureService,
    TenantFeatureSnapshot,
)

router = APIRouter(
    prefix="/api/v1/platform/tenants",
    tags=[PLATFORM_TENANTS_TAG],
    dependencies=[Depends(get_platform_request_context)],
    responses=with_correlation_response_headers({
        **PLATFORM_AUTHORIZATION_RESPONSES,
        **PLATFORM_TENANT_VALIDATION_RESPONSES,
        **UNEXPECTED_ERROR_RESPONSES,
    }),
)


@router.post(
    "",
    response_model=DataEnvelope[TenantPlatformRead],
    status_code=status.HTTP_201_CREATED,
    summary="Provision platform tenant",
    description=(
        "Creates tenant metadata, typed default settings, fixed feature defaults, and optional "
        "configured active-employee limit metadata under an injected platform principal. The "
        "server generates the tenant ID and always starts the lifecycle in provisioning; request "
        "headers or payload IDs never grant platform authority."
    ),
    response_description="Provisioned tenant data with safe request metadata.",
    responses=with_correlation_response_headers({
        status.HTTP_201_CREATED: {},
        **TENANT_CREATE_CONFLICT_RESPONSES,
    }),
)
async def create_platform_tenant(
    payload: TenantPlatformCreate,
    request_context: Annotated[RequestContext, Depends(get_platform_request_context)],
    command_handler: Annotated[
        TenantCommandHandler,
        Depends(get_tenant_command_handler),
    ],
) -> DataEnvelope[TenantPlatformRead]:
    tenant = await command_handler.create_tenant(payload, request_context=request_context)
    return data_envelope(_platform_tenant_read(tenant), request_context)


def get_platform_tenant_list_pagination(
    request: Request,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=TENANT_LIST_MAX_LIMIT,
            description="Maximum tenant metadata rows in this bounded page.",
        ),
    ] = TENANT_LIST_DEFAULT_LIMIT,
    cursor: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=MAX_CURSOR_LENGTH,
            description=(
                "Optional opaque cursor returned as meta.next_cursor by the previous page."
            ),
        ),
    ] = None,
) -> TenantListPagination:
    if (
        "offset" in request.query_params
        or len(request.query_params.getlist("limit")) > 1
        or len(request.query_params.getlist("cursor")) > 1
    ):
        raise platform_tenant_pagination_validation_error()
    try:
        decoded_cursor = TenantListCursor.from_token(cursor) if cursor is not None else None
        return TenantListPagination(limit=limit, cursor=decoded_cursor)
    except (InvalidCursorError, ValidationError) as exc:
        raise platform_tenant_pagination_validation_error() from exc


@router.get(
    "",
    response_model=ListEnvelope[TenantPlatformRead],
    summary="List platform tenant metadata",
    description=(
        "Lists a bounded page of tenant identity, plan, configured limits, region, locale, "
        "timezone, status, and lifecycle-derived health metadata. The explicit projection and "
        "response do not join, count, or expose "
        "employees, users, leave records, documents, or HR-derived counts. Results use an opaque "
        "cursor over the deterministic (created_at, id) order and the Phase-1 data/meta envelope."
    ),
    response_description="Bounded platform tenant metadata page with continuation metadata.",
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def list_platform_tenants(
    request_context: Annotated[RequestContext, Depends(get_platform_request_context)],
    service: Annotated[
        PlatformTenantQueryService,
        Depends(get_platform_tenant_query_service),
    ],
    pagination: Annotated[
        TenantListPagination,
        Depends(get_platform_tenant_list_pagination),
    ],
) -> ListEnvelope[TenantPlatformRead]:
    page = await service.list_tenant_page(pagination)
    return list_envelope(
        [_platform_tenant_read(tenant) for tenant in page.items],
        request_context,
        limit=pagination.limit,
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{tenant_id}",
    response_model=DataEnvelope[TenantPlatformRead],
    summary="Read platform tenant metadata",
    description=(
        "Reads one tenant's platform-safe plan, configured limit, region, and lifecycle-derived "
        "health metadata after platform-principal authorization. The path UUID selects a resource "
        "only; it is never treated as proof of authorization, and the response cannot contain "
        "customer HR payloads or HR-derived usage counts."
    ),
    response_description="Platform-safe tenant data with safe request metadata.",
    responses=with_correlation_response_headers({
        status.HTTP_200_OK: {},
        **TENANT_NOT_FOUND_RESPONSES,
    }),
)
async def get_platform_tenant(
    tenant_id: UUID,
    request_context: Annotated[RequestContext, Depends(get_platform_request_context)],
    service: Annotated[
        PlatformTenantQueryService,
        Depends(get_platform_tenant_query_service),
    ],
) -> DataEnvelope[TenantPlatformRead]:
    return data_envelope(
        _platform_tenant_read(await service.get_tenant(tenant_id)),
        request_context,
    )


@router.patch(
    "/{tenant_id}",
    response_model=DataEnvelope[TenantPlatformRead],
    summary="Update platform tenant lifecycle",
    description=(
        "Updates allowlisted tenant metadata and configured limits under the explicit lifecycle "
        "state machine. Closed is terminal, offboarding is closure-only, terminal transitions "
        "cannot be combined with metadata changes, and data region can change only while the "
        "tenant remains in provisioning workflow. Slug, tenant ID, and caller identity are not "
        "client-controlled update fields."
    ),
    response_description="Updated tenant data with safe request metadata.",
    responses=with_correlation_response_headers({
        status.HTTP_200_OK: {},
        **TENANT_NOT_FOUND_RESPONSES,
        **TENANT_UPDATE_CONFLICT_RESPONSES,
    }),
)
async def update_platform_tenant(
    tenant_id: UUID,
    payload: TenantPlatformUpdate,
    request_context: Annotated[RequestContext, Depends(get_platform_request_context)],
    command_handler: Annotated[
        TenantCommandHandler,
        Depends(get_tenant_command_handler),
    ],
) -> DataEnvelope[TenantPlatformRead]:
    tenant = await command_handler.update_tenant(
        tenant_id,
        payload,
        request_context=request_context,
    )
    return data_envelope(_platform_tenant_read(tenant), request_context)


@router.get(
    "/{tenant_id}/features",
    response_model=DataEnvelope[TenantFeaturesRead],
    summary="Read platform tenant feature flags",
    description=(
        "Reads the fixed module-rollout catalog and effective tenant overrides through the "
        "metadata-only platform capability. No employee, user, leave, document, or HR-derived "
        "usage data is queried or returned."
    ),
    response_description="Effective allowlisted feature flags with safe request metadata.",
    responses=with_correlation_response_headers({
        status.HTTP_200_OK: {},
        **TENANT_NOT_FOUND_RESPONSES,
    }),
)
async def get_platform_tenant_features(
    tenant_id: UUID,
    request_context: Annotated[RequestContext, Depends(get_platform_request_context)],
    service: Annotated[
        TenantFeatureService,
        Depends(get_tenant_feature_service),
    ],
) -> DataEnvelope[TenantFeaturesRead]:
    features = await service.get_tenant_features(
        tenant_id,
        enforce_tenant_lifecycle=False,
    )
    return data_envelope(_tenant_features_read(features), request_context)


@router.patch(
    "/{tenant_id}/features",
    response_model=DataEnvelope[TenantFeaturesRead],
    summary="Update platform tenant feature flags",
    description=(
        "Updates only enum-keyed strict-boolean module rollout overrides under the injected "
        "platform principal. Unknown, duplicate, null, numeric, string, and arbitrary nested "
        "flag values are rejected; closed and offboarding tenants are immutable."
    ),
    response_description="Updated effective feature flags with safe request metadata.",
    responses=with_correlation_response_headers({
        status.HTTP_200_OK: {},
        **TENANT_NOT_FOUND_RESPONSES,
        **TENANT_UPDATE_CONFLICT_RESPONSES,
    }),
)
async def update_platform_tenant_features(
    tenant_id: UUID,
    payload: TenantFeaturesUpdate,
    request_context: Annotated[RequestContext, Depends(get_platform_request_context)],
    command_handler: Annotated[
        TenantCommandHandler,
        Depends(get_tenant_command_handler),
    ],
) -> DataEnvelope[TenantFeaturesRead]:
    features = await command_handler.update_tenant_features(
        tenant_id,
        payload,
        request_context=request_context,
    )
    return data_envelope(_tenant_features_read(features), request_context)


def _platform_tenant_read(
    tenant: PlatformTenantMetadata | Tenant,
) -> TenantPlatformRead:
    return TenantPlatformRead.model_validate(
        {
            "id": tenant.id,
            "slug": tenant.slug,
            "name": tenant.name,
            "status": tenant.status,
            "plan_code": tenant.plan_code,
            "data_region": tenant.data_region,
            "locale": tenant.locale,
            "timezone": tenant.timezone,
            "health": health_for_status(tenant.status),
            "limits": {"active_employees": tenant.active_employee_limit},
            "created_at": tenant.created_at,
            "updated_at": tenant.updated_at,
        }
    )


def _tenant_features_read(
    features: tuple[TenantFeatureSnapshot, ...],
) -> TenantFeaturesRead:
    return TenantFeaturesRead(
        features=[
            TenantFeatureFlagRead.model_validate(feature, from_attributes=True)
            for feature in features
        ]
    )
