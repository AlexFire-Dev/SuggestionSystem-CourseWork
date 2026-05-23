from datetime import date

from fastapi import APIRouter, Query

from app.services.dwh_service import (
    list_news_company_candidates,
    list_news_criticality,
    list_news_events,
    list_ticker_dictionary,
)

router = APIRouter(prefix="/news", tags=["news"])


@router.get("/events")
def get_news_events(
    secid: str | None = Query(default=None, description="Optional ticker filter, for example SBER"),
    from_date: date | None = Query(default=None, description="From publication date"),
    to_date: date | None = Query(default=None, description="To publication date"),
    limit: int = Query(default=100, ge=1, le=5000),
):
    return list_news_events(secid=secid, from_date=from_date, to_date=to_date, limit=limit)


@router.get("/ticker-dictionary")
def get_ticker_dictionary(
    secid: str | None = Query(default=None, description="Ticker, for example SBER"),
    query: str | None = Query(default=None, description="Search substring in aliases"),
    limit: int = Query(default=100, ge=1, le=5000),
):
    return list_ticker_dictionary(secid=secid, query=query, limit=limit)


@router.get("/company-candidates")
def get_news_company_candidates(
    secid: str | None = Query(default=None, description="Ticker, for example SBER"),
    from_date: date | None = Query(default=None, description="From publication date"),
    to_date: date | None = Query(default=None, description="To publication date"),
    min_score: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=100, ge=1, le=5000),
):
    return list_news_company_candidates(
        secid=secid,
        from_date=from_date,
        to_date=to_date,
        min_score=min_score,
        limit=limit,
    )


@router.get("/criticality")
def get_news_criticality(
    secid: str | None = Query(default=None, description="Ticker, for example SBER"),
    from_date: date | None = Query(default=None, description="From publication date"),
    to_date: date | None = Query(default=None, description="To publication date"),
    min_criticality: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=100, ge=1, le=5000),
):
    return list_news_criticality(
        secid=secid,
        from_date=from_date,
        to_date=to_date,
        min_criticality=min_criticality,
        limit=limit,
    )
