import asyncio
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from app.api.openapi import SYSTEM_TAG, with_correlation_response_headers
from app.core.config import APP_SETTINGS_STATE_KEY, Settings, get_settings
from app.db.session import DATABASE_RUNTIME_STATE_KEY, DatabaseRuntime
from app.schemas.health import (
    HealthLiveRead,
    HealthReadinessComponentsRead,
    HealthReadinessRead,
)

router = APIRouter(tags=[SYSTEM_TAG])


@router.get(
    "/health",
    summary="Check API health",
    description=(
        "Checks public Wealthy Falcon HR service availability and returns service name, version, "
        "and environment metadata. This operational endpoint does not require tenant headers."
    ),
    response_description="API health metadata.",
)
def health(request: Request) -> dict[str, str]:
    settings = getattr(request.app.state, APP_SETTINGS_STATE_KEY, None)
    if settings is None:
        settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }


@router.get(
    "/health/live",
    response_model=HealthLiveRead,
    summary="Check API process liveness",
    description=(
        "Returns constant-time process and immutable release metadata without checking external "
        "dependencies. This public endpoint does not require tenant context."
    ),
    response_description="API process liveness and release metadata.",
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
def health_live(request: Request, response: Response) -> HealthLiveRead:
    settings = _health_settings(request)
    _set_no_cache_headers(response)
    return HealthLiveRead(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        commit_sha=settings.release_commit_sha,
        build_timestamp=settings.release_build_timestamp,
    )


@router.get(
    "/health/ready",
    response_model=HealthReadinessRead,
    summary="Check API dependency readiness",
    description=(
        "Checks bounded database connectivity without tenant context and returns only generic "
        "component and immutable release metadata."
    ),
    response_description="API dependency readiness and release metadata.",
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {
                "model": HealthReadinessRead,
                "description": "The API database dependency is ready.",
            },
            status.HTTP_503_SERVICE_UNAVAILABLE: {
                "model": HealthReadinessRead,
                "description": "The API database dependency is unavailable.",
            },
        }
    ),
)
async def health_ready(request: Request, response: Response) -> HealthReadinessRead:
    settings = _health_settings(request)
    _set_no_cache_headers(response)
    readiness_status: Literal["ready", "unavailable"] = "unavailable"
    runtime = getattr(request.app.state, DATABASE_RUNTIME_STATE_KEY, None)
    if isinstance(runtime, DatabaseRuntime):
        try:
            async with asyncio.timeout(settings.health_readiness_timeout_seconds):
                async with runtime.engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
        except Exception:
            pass
        else:
            readiness_status = "ready"

    response.status_code = (
        status.HTTP_200_OK if readiness_status == "ready" else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return HealthReadinessRead(
        status=readiness_status,
        service=settings.app_name,
        version=settings.app_version,
        commit_sha=settings.release_commit_sha,
        build_timestamp=settings.release_build_timestamp,
        components=HealthReadinessComponentsRead(database=readiness_status),
    )


def _health_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, APP_SETTINGS_STATE_KEY, None)
    if isinstance(settings, Settings):
        return settings
    return get_settings()


def _set_no_cache_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
