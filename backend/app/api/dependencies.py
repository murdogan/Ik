from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import (
    IDEMPOTENCY_KEY_HEADER,
    TENANT_ID_HEADER,
    TENANT_SLUG_HEADER,
    idempotency_key_invalid_error,
    platform_access_denied_error,
    tenant_access_denied_error,
    tenant_header_invalid_error,
    tenant_header_missing_error,
    tenant_slug_header_invalid_error,
)
from app.db.session import get_session
from app.platform.db import (
    DatabaseAccessContext,
    DatabaseAccessPath,
    SqlAlchemyUnitOfWork,
)
from app.platform.db.tenant_access import DATABASE_ACCESS_CONTEXT_STATE_KEY
from app.platform.events import (
    DiscardingPlatformEventRecorder,
    PlatformEventRecorder,
)
from app.platform.observability.correlation import (
    get_or_create_request_context,
    replace_request_context,
)
from app.platform.principals import PlatformPrincipal, TenantPrincipal
from app.platform.request_context import RequestContext
from app.platform.tenancy import TenantContext
from app.services.command_idempotency import CommandIdempotencyService
from app.services.platform_tenant_queries import PlatformTenantQueryService
from app.services.tenant_commands import TenantCommandHandler
from app.services.tenant_feature_service import TenantFeatureService
from app.services.tenant_service import TenantService


def get_platform_principal() -> PlatformPrincipal:
    """Fail closed until a trusted Phase-2 identity adapter injects platform authority."""

    raise platform_access_denied_error()


def get_tenant_principal() -> TenantPrincipal:
    """Fail closed until a trusted identity adapter injects tenant scope."""

    raise tenant_access_denied_error()


def require_platform_principal(
    principal: Annotated[PlatformPrincipal, Depends(get_platform_principal)],
) -> PlatformPrincipal:
    if not isinstance(principal, PlatformPrincipal):
        raise platform_access_denied_error()
    return principal


def require_tenant_principal(
    principal: Annotated[TenantPrincipal, Depends(get_tenant_principal)],
) -> TenantPrincipal:
    if not isinstance(principal, TenantPrincipal):
        raise tenant_access_denied_error()
    return principal


def get_request_context(request: Request) -> RequestContext:
    """Return the middleware-created immutable context for centralized dependencies."""

    return get_or_create_request_context(request)


def get_platform_request_context(
    request: Request,
    context: Annotated[RequestContext, Depends(get_request_context)],
    _principal: Annotated[PlatformPrincipal, Depends(require_platform_principal)],
) -> RequestContext:
    """Authorize a platform request without trusting caller identity metadata."""

    _set_request_database_access(
        request,
        DatabaseAccessContext(path=DatabaseAccessPath.PLATFORM),
    )
    return replace_request_context(request, context)


def get_tenant_principal_request_context(
    request: Request,
    context: Annotated[RequestContext, Depends(get_request_context)],
    principal: Annotated[TenantPrincipal, Depends(require_tenant_principal)],
) -> RequestContext:
    """Enrich context solely from the trusted Phase-1 tenant-principal seam."""

    enriched = context.derive(
        tenant=TenantContext(
            tenant_id=principal.tenant_id,
            slug=str(principal.tenant_id),
        )
    )
    _set_request_database_access(
        request,
        DatabaseAccessContext(
            path=DatabaseAccessPath.TENANT,
            tenant_id=principal.tenant_id,
        ),
    )
    return replace_request_context(request, enriched)


def get_unit_of_work(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(session=session)


def get_command_idempotency_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CommandIdempotencyService:
    return CommandIdempotencyService(session=session)


def get_tenant_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantService:
    return TenantService(session=session)


def get_platform_tenant_query_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlatformTenantQueryService:
    return PlatformTenantQueryService(session=session)


def get_tenant_feature_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantFeatureService:
    return TenantFeatureService(session=session)


def get_platform_event_recorder() -> PlatformEventRecorder:
    """Contract-only Phase-1 seam; Phase 2 replaces it with same-session persistence."""

    return DiscardingPlatformEventRecorder()


def get_tenant_command_handler(
    service: Annotated[TenantService, Depends(get_tenant_service)],
    feature_service: Annotated[
        TenantFeatureService,
        Depends(get_tenant_feature_service),
    ],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
    event_recorder: Annotated[
        PlatformEventRecorder,
        Depends(get_platform_event_recorder),
    ],
) -> TenantCommandHandler:
    return TenantCommandHandler(
        service=service,
        feature_service=feature_service,
        unit_of_work=unit_of_work,
        event_recorder=event_recorder,
    )


def get_idempotency_key(
    request: Request,
    x_idempotency_key: Annotated[
        str | None,
        Header(
            alias=IDEMPOTENCY_KEY_HEADER,
            description=(
                "Optional tenant-scoped retry key. Reusing it with the same command request "
                "replays the first successful response."
            ),
        ),
    ] = None,
) -> str | None:
    values = request.headers.getlist(IDEMPOTENCY_KEY_HEADER)
    if len(values) > 1:
        raise idempotency_key_invalid_error()
    if not values:
        return x_idempotency_key

    value = values[0]
    if not value or len(value) > 128 or any(character.isspace() for character in value):
        raise idempotency_key_invalid_error()
    return value


def get_phase0_tenant_context(
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


# Historical import retained for Phase-0 tests and adapters. New protected routes must use a
# trusted-principal RequestContext dependency instead.
get_tenant_context = get_phase0_tenant_context


def get_phase0_tenant_request_context(
    request: Request,
    context: Annotated[RequestContext, Depends(get_request_context)],
    tenant: Annotated[TenantContext, Depends(get_phase0_tenant_context)],
) -> RequestContext:
    """Explicitly adapt legacy tenant headers to immutable Phase-0 route context.

    The header remains a compatibility scope selector only. It does not create a trusted
    principal and must not be reused by new protected endpoints.
    """

    _set_request_database_access(
        request,
        DatabaseAccessContext(
            path=DatabaseAccessPath.TENANT,
            tenant_id=tenant.tenant_id,
        ),
    )
    return replace_request_context(request, context.derive(tenant=tenant))


def _set_request_database_access(
    request: Request,
    context: DatabaseAccessContext,
) -> None:
    existing = getattr(request.state, DATABASE_ACCESS_CONTEXT_STATE_KEY, None)
    if existing == context:
        return
    if existing is not None:
        raise RuntimeError("Database access path is immutable for the request lifetime")
    setattr(request.state, DATABASE_ACCESS_CONTEXT_STATE_KEY, context)


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

    if tenant_id.int == 0 or value != str(tenant_id):
        raise tenant_header_invalid_error()
    return tenant_id


def _parse_tenant_slug_header(value: str | None, tenant_id: UUID) -> str:
    if value is None:
        return str(tenant_id)

    clean_value = value.strip()
    if not clean_value:
        raise tenant_slug_header_invalid_error()
    return clean_value
