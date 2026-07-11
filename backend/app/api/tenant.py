from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_tenant_command_handler,
    get_tenant_service,
    require_tenant_principal,
)
from app.api.errors import (
    TENANT_AUTHORIZATION_RESPONSES,
    TENANT_CLOSED_RESPONSES,
    TENANT_NOT_FOUND_RESPONSES,
    TENANT_NOT_READY_RESPONSES,
    TENANT_SETTINGS_VALIDATION_RESPONSES,
    TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
)
from app.api.openapi import TENANT_SETTINGS_TAG
from app.models.tenant import Tenant
from app.platform.principals import TenantPrincipal
from app.schemas.tenant import (
    TenantRead,
    TenantSettingsRead,
    TenantSettingsUpdate,
)
from app.services.tenant_commands import TenantCommandHandler
from app.services.tenant_service import TenantService, TenantSettingsSnapshot

router = APIRouter(
    prefix="/api/v1/tenant",
    tags=[TENANT_SETTINGS_TAG],
    responses={
        **TENANT_AUTHORIZATION_RESPONSES,
        **TENANT_SETTINGS_VALIDATION_RESPONSES,
    },
)


@router.get(
    "",
    response_model=TenantRead,
    summary="Read current tenant metadata",
    description=(
        "Reads basic tenant metadata from the injected trusted tenant principal. Caller-supplied "
        "headers, user IDs, and tenant IDs do not select or authorize this resource. Provisioning "
        "tenants are not ready, closed tenants are unavailable, and suspended or offboarding "
        "tenants retain read-only metadata access."
    ),
    response_description="Current trusted-principal tenant metadata.",
    responses={
        **TENANT_NOT_FOUND_RESPONSES,
        **TENANT_CLOSED_RESPONSES,
        **TENANT_NOT_READY_RESPONSES,
    },
)
async def get_current_tenant(
    principal: Annotated[TenantPrincipal, Depends(require_tenant_principal)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> TenantRead:
    tenant = await service.get_current_tenant(principal.tenant_id)
    return _tenant_read(tenant)


@router.get(
    "/settings",
    response_model=TenantSettingsRead,
    summary="Read typed tenant settings",
    description=(
        "Reads only the fixed locale, IANA timezone, week-start, date-format, and time-format "
        "settings for the injected tenant principal. Suspended and offboarding tenants may read "
        "settings; provisioning and closed tenants cannot use the tenant surface."
    ),
    response_description="Current typed tenant settings.",
    responses={
        **TENANT_NOT_FOUND_RESPONSES,
        **TENANT_CLOSED_RESPONSES,
        **TENANT_NOT_READY_RESPONSES,
    },
)
async def get_current_tenant_settings(
    principal: Annotated[TenantPrincipal, Depends(require_tenant_principal)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> TenantSettingsRead:
    snapshot = await service.get_tenant_settings(principal.tenant_id)
    return _tenant_settings_read(snapshot)


@router.patch(
    "/settings",
    response_model=TenantSettingsRead,
    summary="Update typed tenant settings",
    description=(
        "Partially updates the fixed typed settings allowlist for the injected tenant principal. "
        "Arbitrary keys, null values, nested settings bags, tenant IDs, and user IDs are rejected. "
        "Only trial or active tenants may write; suspended and offboarding tenants are read-only."
    ),
    response_description="Updated typed tenant settings.",
    responses={
        **TENANT_NOT_FOUND_RESPONSES,
        **TENANT_CLOSED_RESPONSES,
        **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
    },
)
async def update_current_tenant_settings(
    payload: TenantSettingsUpdate,
    principal: Annotated[TenantPrincipal, Depends(require_tenant_principal)],
    command_handler: Annotated[
        TenantCommandHandler,
        Depends(get_tenant_command_handler),
    ],
) -> TenantSettingsRead:
    snapshot = await command_handler.update_tenant_settings(
        principal.tenant_id,
        payload,
    )
    return _tenant_settings_read(snapshot)


def _tenant_read(tenant: Tenant) -> TenantRead:
    return TenantRead.model_validate(tenant)


def _tenant_settings_read(snapshot: TenantSettingsSnapshot) -> TenantSettingsRead:
    return TenantSettingsRead.model_validate(snapshot, from_attributes=True)
