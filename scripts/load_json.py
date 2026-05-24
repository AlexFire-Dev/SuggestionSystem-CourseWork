import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import clickhouse_connect
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def to_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if value == "":
        return default
    if isinstance(value, str) and value.lower() in {"none", "null", "nan"}:
        return default
    return float(value)


def to_int(value, default: int = 0) -> int:
    if value is None:
        return default
    if value == "":
        return default
    if isinstance(value, str) and value.lower() in {"none", "null", "nan"}:
        return default
    return int(value)


def to_str(value, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def get_client():
    load_dotenv(PROJECT_ROOT / ".env")
    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        secure=os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true",
    )


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value))


def parse_event_time(trade_date: str, trade_time: str) -> datetime:
    return datetime.fromisoformat(f"{trade_date} {trade_time}")


def get_block(payload: dict, block_name: str) -> tuple[list[str], list[list[Any]]]:
    block = payload.get(block_name)
    if not isinstance(block, dict) or "columns" not in block or "data" not in block:
        raise ValueError(f"Block {block_name!r} not found. Available: {list(payload.keys())}")
    return block["columns"], block["data"]


def rows_as_dicts(payload: dict, block_name: str) -> list[dict[str, Any]]:
    columns, rows = get_block(payload, block_name)
    return [dict(zip(columns, row)) for row in rows]


def save_raw_response(client, kind: str, ticker: str, request_date: str | None, payload: dict, endpoint: str | None):
    client.insert(
        "raw.algopack_responses",
        [(
            endpoint or kind,
            kind,
            ticker,
            parse_date(request_date) if request_date else None,
            json.dumps(payload, ensure_ascii=False),
        )],
        column_names=["endpoint", "response_kind", "ticker", "request_date", "response_json"],
    )


def save_dataversion(client, payload: dict, kind: str, ticker: str, endpoint: str | None):
    if "dataversion" not in payload:
        return

    rows = rows_as_dicts(payload, "dataversion")
    out = []
    for row in rows:
        out.append((
            endpoint or kind,
            kind,
            ticker,
            int(row["data_version"]),
            int(row["seqnum"]),
            parse_date(row["trade_date"]),
            parse_date(row["trade_session_date"]),
        ))

    if out:
        client.insert(
            "raw.dataversions",
            out,
            column_names=[
                "endpoint",
                "response_kind",
                "ticker",
                "data_version",
                "seqnum",
                "trade_date",
                "trade_session_date",
            ],
        )


def load_obstats(client, payload: dict):
    out = []
    for row in rows_as_dicts(payload, "data"):
        out.append((
            parse_date(row["tradedate"]),
            row["tradetime"],
            parse_event_time(row["tradedate"], row["tradetime"]),
            row["secid"],
            float(row["spread_bbo"]),
            float(row["spread_lv10"]),
            float(row["spread_1mio"]),
            int(row["levels_b"]),
            int(row["levels_s"]),
            int(row["vol_b"]),
            int(row["vol_s"]),
            int(row["val_b"]),
            int(row["val_s"]),
            float(row["imbalance_vol_bbo"]),
            float(row["imbalance_val_bbo"]),
            float(row["imbalance_vol"]),
            float(row["imbalance_val"]),
            float(row["vwap_b"]),
            float(row["vwap_s"]),
            float(row["vwap_b_1mio"]),
            float(row["vwap_s_1mio"]),
            parse_dt(row["SYSTIME"]),
        ))

    client.insert(
        "raw.obstats",
        out,
        column_names=[
            "trade_date", "trade_time", "event_time", "secid",
            "spread_bbo", "spread_lv10", "spread_1mio",
            "levels_b", "levels_s", "vol_b", "vol_s", "val_b", "val_s",
            "imbalance_vol_bbo", "imbalance_val_bbo", "imbalance_vol", "imbalance_val",
            "vwap_b", "vwap_s", "vwap_b_1mio", "vwap_s_1mio", "systime",
        ],
    )
    return len(out)


def load_orderstats(client, payload: dict):
    out = []
    for row in rows_as_dicts(payload, "data"):
        out.append((
            parse_date(row["tradedate"]),
            row["tradetime"],
            parse_event_time(row["tradedate"], row["tradetime"]),
            row["secid"],

            int(row["put_orders_b"]),
            int(row["put_orders_s"]),
            int(row["put_val_b"]),
            int(row["put_val_s"]),
            int(row["put_vol_b"]),
            int(row["put_vol_s"]),
            float(row["put_vwap_b"]),
            float(row["put_vwap_s"]),
            int(row["put_vol"]),
            int(row["put_val"]),
            int(row["put_orders"]),

            int(row["cancel_orders_b"]),
            int(row["cancel_orders_s"]),
            int(row["cancel_val_b"]),
            int(row["cancel_val_s"]),
            int(row["cancel_vol_b"]),
            int(row["cancel_vol_s"]),
            float(row["cancel_vwap_b"]),
            float(row["cancel_vwap_s"]),
            int(row["cancel_vol"]),
            int(row["cancel_val"]),
            int(row["cancel_orders"]),

            parse_dt(row["SYSTIME"]),
        ))

    client.insert(
        "raw.orderstats",
        out,
        column_names=[
            "trade_date", "trade_time", "event_time", "secid",
            "put_orders_b", "put_orders_s", "put_val_b", "put_val_s",
            "put_vol_b", "put_vol_s", "put_vwap_b", "put_vwap_s",
            "put_vol", "put_val", "put_orders",
            "cancel_orders_b", "cancel_orders_s", "cancel_val_b", "cancel_val_s",
            "cancel_vol_b", "cancel_vol_s", "cancel_vwap_b", "cancel_vwap_s",
            "cancel_vol", "cancel_val", "cancel_orders",
            "systime",
        ],
    )
    return len(out)


def load_tradestats(client, payload: dict):
    out = []
    for row in rows_as_dicts(payload, "data"):
        out.append((
            parse_date(row["tradedate"]),
            row["tradetime"],
            parse_event_time(row["tradedate"], row["tradetime"]),
            row["secid"],

            float(row["pr_open"]),
            float(row["pr_high"]),
            float(row["pr_low"]),
            float(row["pr_close"]),
            float(row["pr_std"]),

            int(row["vol"]),
            int(row["val"]),
            int(row["trades"]),
            float(row["pr_vwap"]),
            float(row["pr_change"]),

            int(row["trades_b"]),
            int(row["trades_s"]),
            int(row["val_b"]),
            int(row["val_s"]),
            int(row["vol_b"]),
            int(row["vol_s"]),

            float(row["disb"]),
            to_float(row.get("pr_vwap_b")),
            to_float(row.get("pr_vwap_s")),

            parse_dt(row["SYSTIME"]),

            int(row["sec_pr_open"]),
            int(row["sec_pr_high"]),
            int(row["sec_pr_low"]),
            int(row["sec_pr_close"]),
        ))

    client.insert(
        "raw.tradestats",
        out,
        column_names=[
            "trade_date", "trade_time", "event_time", "secid",
            "pr_open", "pr_high", "pr_low", "pr_close", "pr_std",
            "vol", "val", "trades", "pr_vwap", "pr_change",
            "trades_b", "trades_s", "val_b", "val_s", "vol_b", "vol_s",
            "disb", "pr_vwap_b", "pr_vwap_s", "systime",
            "sec_pr_open", "sec_pr_high", "sec_pr_low", "sec_pr_close",
        ],
    )
    return len(out)


def trade_date_from_payload(payload: dict) -> date:
    if "dataversion" in payload:
        rows = rows_as_dicts(payload, "dataversion")
        if rows:
            return parse_date(rows[0]["trade_date"])
    # Fallback: current local date
    return datetime.now().date()


def load_orderbook(client, payload: dict):
    trade_date = trade_date_from_payload(payload)
    out = []
    for row in rows_as_dicts(payload, "orderbook"):
        snapshot_ts = datetime.strptime(str(row["SEQNUM"]), "%Y%m%d%H%M%S")
        out.append((
            trade_date,
            row["UPDATETIME"],
            snapshot_ts,
            row["BOARDID"],
            row["SECID"],
            row["BUYSELL"],
            float(row["PRICE"]),
            int(row["QUANTITY"]),
            int(row["SEQNUM"]),
            row["UPDATETIME"],
            int(row["DECIMALS"]),
        ))

    client.insert(
        "raw.orderbook",
        out,
        column_names=[
            "trade_date", "snapshot_time", "snapshot_ts",
            "boardid", "secid", "side", "price", "quantity", "seqnum",
            "update_time", "decimals",
        ],
    )
    return len(out)


def to_float(value: Any) -> float | None:
    return None if value in (None, "") else float(value)


def to_int(value: Any) -> int | None:
    return None if value in (None, "") else int(value)


