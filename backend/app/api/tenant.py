from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_tenant_command_handler,
    get_tenant_feature_service,
    get_tenant_principal_request_context,
    get_tenant_service,
)
from app.api.errors import (
    TENANT_AUTHORIZATION_RESPONSES,
    TENANT_CLOSED_RESPONSES,
    TENANT_NOT_FOUND_RESPONSES,
    TENANT_NOT_READY_RESPONSES,
    TENANT_SETTINGS_VALIDATION_RESPONSES,
    TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
)
from app.api.openapi import TENANT_SETTINGS_TAG, with_correlation_response_headers
from app.models.tenant import Tenant
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.tenant import (
    TenantFeatureFlagRead,
    TenantFeaturesRead,
    TenantRead,
    TenantSettingsRead,
    TenantSettingsUpdate,
)
from app.services.tenant_commands import TenantCommandHandler
from app.services.tenant_feature_service import (
    TenantFeatureService,
    TenantFeatureSnapshot,
)
from app.services.tenant_service import TenantService, TenantSettingsSnapshot

router = APIRouter(
    prefix="/api/v1/tenant",
    tags=[TENANT_SETTINGS_TAG],
    dependencies=[Depends(get_tenant_principal_request_context)],
    responses=with_correlation_response_headers({
        **TENANT_AUTHORIZATION_RESPONSES,
        **TENANT_SETTINGS_VALIDATION_RESPONSES,
        **UNEXPECTED_ERROR_RESPONSES,
    }),
)


@router.get(
    "",
    response_model=DataEnvelope[TenantRead],
    summary="Read current tenant metadata",
    description=(
        "Reads basic tenant metadata from the injected trusted tenant principal. Caller-supplied "
        "headers, user IDs, and tenant IDs do not select or authorize this resource. Provisioning "
        "tenants are not ready, closed tenants are unavailable, and suspended or offboarding "
        "tenants retain read-only metadata access."
    ),
    response_description="Current tenant data with safe request metadata.",
    responses=with_correlation_response_headers({
        200: {},
        **TENANT_NOT_FOUND_RESPONSES,
        **TENANT_CLOSED_RESPONSES,
        **TENANT_NOT_READY_RESPONSES,
    }),
)
async def get_current_tenant(
    request_context: Annotated[
        RequestContext,
        Depends(get_tenant_principal_request_context),
    ],
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> DataEnvelope[TenantRead]:
    tenant = await service.get_current_tenant(request_context.require_tenant().tenant_id)
    return data_envelope(_tenant_read(tenant), request_context)


@router.get(
    "/settings",
    response_model=DataEnvelope[TenantSettingsRead],
    summary="Read typed tenant settings",
    description=(
        "Reads only the fixed locale, IANA timezone, week-start, date-format, and time-format "
        "settings for the injected tenant principal. Suspended and offboarding tenants may read "
        "settings; provisioning and closed tenants cannot use the tenant surface."
    ),
    response_description="Current typed settings with safe request metadata.",
    responses=with_correlation_response_headers({
        200: {},
        **TENANT_NOT_FOUND_RESPONSES,
        **TENANT_CLOSED_RESPONSES,
        **TENANT_NOT_READY_RESPONSES,
    }),
)
async def get_current_tenant_settings(
    request_context: Annotated[
        RequestContext,
        Depends(get_tenant_principal_request_context),
    ],
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> DataEnvelope[TenantSettingsRead]:
    snapshot = await service.get_tenant_settings(
        request_context.require_tenant().tenant_id
    )
    return data_envelope(_tenant_settings_read(snapshot), request_context)


@router.patch(
    "/settings",
    response_model=DataEnvelope[TenantSettingsRead],
    summary="Update typed tenant settings",
    description=(
        "Partially updates the fixed typed settings allowlist for the injected tenant principal. "
        "Arbitrary keys, null values, nested settings bags, tenant IDs, and user IDs are rejected. "
        "Only trial or active tenants may write; suspended and offboarding tenants are read-only."
    ),
    response_description="Updated typed settings with safe request metadata.",
    responses=with_correlation_response_headers({
        200: {},
        **TENANT_NOT_FOUND_RESPONSES,
        **TENANT_CLOSED_RESPONSES,
        **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
    }),
)
async def update_current_tenant_settings(
    payload: TenantSettingsUpdate,
    request_context: Annotated[
        RequestContext,
        Depends(get_tenant_principal_request_context),
    ],
    command_handler: Annotated[
        TenantCommandHandler,
        Depends(get_tenant_command_handler),
    ],
) -> DataEnvelope[TenantSettingsRead]:
    snapshot = await command_handler.update_tenant_settings(
        request_context.require_tenant().tenant_id,
        payload,
        request_context=request_context,
    )
    return data_envelope(_tenant_settings_read(snapshot), request_context)


@router.get(
    "/features",
    response_model=DataEnvelope[TenantFeaturesRead],
    summary="Read current tenant feature flags",
    description=(
        "Reads the fixed module-rollout catalog for only the injected tenant principal. The "
        "request accepts no tenant selector, and caller headers, query values, or payload fields "
        "cannot switch tenant scope. Provisioning tenants are not ready and closed tenants are "
        "unavailable; suspended and offboarding tenants retain read-only visibility."
    ),
    response_description="Effective allowlisted feature flags with safe request metadata.",
    responses=with_correlation_response_headers({
        200: {},
        **TENANT_NOT_FOUND_RESPONSES,
        **TENANT_CLOSED_RESPONSES,
        **TENANT_NOT_READY_RESPONSES,
    }),
)
async def get_current_tenant_features(
    request_context: Annotated[
        RequestContext,
        Depends(get_tenant_principal_request_context),
    ],
    service: Annotated[
        TenantFeatureService,
        Depends(get_tenant_feature_service),
    ],
) -> DataEnvelope[TenantFeaturesRead]:
    features = await service.get_tenant_features(
        request_context.require_tenant().tenant_id,
        enforce_tenant_lifecycle=True,
    )
    return data_envelope(_tenant_features_read(features), request_context)


def _tenant_read(tenant: Tenant) -> TenantRead:
    return TenantRead.model_validate(tenant)


def _tenant_settings_read(snapshot: TenantSettingsSnapshot) -> TenantSettingsRead:
    return TenantSettingsRead.model_validate(snapshot, from_attributes=True)


def _tenant_features_read(
    features: tuple[TenantFeatureSnapshot, ...],
) -> TenantFeaturesRead:
    return TenantFeaturesRead(
        features=[
            TenantFeatureFlagRead.model_validate(feature, from_attributes=True)
            for feature in features
        ]
    )
