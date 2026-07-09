from typing import Annotated
from uuid import UUID

from fastapi import Header

from app.api.errors import (
    TENANT_ID_HEADER,
    TENANT_SLUG_HEADER,
    tenant_header_invalid_error,
    tenant_header_missing_error,
    tenant_slug_header_invalid_error,
)
from app.core.tenancy import TenantContext


def get_tenant_context(
    x_tenant_id: Annotated[str, Header(alias=TENANT_ID_HEADER)],
    x_tenant_slug: Annotated[str | None, Header(alias=TENANT_SLUG_HEADER)] = None,
) -> TenantContext:
    tenant_id = _parse_tenant_id_header(x_tenant_id)
    return TenantContext(
        tenant_id=tenant_id,
        slug=_parse_tenant_slug_header(x_tenant_slug, tenant_id),
    )


def _parse_tenant_id_header(value: str) -> UUID:
    clean_value = value.strip()
    if not clean_value:
        raise tenant_header_missing_error()

    try:
        return UUID(clean_value)
    except ValueError as exc:
        raise tenant_header_invalid_error() from exc


def _parse_tenant_slug_header(value: str | None, tenant_id: UUID) -> str:
    if value is None:
        return str(tenant_id)

    clean_value = value.strip()
    if not clean_value:
        raise tenant_slug_header_invalid_error()
    return clean_value
