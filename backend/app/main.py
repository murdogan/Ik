from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.audit import platform_router as platform_audit_router
from app.api.audit import tenant_router as tenant_audit_router
from app.api.auth import me_router
from app.api.auth import router as auth_router
from app.api.authorization import router as authorization_router
from app.api.dashboard import router as dashboard_router
from app.api.departments import router as departments_router
from app.api.employees import router as employees_router
from app.api.errors import (
    application_error_handler,
    request_validation_error_handler,
    unexpected_error_handler,
)
from app.api.health import router as health_router
from app.api.landing import router as landing_router
from app.api.leave_balances import router as leave_balances_router
from app.api.leave_requests import router as leave_requests_router
from app.api.openapi import OPENAPI_TAGS
from app.api.organization import branches_router, legal_entities_router
from app.api.platform_auth import me_router as platform_me_router
from app.api.platform_auth import router as platform_auth_router
from app.api.platform_tenants import router as platform_tenants_router
from app.api.tenant import router as tenant_router
from app.api.user_invitations import router as user_invitations_router
from app.api.users import router as users_router
from app.core.auth_runtime import AUTH_RUNTIME_STATE_KEY, create_auth_runtime
from app.core.config import APP_SETTINGS_STATE_KEY, Settings, get_settings
from app.db.session import (
    DATABASE_RUNTIME_STATE_KEY,
    create_database_runtime,
)
from app.platform.errors import ApiError, ApplicationError, api_error_handler
from app.platform.observability.correlation import CorrelationMiddleware


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = getattr(application.state, APP_SETTINGS_STATE_KEY, None)
    if settings is None:
        settings = get_settings()
    runtime = create_database_runtime(settings)
    setattr(application.state, DATABASE_RUNTIME_STATE_KEY, runtime)
    try:
        yield
    finally:
        try:
            await runtime.dispose()
        finally:
            delattr(application.state, DATABASE_RUNTIME_STATE_KEY)


def create_app(*, settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "prod" else None,
        redoc_url="/redoc" if settings.environment != "prod" else None,
        openapi_tags=OPENAPI_TAGS,
    )
    setattr(app.state, APP_SETTINGS_STATE_KEY, settings)
    setattr(app.state, AUTH_RUNTIME_STATE_KEY, create_auth_runtime(settings))
    app.add_middleware(CorrelationMiddleware)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(ApplicationError, application_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
    app.include_router(platform_auth_router)
    app.include_router(platform_me_router)
    app.include_router(platform_tenants_router)
    app.include_router(platform_audit_router)
    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(authorization_router)
    app.include_router(user_invitations_router)
    app.include_router(users_router)
    app.include_router(tenant_audit_router)
    app.include_router(tenant_router)
    app.include_router(legal_entities_router)
    app.include_router(branches_router)
    app.include_router(departments_router)
    app.include_router(dashboard_router)
    app.include_router(employees_router)
    app.include_router(leave_balances_router)
    app.include_router(leave_requests_router)
    app.include_router(landing_router)
    app.include_router(health_router)
    return app


app = create_app()
