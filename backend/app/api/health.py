from fastapi import APIRouter, Request

from app.api.openapi import SYSTEM_TAG
from app.core.config import APP_SETTINGS_STATE_KEY, get_settings

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
