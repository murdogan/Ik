from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.announcements import router as announcements_router
from app.api.audit import platform_router as platform_audit_router
from app.api.audit import tenant_router as tenant_audit_router
from app.api.auth import me_router
from app.api.auth import router as auth_router
from app.api.authorization import router as authorization_router
from app.api.dashboard import router as dashboard_router
from app.api.departments import router as departments_router
from app.api.document_requests import router as document_requests_router
from app.api.employee_account_links import own_router as employee_own_profile_router
from app.api.employee_account_links import router as employee_account_links_router
from app.api.employee_assignments import assignments_router, teams_router
from app.api.employee_documents import (
    document_types_router,
)
from app.api.employee_documents import (
    employee_router as employee_documents_router,
)
from app.api.employee_documents import (
    own_router as own_employee_documents_router,
)
from app.api.employee_imports import router as employee_imports_router
from app.api.employee_profile_change_requests import (
    own_router as employee_own_profile_change_requests_router,
)
from app.api.employee_profile_change_requests import (
    router as employee_profile_change_requests_router,
)
from app.api.employee_profiles import router as employee_profiles_router
from app.api.employees import router as employees_router
from app.api.errors import (
    application_error_handler,
    request_validation_error_handler,
    unexpected_error_handler,
)
from app.api.export_jobs import router as export_jobs_router
from app.api.health import router as health_router
from app.api.landing import router as landing_router
from app.api.leave import (
    approval_router as leave_approval_router,
)
from app.api.leave import (
    balance_router as leave_balance_router,
)
from app.api.leave import (
    configuration_router as leave_configuration_router,
)
from app.api.leave import (
    request_router as leave_request_router,
)
from app.api.notifications import router as notifications_router
from app.api.openapi import OPENAPI_TAGS
from app.api.org_chart import router as org_chart_router
from app.api.organization import branches_router, legal_entities_router
from app.api.platform_auth import me_router as platform_me_router
from app.api.platform_auth import router as platform_auth_router
from app.api.platform_tenants import router as platform_tenants_router
from app.api.positions import router as positions_router
from app.api.reports import router as reports_router
from app.api.requests import router as requests_router
from app.api.self_service import router as self_service_router
from app.api.tenant import router as tenant_router
from app.api.user_invitations import router as user_invitations_router
from app.api.users import router as users_router
from app.core.auth_runtime import AUTH_RUNTIME_STATE_KEY, create_auth_runtime
from app.core.config import APP_SETTINGS_STATE_KEY, Settings, get_settings
from app.db.session import (
    DATABASE_RUNTIME_STATE_KEY,
    create_database_runtime,
)
from app.modules.documents import (
    DOCUMENT_RUNTIME_STATE_KEY,
    create_document_runtime,
)
from app.platform.errors import ApiError, ApplicationError, api_error_handler
from app.platform.http_limits import RequestBodyLimitMiddleware
from app.platform.observability.correlation import CorrelationMiddleware
from app.schemas.employee_import import EMPLOYEE_IMPORT_MAX_REQUEST_BYTES


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = getattr(application.state, APP_SETTINGS_STATE_KEY, None)
    if settings is None:
        settings = get_settings()
    runtime = create_database_runtime(settings)
    document_runtime = create_document_runtime(settings)
    setattr(application.state, DATABASE_RUNTIME_STATE_KEY, runtime)
    setattr(application.state, DOCUMENT_RUNTIME_STATE_KEY, document_runtime)
    try:
        await document_runtime.initialize()
        yield
    finally:
        try:
            await document_runtime.close()
        finally:
            try:
                await runtime.dispose()
            finally:
                delattr(application.state, DOCUMENT_RUNTIME_STATE_KEY)
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
    app.add_middleware(
        RequestBodyLimitMiddleware,
        method="POST",
        path="/api/v1/employees/imports",
        maximum_bytes=EMPLOYEE_IMPORT_MAX_REQUEST_BYTES,
        error_code="reporting_validation_error",
        error_message="Report or import request validation failed",
    )
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
    app.include_router(positions_router)
    app.include_router(assignments_router)
    app.include_router(teams_router)
    app.include_router(org_chart_router)
    app.include_router(dashboard_router)
    app.include_router(employee_account_links_router)
    app.include_router(employee_own_profile_router)
    app.include_router(employee_profile_change_requests_router)
    app.include_router(employee_own_profile_change_requests_router)
    app.include_router(employee_profiles_router)
    app.include_router(document_types_router)
    app.include_router(employee_documents_router)
    app.include_router(own_employee_documents_router)
    app.include_router(employee_imports_router)
    app.include_router(employees_router)
    app.include_router(reports_router)
    app.include_router(export_jobs_router)
    app.include_router(leave_configuration_router)
    app.include_router(leave_balance_router)
    app.include_router(leave_request_router)
    app.include_router(leave_approval_router)
    app.include_router(requests_router)
    app.include_router(document_requests_router)
    app.include_router(self_service_router)
    app.include_router(announcements_router)
    app.include_router(notifications_router)
    app.include_router(landing_router)
    app.include_router(health_router)
    return app


app = create_app()
