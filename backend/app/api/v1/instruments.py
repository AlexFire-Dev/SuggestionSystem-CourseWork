from fastapi import APIRouter, Query

from app.services.dwh_service import list_instruments

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("")
def instruments(
    secid: str | None = Query(default=None, description="Ticker, for example SBER"),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[dict]:
    return list_instruments(secid=secid, limit=limit)
