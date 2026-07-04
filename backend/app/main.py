from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.landing import router as landing_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.environment != "prod" else None,
        redoc_url="/redoc" if settings.environment != "prod" else None,
    )
    app.include_router(landing_router)
    app.include_router(health_router)
    return app


app = create_app()
