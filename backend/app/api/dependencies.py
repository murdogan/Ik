from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Header, Request

from app.api.errors import (
    TENANT_ID_HEADER,
    TENANT_SLUG_HEADER,
    tenant_header_invalid_error,
    tenant_header_missing_error,
    tenant_slug_header_invalid_error,
)
from app.core.tenancy import TenantContext


def get_tenant_context(
    request: Request,
    x_tenant_id: Annotated[
        str,
        Header(
            alias=TENANT_ID_HEADER,
            description=(
                "Required current tenant id. Must be a single canonical hyphenated UUID."
            ),
        ),
    ],
    x_tenant_slug: Annotated[
        str | None,
        Header(
            alias=TENANT_SLUG_HEADER,
            description="Optional current tenant slug. Must be non-empty when provided.",
        ),
    ] = None,
) -> TenantContext:
    tenant_id = _parse_tenant_id_header(
        _single_header_value(
            request,
            TENANT_ID_HEADER,
            fallback=x_tenant_id,
            duplicate_error_factory=tenant_header_invalid_error,
        )
    )
    return TenantContext(
        tenant_id=tenant_id,
        slug=_parse_tenant_slug_header(
            _single_header_value(
                request,
                TENANT_SLUG_HEADER,
                fallback=x_tenant_slug,
                duplicate_error_factory=tenant_slug_header_invalid_error,
            ),
            tenant_id,
        ),
    )


def _single_header_value(
    request: Request,
    header_name: str,
    *,
    fallback: str | None,
    duplicate_error_factory: Callable[[], Exception],
) -> str | None:
    values = request.headers.getlist(header_name)
    if len(values) > 1:
        raise duplicate_error_factory()
    if len(values) == 1:
        return values[0]
    return fallback


def _parse_tenant_id_header(value: str | None) -> UUID:
    if value is None:
        raise tenant_header_missing_error()

    clean_value = value.strip()
    if not clean_value:
        raise tenant_header_missing_error()
    if clean_value != value:
        raise tenant_header_invalid_error()

    try:
        tenant_id = UUID(value)
    except ValueError as exc:
        raise tenant_header_invalid_error() from exc

    if value != str(tenant_id):
        raise tenant_header_invalid_error()
    return tenant_id


def _parse_tenant_slug_header(value: str | None, tenant_id: UUID) -> str:
    if value is None:
        return str(tenant_id)

    clean_value = value.strip()
    if not clean_value:
        raise tenant_slug_header_invalid_error()
    return clean_value
