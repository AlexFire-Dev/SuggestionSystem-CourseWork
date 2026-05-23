from datetime import date
from typing import Any

from clickhouse_connect.driver.exceptions import DatabaseError, OperationalError
from fastapi import HTTPException

from app.core.config import get_settings
from app.db.clickhouse import clickhouse_client, rows_as_dicts
from app.utils.serialization import jsonable_rows


def _bounded_limit(limit: int | None) -> int:
    settings = get_settings()
    if limit is None:
        return settings.default_limit
    if limit < 1:
        return settings.default_limit
    return min(limit, settings.max_limit)


def _query(sql: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    try:
        with clickhouse_client() as client:
            result = client.query(sql, parameters=parameters or {})
            rows = rows_as_dicts(list(result.column_names), list(result.result_rows))
            return jsonable_rows(rows)
    except (DatabaseError, OperationalError) as exc:
        raise HTTPException(status_code=503, detail=f"ClickHouse query failed: {exc}") from exc


def ping() -> dict[str, Any]:
    try:
        with clickhouse_client() as client:
            value = client.query("SELECT 1 AS ok").first_row[0]
            return {"status": "ok", "clickhouse": bool(value)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"ClickHouse is unavailable: {exc}") from exc


def list_migrations() -> list[dict[str, Any]]:
    return _query(
        """
        SELECT version, applied_at
        FROM meta.schema_migrations
        ORDER BY version
        """
    )


def list_instruments(secid: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    limit_value = _bounded_limit(limit)
    if secid:
        return _query(
            """
            SELECT
                secid, boardid, shortname, secname, latname, isin,
                marketcode, instrid, sectype, currencyid, status,
                lotsize, minstep, decimals, listlevel, issuesize, latest_loaded_at
            FROM stg.v_instruments_latest
            WHERE secid = {secid:String}
            ORDER BY secid, boardid
            LIMIT {limit:UInt32}
            """,
            {"secid": secid.upper(), "limit": limit_value},
        )

    return _query(
        """
        SELECT
            secid, boardid, shortname, secname, latname, isin,
            marketcode, instrid, sectype, currencyid, status,
            lotsize, minstep, decimals, listlevel, issuesize, latest_loaded_at
        FROM stg.v_instruments_latest
        ORDER BY secid, boardid
        LIMIT {limit:UInt32}
        """,
        {"limit": limit_value},
    )


def get_intraday_liquidity_state(
    secid: str,
    trade_date: date | None = None,
    state: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    limit_value = _bounded_limit(limit)
    where = ["secid = {secid:String}"]
    params: dict[str, Any] = {"secid": secid.upper(), "limit": limit_value}

    if trade_date is not None:
        where.append("trade_date = {trade_date:Date}")
        params["trade_date"] = trade_date.isoformat()
    if state is not None:
        where.append("market_state = {state:String}")
        params["state"] = state

    sql = f"""
        SELECT
            trade_date,
            trade_time,
            event_time,
            secid,
            shortname,
            spread_bbo,
            spread_lv10,
            spread_1mio,
            book_vol_b,
            book_vol_s,
            book_val_b,
            book_val_s,
            book_vol_imbalance,
            book_val_imbalance,
            imbalance_vol_bbo,
            imbalance_val_bbo,
            relative_spread_1mio,
            put_orders,
            put_vol,
            put_vol_imbalance,
            cancel_orders,
            cancel_vol,
            cancel_vol_imbalance,
            pr_open,
            pr_high,
            pr_low,
            pr_close,
            pr_change,
            trade_vol,
            trade_val,
            trades,
            trade_direction_imbalance,
            market_state
        FROM mart.v_intraday_liquidity_state
        WHERE {' AND '.join(where)}
        ORDER BY event_time
        LIMIT {{limit:UInt32}}
    """
    return _query(sql, params)


def get_market_fact_5m(secid: str, trade_date: date | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    limit_value = _bounded_limit(limit)
    where = ["secid = {secid:String}"]
    params: dict[str, Any] = {"secid": secid.upper(), "limit": limit_value}
    if trade_date is not None:
        where.append("trade_date = {trade_date:Date}")
        params["trade_date"] = trade_date.isoformat()

    sql = f"""
        SELECT *
        FROM dwh.fct_market_5m
        WHERE {' AND '.join(where)}
        ORDER BY event_time
        LIMIT {{limit:UInt32}}
    """
    return _query(sql, params)


def get_daily_summary(secid: str | None = None, trade_date: date | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    limit_value = _bounded_limit(limit)
    where: list[str] = []
    params: dict[str, Any] = {"limit": limit_value}

    if secid:
        where.append("secid = {secid:String}")
        params["secid"] = secid.upper()
    if trade_date is not None:
        where.append("trade_date = {trade_date:Date}")
        params["trade_date"] = trade_date.isoformat()

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    return _query(
        f"""
        SELECT *
        FROM mart.v_daily_instrument_summary
        {where_sql}
        ORDER BY trade_date DESC, secid
        LIMIT {{limit:UInt32}}
        """,
        params,
    )


def get_orderbook_top(secid: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    limit_value = _bounded_limit(limit)
    if secid:
        return _query(
            """
            SELECT *
            FROM stg.v_orderbook_top
            WHERE secid = {secid:String}
            ORDER BY snapshot_time DESC, secid
            LIMIT {limit:UInt32}
            """,
            {"secid": secid.upper(), "limit": limit_value},
        )

    return _query(
        """
        SELECT *
        FROM stg.v_orderbook_top
        ORDER BY snapshot_time DESC, secid
        LIMIT {limit:UInt32}
        """,
        {"limit": limit_value},
    )


def get_available_market_states() -> list[dict[str, Any]]:
    return _query(
        """
        SELECT market_state, count() AS intervals
        FROM mart.v_intraday_liquidity_state
        GROUP BY market_state
        ORDER BY intervals DESC
        """
    )
