from fastapi import APIRouter, Query

from app.services.dwh_service import get_orderbook_top

router = APIRouter(prefix="/orderbook", tags=["orderbook"])


@router.get("/top")
def orderbook_top(
    secid: str | None = Query(default=None, description="Ticker, for example SBER"),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[dict]:
    return get_orderbook_top(secid=secid, limit=limit)
