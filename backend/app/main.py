from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.dashboard import router as dashboard_router
from app.api.employees import router as employees_router
from app.api.errors import ApiError, api_error_handler, request_validation_error_handler
from app.api.health import router as health_router
from app.api.landing import router as landing_router
from app.api.leave_balances import router as leave_balances_router
from app.api.leave_requests import router as leave_requests_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.environment != "prod" else None,
        redoc_url="/redoc" if settings.environment != "prod" else None,
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.include_router(dashboard_router)
    app.include_router(employees_router)
    app.include_router(leave_balances_router)
    app.include_router(leave_requests_router)
    app.include_router(landing_router)
    app.include_router(health_router)
    return app


app = create_app()
