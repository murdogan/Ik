from uuid import UUID

from app.models.tenant import Tenant
from app.platform.db import UnitOfWork
from app.schemas.tenant import (
    TenantPlatformCreate,
    TenantPlatformUpdate,
    TenantSettingsUpdate,
)
from app.services.tenant_service import TenantService, TenantSettingsSnapshot


class TenantCommandHandler:
    """Own tenant command transaction composition without adding repository ceremony."""

    def __init__(self, *, service: TenantService, unit_of_work: UnitOfWork) -> None:
        self.service = service
        self.unit_of_work = unit_of_work

    async def create_tenant(self, payload: TenantPlatformCreate) -> Tenant:
        return await self.unit_of_work.execute(lambda: self.service.create_tenant(payload))

    async def update_tenant(
        self,
        tenant_id: UUID,
        payload: TenantPlatformUpdate,
    ) -> Tenant:
        return await self.unit_of_work.execute(
            lambda: self.service.update_tenant(tenant_id, payload)
        )

    async def update_tenant_settings(
        self,
        tenant_id: UUID,
        payload: TenantSettingsUpdate,
    ) -> TenantSettingsSnapshot:
        return await self.unit_of_work.execute(
            lambda: self.service.update_tenant_settings(tenant_id, payload)
        )
