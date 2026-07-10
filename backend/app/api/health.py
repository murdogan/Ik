from fastapi import APIRouter

from app.api.openapi import SYSTEM_TAG
from app.core.config import get_settings

router = APIRouter(tags=[SYSTEM_TAG])


@router.get(
    "/health",
    summary="Get API health status",
    description=(
        "Returns public Wealthy Falcon HR service status metadata, including service name, "
        "version, and environment. This endpoint does not require tenant headers."
    ),
    response_description="API health metadata.",
)
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }
