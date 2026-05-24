from pathlib import Path
import ast

import pandas as pd


INPUT_PATH = Path("news_collection.parquet")  # поменяй на свой parquet-файл
OUTPUT_PATH = Path("news.csv")


def normalize_title(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"no title", "not stated", "nan", "none", "null"}:
        return ""
    return text


def normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def normalize_date(value) -> str:
    if pd.isna(value):
        return ""

    dt = pd.to_datetime(value, errors="coerce")
    if pd.isna(dt):
        return ""

    return dt.strftime("%Y-%m-%d")


def normalize_time(value) -> str:
    if pd.isna(value):
        return ""

    text = str(value).strip()

    if text.lower() in {"", "not stated", "nan", "none", "null"}:
        return ""

    parsed = pd.to_datetime(text, errors="coerce")

    if pd.isna(parsed):
        return ""

    return parsed.strftime("%H:%M:%S")


def normalize_tags(value) -> str:
    if pd.isna(value):
        return "[]"

    if isinstance(value, list):
        return str([str(item).strip() for item in value if str(item).strip()])

    text = str(value).strip()

    if not text or text.lower() in {"nan", "none", "null", "not stated"}:
        return "[]"

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return str([str(item).strip() for item in parsed if str(item).strip()])
        except Exception:
            pass

    parts = [
        part.strip()
        for part in text.replace(";", ",").split(",")
        if part.strip()
    ]

    return str(parts)


def main():
    df = pd.read_parquet(INPUT_PATH)

    print(df.head())
    print(df.columns)
    print(df.dtypes)

    required = ["title", "body", "date", "time", "tags"]
    missing = [col for col in required if col not in df.columns]

    if missing:
        raise ValueError(f"Missing columns: {missing}. Existing columns: {list(df.columns)}")

    result = pd.DataFrame()
    result["title"] = df["title"].apply(normalize_title)
    result["body"] = df["body"].apply(normalize_text)
    result["date"] = df["date"].apply(normalize_date)
    result["time"] = df["time"].apply(normalize_time)
    result["tags"] = df["tags"].apply(normalize_tags)

    result = result[
        (result["title"].str.strip() != "") |
        (result["body"].str.strip() != "")
    ]

    result = result[result["date"].str.strip() != ""]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)

    print(f"Saved: {OUTPUT_PATH}")
    print(f"Rows: {len(result)}")
    print(result.head())


if __name__ == "__main__":
    main()