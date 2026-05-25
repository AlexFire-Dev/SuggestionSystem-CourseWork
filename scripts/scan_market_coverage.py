import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path


DEFAULT_TICKERS = [
    "SBER", "GAZP", "LKOH", "GMKN", "NVTK", "ROSN", "TATN", "VTBR",
    "MOEX", "AFLT", "ALRS", "MAGN", "CHMF", "NLMK", "PLZL", "YNDX",
    "OZON", "FIVE", "PIKK", "MTSS", "MGNT", "SNGS", "SNGSP", "IRAO",
    "RUAL", "POLY", "PHOR", "RTKM", "TRNFP", "CBOM"
]


ENDPOINTS = [
    "/market/intraday",
    "/market/fact-5m",
    "/market/daily-summary",
]


def parse_dates(date_from: str, date_to: str) -> list[str]:
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)

    result = []
    current = start

    while current <= end:
        result.append(current.isoformat())
        current += timedelta(days=1)

    return result


def parse_tickers(values: list[str] | None) -> list[str]:
    if not values:
        return DEFAULT_TICKERS

    result = []

    for value in values:
        result.extend(value.replace(",", " ").split())

    return sorted({item.strip().upper() for item in result if item.strip()})


def fetch_json(base_url: str, path: str, params: dict, timeout: int = 20):
    url = f"{base_url.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SuggestionSystem-Coverage-Scanner/1.0"},
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode("utf-8")

    if not text.strip():
        return None

    return json.loads(text)


def count_rows(base_url: str, endpoint: str, secid: str, trade_date: str, limit: int):
    params = {
        "secid": secid,
        "trade_date": trade_date,
        "limit": limit,
    }

    try:
        data = fetch_json(base_url, endpoint, params)

        if isinstance(data, list):
            return {
                "ok": True,
                "rows": len(data),
                "error": "",
                "sample": data[0] if data else None,
            }

        return {
            "ok": False,
            "rows": 0,
            "error": f"non-list response: {type(data).__name__}",
            "sample": None,
        }

    except Exception as exc:
        return {
            "ok": False,
            "rows": 0,
            "error": str(exc),
            "sample": None,
        }


def main():
    parser = argparse.ArgumentParser(description="Scan MOEX backend market data coverage")
    parser.add_argument("--base-url", default="http://localhost:5173/api/v1")
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--tickers", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--sleep", type=float, default=0.05)
    parser.add_argument("--output", default="reports/market_coverage.csv")
    parser.add_argument("--json-output", default="reports/market_coverage.json")
    args = parser.parse_args()

    tickers = parse_tickers(args.tickers)
    dates = parse_dates(args.date_from, args.date_to)

    rows = []
    found = []

    total = len(tickers) * len(dates) * len(ENDPOINTS)
    current = 0

    print(f"BASE: {args.base_url}")
    print(f"TICKERS: {len(tickers)}")
    print(f"DATES: {dates[0]} .. {dates[-1]} ({len(dates)})")
    print(f"REQUESTS: {total}")

    for secid in tickers:
        for trade_date in dates:
            for endpoint in ENDPOINTS:
                current += 1

                result = count_rows(
                    base_url=args.base_url,
                    endpoint=endpoint,
                    secid=secid,
                    trade_date=trade_date,
                    limit=args.limit,
                )

                row = {
                    "secid": secid,
                    "trade_date": trade_date,
                    "endpoint": endpoint,
                    "ok": result["ok"],
                    "rows": result["rows"],
                    "error": result["error"],
                }

                rows.append(row)

                if result["rows"] > 0:
                    found.append(row)
                    print(
                        f"[{current}/{total}] FOUND "
                        f"{endpoint} {secid} {trade_date}: rows={result['rows']}"
                    )
                else:
                    print(
                        f"[{current}/{total}] empty "
                        f"{endpoint} {secid} {trade_date}"
                    )

                time.sleep(args.sleep)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["secid", "trade_date", "endpoint", "ok", "rows", "error"],
        )
        writer.writeheader()
        writer.writerows(rows)

    json_path = Path(args.json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=" * 80)
    print(f"SAVED CSV: {output_path}")
    print(f"SAVED JSON: {json_path}")
    print(f"FOUND NON-EMPTY SERIES: {len(found)}")

    if found:
        print()
        print("NON-EMPTY SERIES:")
        for item in found:
            print(
                f"{item['endpoint']:20s} "
                f"{item['secid']:8s} "
                f"{item['trade_date']} "
                f"rows={item['rows']}"
            )

        intraday = [
            item for item in found
            if item["endpoint"] == "/market/intraday"
        ]

        if intraday:
            tickers_found = sorted({item["secid"] for item in intraday})
            dates_found = sorted({item["trade_date"] for item in intraday})

            print()
            print("TRAIN COMMAND FOR INTRADAY DATA:")
            print(
                "python scripts/train_market_sentiment_nn.py "
                "--base-url https://okak.af.shvarev.com/api/v1 "
                f"--tickers {' '.join(tickers_found)} "
                f"--dates {' '.join(dates_found)} "
                "--limit 5000 "
                "--horizon 3 "
                "--hidden 8 "
                "--epochs 120 "
                "--lr 0.01 "
                "--min-samples 30 "
                "--output frontend/models/market_sentiment_nn.json"
            )
    else:
        print("No market data found for selected tickers/dates.")


if __name__ == "__main__":
    main()
