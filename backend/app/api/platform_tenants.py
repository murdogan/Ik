from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import ValidationError

from app.api.auth_dependencies import (
    get_application_settings,
    require_platform_permission,
)
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
    TENANT_INITIAL_ADMIN_REISSUE_CONFLICT_RESPONSES,
    TENANT_NOT_FOUND_RESPONSES,
    TENANT_UPDATE_CONFLICT_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
    platform_tenant_pagination_validation_error,
    platform_tenant_validation_error,
)
from app.api.openapi import (
    PLATFORM_PRINCIPAL_OPENAPI,
    PLATFORM_TENANTS_TAG,
    with_correlation_response_headers,
)
from app.core.config import Settings
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
    TenantInitialAdminCorrection,
    TenantInitialAdminManualLinkRead,
    TenantInitialAdminProvisioningRead,
    TenantListCursor,
    TenantListPagination,
    TenantPlatformCreate,
    TenantPlatformCreateRead,
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
    responses=with_correlation_response_headers(
        {
            **PLATFORM_AUTHORIZATION_RESPONSES,
            **PLATFORM_TENANT_VALIDATION_RESPONSES,
            **UNEXPECTED_ERROR_RESPONSES,
        }
    ),
)


@router.post(
    "",
    dependencies=[Depends(require_platform_permission("tenant:create:platform"))],
    openapi_extra=PLATFORM_PRINCIPAL_OPENAPI,
    response_model=DataEnvelope[TenantPlatformCreateRead],
    status_code=status.HTTP_201_CREATED,
    summary="Provision platform tenant",
    description=(
        "Creates tenant metadata, typed default settings, fixed feature defaults, optional "
        "configured active-employee limit metadata, and one invited tenant administrator under "
        "an injected platform principal. The server owns all tenant, identity, membership, role, "
        "and activation identifiers; the server generates the tenant ID, assigns only the system "
        "tenant_admin role, and never returns the activation credential. The tenant always starts "
        "in provisioning."
    ),
    response_description="Provisioned tenant data with safe request metadata.",
    responses=with_correlation_response_headers(
        {
            status.HTTP_201_CREATED: {},
            **TENANT_CREATE_CONFLICT_RESPONSES,
        }
    ),
)
async def create_platform_tenant(
    payload: TenantPlatformCreate,
    request_context: Annotated[RequestContext, Depends(get_platform_request_context)],
    command_handler: Annotated[
        TenantCommandHandler,
        Depends(get_tenant_command_handler),
    ],
) -> DataEnvelope[TenantPlatformCreateRead]:
    tenant = await command_handler.create_tenant(payload, request_context=request_context)
    return data_envelope(_platform_tenant_create_read(tenant), request_context)


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
    dependencies=[Depends(require_platform_permission("tenant:read:platform"))],
    openapi_extra=PLATFORM_PRINCIPAL_OPENAPI,
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
    dependencies=[Depends(require_platform_permission("tenant:read:platform"))],
    openapi_extra=PLATFORM_PRINCIPAL_OPENAPI,
    response_model=DataEnvelope[TenantPlatformRead],
    summary="Read platform tenant metadata",
    description=(
        "Reads one tenant's platform-safe plan, configured limit, region, and lifecycle-derived "
        "health metadata after platform-principal authorization. The path UUID selects a resource "
        "only; it is never treated as proof of authorization, and the response cannot contain "
        "customer HR payloads or HR-derived usage counts."
    ),
    response_description="Platform-safe tenant data with safe request metadata.",
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **TENANT_NOT_FOUND_RESPONSES,
        }
    ),
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
    dependencies=[Depends(require_platform_permission("tenant:update:platform"))],
    openapi_extra=PLATFORM_PRINCIPAL_OPENAPI,
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
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **TENANT_NOT_FOUND_RESPONSES,
            **TENANT_UPDATE_CONFLICT_RESPONSES,
        }
    ),
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


@router.post(
    "/{tenant_id}/initial-admin-invitation/resend",
    dependencies=[Depends(require_platform_permission("tenant:update:platform"))],
    openapi_extra=PLATFORM_PRINCIPAL_OPENAPI,
    response_model=DataEnvelope[TenantInitialAdminProvisioningRead],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Reissue initial tenant administrator invitation",
    description=(
        "Atomically revokes prior activation credentials and prepares a fresh invitation only "
        "for the tenant's original, still-unactivated initial administrator. The response never "
        "reveals the administrator identity, activation credential, or activation path."
    ),
    response_description="Safe invitation preparation status with request metadata.",
    responses=with_correlation_response_headers(
        {
            status.HTTP_202_ACCEPTED: {},
            **TENANT_INITIAL_ADMIN_REISSUE_CONFLICT_RESPONSES,
        }
    ),
)
async def reissue_platform_initial_admin_invitation(
    tenant_id: UUID,
    request_context: Annotated[RequestContext, Depends(get_platform_request_context)],
    command_handler: Annotated[
        TenantCommandHandler,
        Depends(get_tenant_command_handler),
    ],
) -> DataEnvelope[TenantInitialAdminProvisioningRead]:
    await command_handler.reissue_initial_admin_invitation(
        tenant_id,
        request_context=request_context,
    )
    return data_envelope(TenantInitialAdminProvisioningRead(), request_context)


async def require_empty_platform_tenant_request_body(request: Request) -> None:
    """Reject any request-body bytes without buffering a credential-adjacent payload."""

    async for chunk in request.stream():
        if chunk:
            raise platform_tenant_validation_error()


