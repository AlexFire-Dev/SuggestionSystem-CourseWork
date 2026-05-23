import argparse
import os
import re
from pathlib import Path
from typing import Any

import clickhouse_connect
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def get_client():
    load_dotenv(PROJECT_ROOT / ".env")
    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        secure=os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true",
    )


def normalize_text(value: Any) -> str:
    text = str(value or "").casefold().replace("ё", "е")
    text = re.sub(r"[\"'«»()\[\]{}]", " ", text)
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_normalized(text: str, alias: str) -> bool:
    if not alias:
        return False
    return re.search(rf"(^|\s){re.escape(alias)}($|\s)", text) is not None


def contains_ticker(original_text: str, ticker: str) -> bool:
    if not ticker:
        return False
    return re.search(rf"(?<![A-Z0-9]){re.escape(ticker.upper())}(?![A-Z0-9])", original_text.upper()) is not None


def fetch_news(client, from_date: str | None, to_date: str | None, limit: int) -> list[dict[str, Any]]:
    where = []
    params: dict[str, Any] = {"limit": limit}
    if from_date:
        where.append("published_date >= {from_date:Date}")
        params["from_date"] = from_date
    if to_date:
        where.append("published_date <= {to_date:Date}")
        params["to_date"] = to_date
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    result = client.query(
        f"""
        SELECT news_id, title, body, published_date, published_time, published_at, tags
        FROM stg.v_news_events
        {where_sql}
        ORDER BY published_date, news_id
        LIMIT {{limit:UInt32}}
        """,
        parameters=params,
    )
    columns = list(result.column_names)
    return [dict(zip(columns, row, strict=False)) for row in result.result_rows]


def fetch_dictionary(client) -> list[dict[str, Any]]:
    result = client.query("""
        SELECT secid, boardid, alias, alias_normalized, alias_type, weight
        FROM dwh.news_ticker_dictionary
        WHERE alias_normalized != ''
        ORDER BY weight DESC, length(alias_normalized) DESC
    """)
    columns = list(result.column_names)
    return [dict(zip(columns, row, strict=False)) for row in result.result_rows]


def score_match(alias_type: str, base_weight: float, field: str) -> float:
    field_weight = {"title": 1.00, "tags": 0.95, "body": 0.75}.get(field, 0.70)
    method_bonus = 0.05 if alias_type == "secid" else 0.0
    return min(1.0, float(base_weight) * field_weight + method_bonus)


def best_matches_for_news(news: dict[str, Any], dictionary: list[dict[str, Any]], min_score: float) -> list[tuple]:
    title = str(news.get("title") or "")
    body = str(news.get("body") or "")
    tags = news.get("tags") or []
    tags_text = " ".join(str(tag) for tag in tags)

    fields = {
        "title": title,
        "tags": tags_text,
        "body": body,
    }
    normalized_fields = {field: normalize_text(value) for field, value in fields.items()}

    best_by_secid: dict[str, tuple] = {}
    for item in dictionary:
        secid = item["secid"]
        boardid = item["boardid"]
        alias = item["alias"]
        alias_norm = item["alias_normalized"]
        alias_type = item["alias_type"]
        weight = float(item["weight"])

        for field_name, field_value in fields.items():
            if alias_type == "secid":
                matched = contains_ticker(field_value, alias)
                method = "secid_exact"
            else:
                matched = contains_normalized(normalized_fields[field_name], alias_norm)
                method = "alias_dictionary"

            if not matched:
                continue

            score = score_match(alias_type, weight, field_name)
            if score < min_score:
                continue

            row = (
                news["news_id"],
                secid,
                boardid,
                method,
                field_name,
                alias,
                score,
            )
            current = best_by_secid.get(secid)
            if current is None or score > current[-1]:
                best_by_secid[secid] = row

    return list(best_by_secid.values())


def main():
    parser = argparse.ArgumentParser(description="Extract related MOEX tickers for loaded news")
    parser.add_argument("--from-date", default=None, help="Filter news from YYYY-MM-DD")
    parser.add_argument("--to-date", default=None, help="Filter news to YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--min-score", type=float, default=float(os.getenv("NEWS_MATCH_MIN_SCORE", "0.65")))
    parser.add_argument("--truncate", action="store_true", help="Truncate dwh.news_company_candidates before inserting")
    args = parser.parse_args()

    client = get_client()
    news = fetch_news(client, args.from_date, args.to_date, args.limit)
    dictionary = fetch_dictionary(client)

    rows: list[tuple] = []
    for item in news:
        rows.extend(best_matches_for_news(item, dictionary, args.min_score))

    if args.truncate:
        client.command("TRUNCATE TABLE dwh.news_company_candidates")

    if rows:
        client.insert(
            "dwh.news_company_candidates",
            rows,
            column_names=[
                "news_id",
                "secid",
                "boardid",
                "match_method",
                "matched_field",
                "matched_value",
                "match_score",
            ],
        )
    print(f"Matched {len(rows)} news-company candidates for {len(news)} news items")


if __name__ == "__main__":
    main()
