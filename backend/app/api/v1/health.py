from fastapi import APIRouter

from app.core.config import get_settings
from app.services.dwh_service import ping

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health_check() -> dict:
    settings = get_settings()
    status = ping()
    return {
        "status": status["status"],
        "app": settings.app_name,
        "version": settings.app_version,
        "clickhouse": status["clickhouse"],
    }
