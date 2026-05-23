from datetime import date

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.services.dwh_service import get_daily_summary, get_intraday_liquidity_state, get_market_fact_5m
from app.utils.csv_export import rows_to_csv

router = APIRouter(prefix="/exports", tags=["exports"])


def _csv_response(rows: list[dict], filename: str) -> Response:
    csv_payload = rows_to_csv(rows)
    return Response(
        content=csv_payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/intraday.csv")
def export_intraday_csv(
    secid: str = Query(..., description="Ticker, for example SBER"),
    trade_date: date | None = Query(default=None, description="Trading date in YYYY-MM-DD format"),
    state: str | None = Query(default=None, description="Filter by market_state"),
    limit: int = Query(default=5000, ge=1, le=5000),
) -> Response:
    rows = get_intraday_liquidity_state(secid=secid, trade_date=trade_date, state=state, limit=limit)
    date_part = trade_date.isoformat() if trade_date else "all"
    return _csv_response(rows, f"intraday_liquidity_state_{secid.upper()}_{date_part}.csv")


@router.get("/fact-5m.csv")
def export_fact_5m_csv(
    secid: str = Query(..., description="Ticker, for example SBER"),
    trade_date: date | None = Query(default=None, description="Trading date in YYYY-MM-DD format"),
    limit: int = Query(default=5000, ge=1, le=5000),
) -> Response:
    rows = get_market_fact_5m(secid=secid, trade_date=trade_date, limit=limit)
    date_part = trade_date.isoformat() if trade_date else "all"
    return _csv_response(rows, f"market_fact_5m_{secid.upper()}_{date_part}.csv")


@router.get("/daily-summary.csv")
def export_daily_summary_csv(
    secid: str | None = Query(default=None, description="Ticker, for example SBER"),
    trade_date: date | None = Query(default=None, description="Trading date in YYYY-MM-DD format"),
    limit: int = Query(default=5000, ge=1, le=5000),
) -> Response:
    rows = get_daily_summary(secid=secid, trade_date=trade_date, limit=limit)
    ticker_part = secid.upper() if secid else "all"
    date_part = trade_date.isoformat() if trade_date else "all"
    return _csv_response(rows, f"daily_summary_{ticker_part}_{date_part}.csv")
