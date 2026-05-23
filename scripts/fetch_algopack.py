import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://apim.moex.com"


def build_endpoint(kind: str, ticker: str | None) -> str:
    ticker = (ticker or "").upper()

    if kind in {"obstats", "orderstats", "tradestats"}:
        if not ticker:
            raise ValueError(f"--ticker is required for kind={kind}")
        return f"/iss/datashop/algopack/eq/{kind}/{ticker}.json"

    if kind == "orderbook":
        if not ticker:
            raise ValueError("--ticker is required for orderbook")
        return f"/iss/engines/stock/markets/shares/boards/TQBR/securities/{ticker}/orderbook.json"

    if kind == "securities":
        return "/iss/engines/stock/markets/shares/boards/TQBR/securities.json"

    raise ValueError(f"Unsupported kind: {kind}")


def fetch(kind: str, ticker: str | None, trade_date: str | None, output: Path) -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    base_url = os.getenv("MOEX_ALGOPACK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    token = os.getenv("MOEX_ALGOPACK_TOKEN")

    if not token:
        raise RuntimeError("MOEX_ALGOPACK_TOKEN is not set")

    endpoint = build_endpoint(kind, ticker)
    params = {"iss.meta": "off"}

    # Historical AlgoPack endpoints use date. The live orderbook endpoint does not need it.
    if trade_date and kind in {"obstats", "orderstats", "tradestats"}:
        params["date"] = trade_date

    url = f"{base_url}{endpoint}"
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.get(url, headers=headers, params=params, timeout=60)
    print(f"GET {response.url}")
    print(f"Status: {response.status_code}")
    response.raise_for_status()

    payload = response.json()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Saved {kind} response to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch MOEX AlgoPack/ISS JSON response to a local file")
    parser.add_argument("--kind", required=True, choices=["obstats", "orderstats", "tradestats", "orderbook", "securities"])
    parser.add_argument("--ticker", default="SBER")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD. Used for historical AlgoPack endpoints")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    fetch(args.kind, args.ticker, args.date, Path(args.output))


if __name__ == "__main__":
    main()
