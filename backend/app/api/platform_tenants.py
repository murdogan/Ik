from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import (
    get_tenant_command_handler,
    get_tenant_service,
    require_platform_principal,
)
from app.api.errors import (
    PLATFORM_AUTHORIZATION_RESPONSES,
    PLATFORM_TENANT_VALIDATION_RESPONSES,
    TENANT_CREATE_CONFLICT_RESPONSES,
    TENANT_NOT_FOUND_RESPONSES,
    TENANT_UPDATE_CONFLICT_RESPONSES,
)
from app.api.openapi import PLATFORM_TENANTS_TAG
from app.models.tenant import Tenant
from app.modules.core.domain.tenant import health_for_status
from app.schemas.tenant import (
    TENANT_LIST_DEFAULT_LIMIT,
    TENANT_LIST_MAX_LIMIT,
    TenantPlatformCreate,
    TenantPlatformRead,
    TenantPlatformUpdate,
)
from app.services.tenant_commands import TenantCommandHandler
from app.services.tenant_service import TenantService

router = APIRouter(
    prefix="/api/v1/platform/tenants",
    tags=[PLATFORM_TENANTS_TAG],
    dependencies=[Depends(require_platform_principal)],
    responses={
        **PLATFORM_AUTHORIZATION_RESPONSES,
        **PLATFORM_TENANT_VALIDATION_RESPONSES,
    },
)


@router.post(
    "",
    response_model=TenantPlatformRead,
    status_code=status.HTTP_201_CREATED,
    summary="Provision platform tenant",
    description=(
        "Creates tenant metadata and typed default settings under an injected platform principal. "
        "The server generates the tenant ID and always starts the lifecycle in provisioning; "
        "request headers or payload IDs never grant platform authority."
    ),
    response_description="Provisioned tenant metadata and lifecycle-derived health.",
    responses=TENANT_CREATE_CONFLICT_RESPONSES,
)
async def create_platform_tenant(
    payload: TenantPlatformCreate,
    command_handler: Annotated[
        TenantCommandHandler,
        Depends(get_tenant_command_handler),
    ],
) -> TenantPlatformRead:
    tenant = await command_handler.create_tenant(payload)
    return _platform_tenant_read(tenant)


@router.get(
    "",
    response_model=list[TenantPlatformRead],
    summary="List platform tenant metadata",
    description=(
        "Lists a bounded page of tenant identity, plan, region, locale, timezone, status, and "
        "lifecycle-derived health metadata. The query and response do not join or expose "
        "employees, users, leave records, documents, or HR-derived counts."
    ),
    response_description="Bounded platform tenant metadata list.",
)
async def list_platform_tenants(
    service: Annotated[TenantService, Depends(get_tenant_service)],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=TENANT_LIST_MAX_LIMIT,
            description="Maximum tenant metadata rows to return.",
        ),
    ] = TENANT_LIST_DEFAULT_LIMIT,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of tenant metadata rows to skip."),
    ] = 0,
) -> list[TenantPlatformRead]:
    tenants = await service.list_tenants(limit=limit, offset=offset)
    return [_platform_tenant_read(tenant) for tenant in tenants]


@router.get(
    "/{tenant_id}",
    response_model=TenantPlatformRead,
    summary="Read platform tenant metadata",
    description=(
        "Reads one tenant's platform-safe metadata after platform-principal authorization. The "
        "path UUID selects a resource only; it is never treated as proof of authorization, and "
        "the response cannot contain customer HR payloads."
    ),
    response_description="Platform-safe tenant metadata.",
    responses=TENANT_NOT_FOUND_RESPONSES,
)
async def get_platform_tenant(
    tenant_id: UUID,
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> TenantPlatformRead:
    return _platform_tenant_read(await service.get_tenant(tenant_id))


@router.patch(
    "/{tenant_id}",
    response_model=TenantPlatformRead,
    summary="Update platform tenant lifecycle",
    description=(
        "Updates allowlisted tenant metadata under the explicit lifecycle state machine. Closed "
        "is terminal, offboarding is closure-only, and data region can change only while the "
        "tenant remains in provisioning workflow. Slug, tenant ID, and caller identity are not "
        "client-controlled update fields."
    ),
    response_description="Updated tenant metadata and lifecycle-derived health.",
    responses={
        **TENANT_NOT_FOUND_RESPONSES,
        **TENANT_UPDATE_CONFLICT_RESPONSES,
    },
)
async def update_platform_tenant(
    tenant_id: UUID,
    payload: TenantPlatformUpdate,
    command_handler: Annotated[
        TenantCommandHandler,
        Depends(get_tenant_command_handler),
    ],
) -> TenantPlatformRead:
    tenant = await command_handler.update_tenant(tenant_id, payload)
    return _platform_tenant_read(tenant)


def _platform_tenant_read(tenant: Tenant) -> TenantPlatformRead:
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
            "created_at": tenant.created_at,
            "updated_at": tenant.updated_at,
        }
    )
