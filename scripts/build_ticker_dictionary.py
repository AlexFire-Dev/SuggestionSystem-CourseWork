import os
import re
from pathlib import Path
from typing import Any

import clickhouse_connect
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

LEGAL_WORDS = {
    "пао", "оао", "зао", "ао", "нко", "банк", "ак", "гк", "мкпао",
    "pao", "ojsc", "pjsc", "jsc", "ao", "ipjsc", "group", "company",
    "ordinary", "ord", "shs", "ao", "pref", "preferred", "gdr", "adr",
}


def get_client():
    load_dotenv(PROJECT_ROOT / ".env")
    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        secure=os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true",
    )


def normalize_alias(value: Any) -> str:
    text = str(value or "").casefold().replace("ё", "е")
    text = re.sub(r"[\"'«»()\[\]{}]", " ", text)
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_company_name(value: Any) -> str:
    normalized = normalize_alias(value)
    tokens = [token for token in normalized.split() if token not in LEGAL_WORDS]
    return " ".join(tokens).strip()


def add_alias(aliases: set[tuple[str, str, str, float]], value: Any, alias_type: str, weight: float):
    alias = str(value or "").strip()
    normalized = normalize_alias(alias)
    if len(normalized) >= 2:
        aliases.add((alias, normalized, alias_type, weight))

    cleaned = clean_company_name(alias)
    if cleaned and cleaned != normalized and len(cleaned) >= 3:
        aliases.add((cleaned, cleaned, f"{alias_type}_clean", max(weight - 0.05, 0.5)))


def load_instruments(client) -> list[dict[str, Any]]:
    result = client.query("""
        SELECT
            secid, boardid, shortname, secname, latname, isin
        FROM stg.v_instruments_latest
        WHERE status IN ('A', 'N') OR status = ''
    """)
    columns = list(result.column_names)
    return [dict(zip(columns, row, strict=False)) for row in result.result_rows]


def main():
    client = get_client()
    instruments = load_instruments(client)

    rows = []
    for item in instruments:
        secid = str(item.get("secid") or "").strip().upper()
        boardid = str(item.get("boardid") or "").strip().upper()
        if not secid:
            continue

        aliases: set[tuple[str, str, str, float]] = set()
        add_alias(aliases, secid, "secid", 1.0)
        add_alias(aliases, item.get("shortname"), "shortname", 0.90)
        add_alias(aliases, item.get("secname"), "secname", 0.95)
        add_alias(aliases, item.get("latname"), "latname", 0.85)
        add_alias(aliases, item.get("isin"), "isin", 0.70)

        for alias, alias_norm, alias_type, weight in aliases:
            # Avoid extremely generic aliases that create false positives.
            if alias_type != "secid" and len(alias_norm) < 3:
                continue
            if alias_norm in {"ао", "ап", "пao", "пао", "банк", "group", "company"}:
                continue
            rows.append((secid, boardid, alias, alias_norm, alias_type, "moex_instruments", float(weight)))

    client.command("TRUNCATE TABLE dwh.news_ticker_dictionary")
    if rows:
        client.insert(
            "dwh.news_ticker_dictionary",
            rows,
            column_names=["secid", "boardid", "alias", "alias_normalized", "alias_type", "source", "weight"],
        )
    print(f"Built ticker dictionary: {len(rows)} aliases from {len(instruments)} instruments")


if __name__ == "__main__":
    main()