@router.post(
    "/{tenant_id}/initial-admin-invitation/manual-link",
    dependencies=[
        Depends(require_platform_permission("tenant:update:platform")),
        Depends(require_empty_platform_tenant_request_body),
    ],
    openapi_extra=PLATFORM_PRINCIPAL_OPENAPI,
    response_model=DataEnvelope[TenantInitialAdminManualLinkRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a manual initial tenant administrator activation link",
    description=(
        "Atomically revokes prior activation credentials and returns one fresh, expiring, "
        "one-time activation link only for the tenant's original, still-unactivated initial "
        "administrator. The credential is returned only in the URL fragment and is never "
        "persisted in platform audit or outbox metadata."
    ),
    response_description="One-time manual activation link with request metadata.",
    responses=with_correlation_response_headers(
        {
            status.HTTP_201_CREATED: {
                "headers": {
                    "Cache-Control": {
                        "description": "Prevents storage of the credential-bearing response.",
                        "schema": {"type": "string", "const": "no-store"},
                    },
                    "Pragma": {
                        "description": "Legacy cache prevention for credential-bearing clients.",
                        "schema": {"type": "string", "const": "no-cache"},
                    },
                }
            },
            **TENANT_INITIAL_ADMIN_REISSUE_CONFLICT_RESPONSES,
        }
    ),
)
async def create_platform_initial_admin_manual_link(
    tenant_id: UUID,
    response: Response,
    request_context: Annotated[RequestContext, Depends(get_platform_request_context)],
    settings: Annotated[Settings, Depends(get_application_settings)],
    command_handler: Annotated[
        TenantCommandHandler,
        Depends(get_tenant_command_handler),
    ],
) -> DataEnvelope[TenantInitialAdminManualLinkRead]:
    result = await command_handler.create_initial_admin_manual_link(
        tenant_id,
        request_context=request_context,
    )
    activation_url = (
        f"{settings.frontend_base_url}/activate#token="
        f"{quote(result.raw_token, safe='.-_')}"
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return data_envelope(
        TenantInitialAdminManualLinkRead(
            status="manual_link_ready",
            activation_url=activation_url,
            expires_at=result.expires_at,
        ),
        request_context,
    )


@router.patch(
    "/{tenant_id}/initial-admin-invitation",
    dependencies=[Depends(require_platform_permission("tenant:update:platform"))],
    openapi_extra=PLATFORM_PRINCIPAL_OPENAPI,
    response_model=DataEnvelope[TenantInitialAdminProvisioningRead],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Correct initial tenant administrator invitation",
    description=(
        "Atomically corrects the name and email association only for the tenant's original, "
        "still-unactivated initial administrator, revokes prior activation credentials, and "
        "prepares a fresh invitation. It never mutates another tenant membership or a global "
        "identity credential. Neither the response nor the platform audit event ever reveals or "
        "records either administrator email, name, identity state, activation credential, or path."
    ),
    response_description="Safe invitation preparation status with request metadata.",
    responses=with_correlation_response_headers(
        {
            status.HTTP_202_ACCEPTED: {},
            **TENANT_INITIAL_ADMIN_REISSUE_CONFLICT_RESPONSES,
        }
    ),
)
async def correct_platform_initial_admin_invitation(
    tenant_id: UUID,
    payload: TenantInitialAdminCorrection,
    request_context: Annotated[RequestContext, Depends(get_platform_request_context)],
    command_handler: Annotated[
        TenantCommandHandler,
        Depends(get_tenant_command_handler),
    ],
) -> DataEnvelope[TenantInitialAdminProvisioningRead]:
    await command_handler.correct_initial_admin_invitation(
        tenant_id,
        payload,
        request_context=request_context,
    )
    return data_envelope(TenantInitialAdminProvisioningRead(), request_context)


@router.get(
    "/{tenant_id}/features",
    dependencies=[Depends(require_platform_permission("feature:read:platform"))],
    openapi_extra=PLATFORM_PRINCIPAL_OPENAPI,
    response_model=DataEnvelope[TenantFeaturesRead],
    summary="Read platform tenant feature flags",
    description=(
        "Reads the fixed module-rollout catalog and effective tenant overrides through the "
        "metadata-only platform capability. No employee, user, leave, document, or HR-derived "
        "usage data is queried or returned."
    ),
    response_description="Effective allowlisted feature flags with safe request metadata.",
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **TENANT_NOT_FOUND_RESPONSES,
        }
    ),
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
    dependencies=[Depends(require_platform_permission("feature:update:platform"))],
    openapi_extra=PLATFORM_PRINCIPAL_OPENAPI,
    response_model=DataEnvelope[TenantFeaturesRead],
    summary="Update platform tenant feature flags",
    description=(
        "Updates only enum-keyed strict-boolean module rollout overrides under the injected "
        "platform principal. Unknown, duplicate, null, numeric, string, and arbitrary nested "
        "flag values are rejected; closed and offboarding tenants are immutable."
    ),
    response_description="Updated effective feature flags with safe request metadata.",
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **TENANT_NOT_FOUND_RESPONSES,
            **TENANT_UPDATE_CONFLICT_RESPONSES,
        }
    ),
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
            "created_at": _aware_utc(tenant.created_at),
            "updated_at": _aware_utc(tenant.updated_at),
        }
    )


def _platform_tenant_create_read(tenant: Tenant) -> TenantPlatformCreateRead:
    return TenantPlatformCreateRead.model_validate(
        {
            **_platform_tenant_read(tenant).model_dump(),
            "initial_admin": {"status": "invitation_prepared"},
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


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise RuntimeError("Tenant timestamps must be datetimes")
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
