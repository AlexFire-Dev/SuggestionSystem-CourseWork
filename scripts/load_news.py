import argparse
import ast
import csv
import hashlib
import json
import os
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import clickhouse_connect
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_FORMATS = {"auto", "csv", "json"}


def get_client():
    load_dotenv(PROJECT_ROOT / ".env")
    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        secure=os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true",
    )


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def parse_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    if isinstance(value, tuple):
        return [clean_text(item) for item in value if clean_text(item)]

    text = clean_text(value)
    if not text or text in {"[]", "{}"}:
        return []

    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, (list, tuple, set)):
            return [clean_text(item) for item in parsed if clean_text(item)]
    except Exception:  # noqa: BLE001
        pass

    if ";" in text:
        return [part.strip() for part in text.split(";") if part.strip()]
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [text]


def parse_date(value: Any) -> date:
    text = clean_text(value)
    if not text:
        return date(1970, 1, 1)
    candidates = [
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d-%m-%Y",
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return date(1970, 1, 1)


def parse_time(value: Any) -> tuple[str | None, str]:
    text = clean_text(value)
    if not text or text.lower() in {"not stated", "unknown", "no time", "none", "null"}:
        return None, "date_only"

    candidates = ["%H:%M:%S", "%H:%M"]
    for fmt in candidates:
        try:
            parsed = datetime.strptime(text[:8], fmt).time()
            return parsed.strftime("%H:%M:%S"), "exact"
        except ValueError:
            continue
    return None, "date_only"


def make_published_at(pub_date: date, pub_time: str | None) -> datetime | None:
    if pub_date == date(1970, 1, 1):
        return None
    if pub_time:
        parsed_time = datetime.strptime(pub_time, "%H:%M:%S").time()
        return datetime.combine(pub_date, parsed_time)
    return datetime.combine(pub_date, time(12, 0, 0))


def make_news_id(title: str, body: str, pub_date: date, pub_time: str | None, tags: list[str]) -> str:
    payload = "\n".join([
        title.casefold().strip(),
        body.casefold().strip(),
        pub_date.isoformat(),
        pub_time or "",
        "|".join(sorted(tag.casefold().strip() for tag in tags)),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader)


def load_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], dict):
        block = payload["data"]
        columns = block.get("columns", [])
        return [dict(zip(columns, row, strict=False)) for row in block.get("data", [])]
    if isinstance(payload, dict) and "columns" in payload and "data" in payload:
        columns = payload.get("columns", [])
        return [dict(zip(columns, row, strict=False)) for row in payload.get("data", [])]
    if isinstance(payload, dict):
        return [payload]
    raise ValueError(f"Unsupported JSON structure in {path}")


def detect_format(path: Path, explicit_format: str) -> str:
    if explicit_format != "auto":
        return explicit_format
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    raise ValueError("Cannot detect input format. Pass --format csv or --format json")


def normalize_row(row: dict[str, Any], source_file: str) -> tuple:
    title = clean_text(row.get("title") or row.get("article_title") or row.get("article title"))
    body = clean_text(row.get("body") or row.get("article_body") or row.get("article body") or row.get("text"))
    pub_date = parse_date(row.get("date") or row.get("published_date") or row.get("DateTime"))
    pub_time, precision = parse_time(row.get("time") or row.get("published_time"))
    tags = parse_tags(row.get("tags") or row.get("tag") or row.get("Tags"))
    published_at = make_published_at(pub_date, pub_time)
    if pub_date == date(1970, 1, 1):
        precision = "unknown"
    news_id = make_news_id(title, body, pub_date, pub_time, tags)
    return (
        news_id,
        title,
        body,
        pub_date,
        pub_time,
        published_at,
        precision,
        tags,
        source_file,
    )


def main():
    parser = argparse.ArgumentParser(description="Load normalized news into ClickHouse raw.news_raw")
    parser.add_argument("--file", required=True, help="Path to CSV or JSON news file")
    parser.add_argument("--format", default="auto", choices=sorted(ALLOWED_FORMATS))
    parser.add_argument("--truncate", action="store_true", help="Truncate raw.news_raw before loading")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        raise FileNotFoundError(path)

    input_format = detect_format(path, args.format)
    rows = load_csv(path) if input_format == "csv" else load_json(path)
    normalized = [normalize_row(row, source_file=path.name) for row in rows]

    client = get_client()
    if args.truncate:
        client.command("TRUNCATE TABLE raw.news_raw")

    if normalized:
        client.insert(
            "raw.news_raw",
            normalized,
            column_names=[
                "news_id",
                "title",
                "body",
                "published_date",
                "published_time",
                "published_at",
                "time_precision",
                "tags",
                "source_file",
            ],
        )

    print(f"Loaded {len(normalized)} news rows from {path}")


if __name__ == "__main__":
    main()
