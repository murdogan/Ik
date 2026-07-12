from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.errors import authentication_required_error
from app.core.auth_runtime import AUTH_RUNTIME_STATE_KEY, AuthRuntime
from app.core.config import APP_SETTINGS_STATE_KEY, Settings
from app.db.session import DATABASE_RUNTIME_STATE_KEY, DatabaseRuntime
from app.platform.identity import AccessPrincipal, InvalidAccessTokenError
from app.platform.observability.correlation import replace_request_context
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.tenancy import TenantContext
from app.services.auth_session_service import AuthenticatedUser, AuthSessionService
from app.services.authentication_service import AuthenticationService
from app.services.user_administration_service import UserAdministrationService
from app.services.user_invitation_service import UserInvitationService

_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Short-lived access credential returned by the login endpoint.",
)


def get_auth_runtime(request: Request) -> AuthRuntime:
    runtime = getattr(request.app.state, AUTH_RUNTIME_STATE_KEY, None)
    if not isinstance(runtime, AuthRuntime):
        raise RuntimeError("Authentication runtime is unavailable")
    return runtime


def get_database_runtime(request: Request) -> DatabaseRuntime:
    runtime = getattr(request.app.state, DATABASE_RUNTIME_STATE_KEY, None)
    if not isinstance(runtime, DatabaseRuntime):
        raise RuntimeError("Database runtime is unavailable outside application lifespan")
    return runtime


def get_application_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, APP_SETTINGS_STATE_KEY, None)
    if not isinstance(settings, Settings):
        raise RuntimeError("Application settings are unavailable")
    return settings


def get_authentication_service(
    auth_runtime: Annotated[AuthRuntime, Depends(get_auth_runtime)],
    database_runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> AuthenticationService:
    return AuthenticationService(
        session_factory=database_runtime.session_factory,
        password_manager=auth_runtime.password_manager,
        access_tokens=auth_runtime.access_tokens,
        refresh_ttl=auth_runtime.refresh_ttl,
    )


def get_auth_session_service(
    auth_runtime: Annotated[AuthRuntime, Depends(get_auth_runtime)],
    database_runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> AuthSessionService:
    return AuthSessionService(
        session_factory=database_runtime.session_factory,
        access_tokens=auth_runtime.access_tokens,
        refresh_ttl=auth_runtime.refresh_ttl,
    )


def get_user_invitation_service(
    database_runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> UserInvitationService:
    return UserInvitationService(
        session_factory=database_runtime.session_factory,
        activation_ttl=timedelta(hours=settings.auth_activation_token_ttl_hours),
        frontend_base_url=settings.frontend_base_url,
    )


def get_user_administration_service(
    database_runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> UserAdministrationService:
    return UserAdministrationService(session_factory=database_runtime.session_factory)


def require_access_principal(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ],
    auth_runtime: Annotated[AuthRuntime, Depends(get_auth_runtime)],
) -> AccessPrincipal:
    authorization_values = request.headers.getlist("Authorization")
    if len(authorization_values) != 1 or credentials is None:
        raise authentication_required_error()
    if credentials.scheme.lower() != "bearer":
        raise authentication_required_error()
    try:
        principal = auth_runtime.access_tokens.decode(credentials.credentials)
    except InvalidAccessTokenError as exc:
        raise authentication_required_error() from exc

    context = getattr(request.state, "request_context", None)
    if isinstance(context, RequestContext):
        enriched = context.derive(
            tenant=TenantContext(
                tenant_id=principal.tenant_id,
                slug=principal.tenant_slug,
            ),
            actor_id=principal.user_id,
            session_id=principal.session_family_id,
            authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
        )
        replace_request_context(request, enriched)
    return principal


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    principal: AccessPrincipal
    user: AuthenticatedUser


async def require_authenticated_session(
    principal: Annotated[AccessPrincipal, Depends(require_access_principal)],
    service: Annotated[AuthSessionService, Depends(get_auth_session_service)],
) -> AuthenticatedSession:
    return AuthenticatedSession(
        principal=principal,
        user=await service.current_user(principal),
    )


def get_authenticated_request_context(
    request: Request,
    authenticated_session: Annotated[
        AuthenticatedSession,
        Depends(require_authenticated_session),
    ],
) -> RequestContext:
    """Return context enriched only by the validated access/session dependency chain."""

    context = getattr(request.state, "request_context", None)
    principal = authenticated_session.principal
    if (
        not isinstance(context, RequestContext)
        or context.tenant is None
        or context.tenant.tenant_id != principal.tenant_id
        or context.actor_id != principal.user_id
        or context.session_id != principal.session_family_id
    ):
        raise authentication_required_error()
    return context


async def require_invitation_principal(
    principal: Annotated[AccessPrincipal, Depends(require_access_principal)],
    service: Annotated[AuthSessionService, Depends(get_auth_session_service)],
) -> AccessPrincipal:
    await service.current_user(principal)
    return principal


__all__ = [
    "AuthenticatedSession",
    "get_auth_session_service",
    "get_authentication_service",
    "get_authenticated_request_context",
    "get_user_administration_service",
    "get_user_invitation_service",
    "require_access_principal",
    "require_authenticated_session",
    "require_invitation_principal",
]
