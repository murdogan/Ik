from typing import Annotated
from uuid import UUID

from fastapi import Header

from app.core.tenancy import TenantContext


def get_tenant_context(
    x_tenant_id: Annotated[UUID, Header(alias="X-Tenant-Id")],
    x_tenant_slug: Annotated[str | None, Header(alias="X-Tenant-Slug")] = None,
) -> TenantContext:
    return TenantContext(tenant_id=x_tenant_id, slug=x_tenant_slug or str(x_tenant_id))
