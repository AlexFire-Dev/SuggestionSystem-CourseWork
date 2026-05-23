from datetime import date

from fastapi import APIRouter, Query

from app.services.dwh_service import (
    get_available_market_states,
    get_daily_summary,
    get_intraday_liquidity_state,
    get_market_fact_5m,
)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/intraday")
def intraday_liquidity_state(
    secid: str = Query(..., description="Ticker, for example SBER"),
    trade_date: date | None = Query(default=None, description="Trading date in YYYY-MM-DD format"),
    state: str | None = Query(default=None, description="Filter by market_state"),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[dict]:
    return get_intraday_liquidity_state(secid=secid, trade_date=trade_date, state=state, limit=limit)


@router.get("/fact-5m")
def market_fact_5m(
    secid: str = Query(..., description="Ticker, for example SBER"),
    trade_date: date | None = Query(default=None, description="Trading date in YYYY-MM-DD format"),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[dict]:
    return get_market_fact_5m(secid=secid, trade_date=trade_date, limit=limit)


@router.get("/daily-summary")
def daily_summary(
    secid: str | None = Query(default=None, description="Ticker, for example SBER"),
    trade_date: date | None = Query(default=None, description="Trading date in YYYY-MM-DD format"),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[dict]:
    return get_daily_summary(secid=secid, trade_date=trade_date, limit=limit)


@router.get("/states")
def market_states() -> list[dict]:
    return get_available_market_states()