def load_securities(client, payload: dict):
    inst = []
    for row in rows_as_dicts(payload, "securities"):
        inst.append((
            row["SECID"],
            row["BOARDID"],
            row["SHORTNAME"],
            row["SECNAME"],
            row.get("LATNAME"),
            row.get("ISIN"),
            row.get("MARKETCODE"),
            row.get("INSTRID"),
            row.get("SECTYPE"),
            row.get("CURRENCYID"),
            row.get("STATUS"),
            to_float(row.get("LOTSIZE")),
            to_float(row.get("MINSTEP")),
            to_int(row.get("DECIMALS")),
            to_int(row.get("LISTLEVEL")),
            to_float(row.get("PREVPRICE")),
            to_float(row.get("PREVWAPRICE")),
            to_float(row.get("PREVLEGALCLOSEPRICE")),
            parse_date(row.get("PREVDATE")),
            parse_date(row.get("SETTLEDATE")),
            to_int(row.get("ISSUESIZE")),
        ))

    if inst:
        client.insert(
            "raw.instruments",
            inst,
            column_names=[
                "secid", "boardid", "shortname", "secname", "latname", "isin",
                "marketcode", "instrid", "sectype", "currencyid", "status",
                "lotsize", "minstep", "decimals", "listlevel",
                "prevprice", "prevwaprice", "prevlegalcloseprice",
                "prevdate", "settledate", "issuesize",
            ],
        )

    md = []
    if "marketdata" in payload:
        for row in rows_as_dicts(payload, "marketdata"):
            md.append((
                row["SECID"],
                row["BOARDID"],
                to_float(row.get("BID")),
                to_float(row.get("BIDDEPTH")),
                to_float(row.get("OFFER")),
                to_float(row.get("OFFERDEPTH")),
                to_float(row.get("SPREAD")),
                to_float(row.get("OPEN")),
                to_float(row.get("LOW")),
                to_float(row.get("HIGH")),
                to_float(row.get("LAST")),
                to_float(row.get("WAPRICE")),
                to_int(row.get("NUMTRADES")),
                to_float(row.get("VOLTODAY")),
                to_float(row.get("VALTODAY")),
                row.get("TRADINGSTATUS"),
                row.get("UPDATETIME"),
                to_float(row.get("LASTBID")),
                to_float(row.get("LASTOFFER")),
                to_int(row.get("NUMBIDS")),
                to_int(row.get("NUMOFFERS")),
                row.get("TIME"),
                to_int(row.get("SEQNUM")),
                parse_dt(row.get("SYSTIME")),
            ))

        if md:
            client.insert(
                "raw.marketdata_snapshots",
                md,
                column_names=[
                    "secid", "boardid", "bid", "biddepth", "offer", "offerdepth", "spread",
                    "open", "low", "high", "last", "waprice", "numtrades", "voltoday", "valtoday",
                    "tradingstatus", "updatetime", "lastbid", "lastoffer", "numbids", "numoffers",
                    "time", "seqnum", "systime",
                ],
            )

    return len(inst) + len(md)


LOADERS = {
    "obstats": load_obstats,
    "orderstats": load_orderstats,
    "tradestats": load_tradestats,
    "orderbook": load_orderbook,
    "securities": load_securities,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True, choices=sorted(LOADERS.keys()))
    parser.add_argument("--file", required=True)
    parser.add_argument("--ticker", default="SBER")
    parser.add_argument("--date", default=None)
    parser.add_argument("--endpoint", default=None)
    args = parser.parse_args()

    client = get_client()
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))

    save_raw_response(client, args.kind, args.ticker, args.date, payload, args.endpoint)
    save_dataversion(client, payload, args.kind, args.ticker, args.endpoint)

    started = datetime.now()
    status = "success"
    message = None
    rows_loaded = 0

    try:
        rows_loaded = LOADERS[args.kind](client, payload)
    except Exception as exc:
        status = "failed"
        message = str(exc)
        raise
    finally:
        client.insert(
            "meta.pipeline_runs",
            [(
                f"load_{args.kind}",
                "algopack",
                status,
                started,
                datetime.now(),
                rows_loaded,
                message,
            )],
            column_names=[
                "pipeline_name",
                "source",
                "status",
                "started_at",
                "finished_at",
                "rows_loaded",
                "message",
            ],
        )

    print(f"Loaded {rows_loaded} rows for kind={args.kind}")


if __name__ == "__main__":
    main()
