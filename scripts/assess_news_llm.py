import argparse
import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

import clickhouse_connect
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPT_VERSION = "news-criticality-v1"
ALLOWED_SENTIMENTS = {"positive", "negative", "neutral", "mixed", "unknown"}
ALLOWED_EVENT_TYPES = {"corporate", "macro", "regulatory", "sector", "market", "other"}
ALLOWED_HORIZONS = {"intraday", "short_term", "medium_term", "long_term", "unknown"}


@dataclass
class NewsCandidate:
    news_id: str
    secid: str
    boardid: str
    shortname: str
    secname: str
    title: str
    body: str
    tags: list[str]
    published_date: Any
    published_time: Any
    published_at: Any
    match_score: float
    match_method: str
    matched_field: str
    matched_value: str


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def assess(self, candidate: NewsCandidate) -> dict[str, Any]:
        ...


def get_client():
    load_dotenv(PROJECT_ROOT / ".env")
    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        secure=os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true",
    )


def clamp(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:  # noqa: BLE001
        return default


def normalize_label(value: Any, allowed: set[str], default: str) -> str:
    label = str(value or "").strip().lower()
    return label if label in allowed else default


def safe_json_loads(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise


def normalize_assessment(raw: dict[str, Any], candidate: NewsCandidate, provider: str, model: str, response_json: str) -> tuple:
    relevance_score = clamp(raw.get("relevance_score"), candidate.match_score)
    criticality_score = clamp(raw.get("criticality_score"), 0.0)
    confidence = clamp(raw.get("confidence"), 0.60)
    sentiment = normalize_label(raw.get("sentiment"), ALLOWED_SENTIMENTS, "unknown")
    event_type = normalize_label(raw.get("event_type"), ALLOWED_EVENT_TYPES, "other")
    impact_horizon = normalize_label(raw.get("impact_horizon"), ALLOWED_HORIZONS, "unknown")
    reason = str(raw.get("reason") or "").strip()[:2000]

    return (
        candidate.news_id,
        candidate.secid,
        relevance_score,
        criticality_score,
        sentiment,
        event_type,
        impact_horizon,
        confidence,
        reason,
        model,
        PROMPT_VERSION,
        response_json,
    )


class MockLLMProvider:
    provider_name = "mock"
    model_name = "mock-news-criticality-rules"

    NEGATIVE_KEYWORDS = {
        "санкц", "суд", "иск", "штраф", "убыт", "банкрот", "дефолт", "сниж", "паден",
        "отриц", "риск", "расслед", "запрет", "огранич", "авар", "дивиденды не", "сократ",
    }
    POSITIVE_KEYWORDS = {
        "рост", "увелич", "прибыл", "выручк", "дивиденд", "рекоменд", "одобр", "контракт",
        "разреш", "покупк", "байбек", "рекорд", "повыс", "запуск",
    }
    CRITICAL_KEYWORDS = {
        "дивиденд", "прибыл", "выручк", "санкц", "ставк", "цб", "суд", "штраф", "банкрот",
        "дефолт", "отчет", "мсфо", "рсбу", "слиян", "поглощ", "байбек", "эмисс", "делист",
    }
    MACRO_KEYWORDS = {"цб", "ставк", "инфляц", "ввп", "рубл", "нефт", "доллар", "курс"}
    REGULATORY_KEYWORDS = {"цб", "регулятор", "санкц", "закон", "правитель", "минфин", "фас", "суд", "штраф"}

    def assess(self, candidate: NewsCandidate) -> dict[str, Any]:
        text = f"{candidate.title}\n{candidate.body}\n{' '.join(candidate.tags)}".casefold().replace("ё", "е")
        relevance = max(float(candidate.match_score), 0.55)
        if candidate.matched_field == "title":
            relevance = min(1.0, relevance + 0.10)
        elif candidate.matched_field == "tags":
            relevance = min(1.0, relevance + 0.05)

        critical_hits = sum(1 for keyword in self.CRITICAL_KEYWORDS if keyword in text)
        negative_hits = sum(1 for keyword in self.NEGATIVE_KEYWORDS if keyword in text)
        positive_hits = sum(1 for keyword in self.POSITIVE_KEYWORDS if keyword in text)

        criticality = 0.18 + 0.45 * relevance + min(0.30, 0.08 * critical_hits)
        if candidate.matched_field == "title":
            criticality += 0.08
        if negative_hits or positive_hits:
            criticality += 0.05
        criticality = clamp(criticality)

        if negative_hits > positive_hits:
            sentiment = "negative"
        elif positive_hits > negative_hits:
            sentiment = "positive"
        elif positive_hits and negative_hits:
            sentiment = "mixed"
        else:
            sentiment = "neutral"

        if any(keyword in text for keyword in self.REGULATORY_KEYWORDS):
            event_type = "regulatory"
        elif any(keyword in text for keyword in self.MACRO_KEYWORDS):
            event_type = "macro"
        elif critical_hits:
            event_type = "corporate"
        else:
            event_type = "other"

        impact_horizon = "intraday" if criticality >= 0.65 else "short_term"
        reason = (
            "Mock assessment based on candidate match score and financial-news keywords. "
            f"matched_field={candidate.matched_field}, matched_value={candidate.matched_value}, "
            f"critical_hits={critical_hits}, positive_hits={positive_hits}, negative_hits={negative_hits}."
        )
        return {
            "relevance_score": relevance,
            "criticality_score": criticality,
            "sentiment": sentiment,
            "event_type": event_type,
            "impact_horizon": impact_horizon,
            "confidence": 0.55,
            "reason": reason,
        }


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + " ..."


def build_prompt(candidate: NewsCandidate, max_body_chars: int) -> str:
    body = truncate_text(candidate.body or "", max_body_chars)
    tags = candidate.tags or []
    return f"""
Ты — аналитический модуль для оценки финансовых новостей российского фондового рынка.
Твоя задача — оценить, насколько новость релевантна конкретной компании и насколько она потенциально важна для краткосрочной ликвидности, стакана заявок и поведения участников рынка.

Компания-кандидат:
- secid: {candidate.secid}
- shortname: {candidate.shortname}
- secname: {candidate.secname}
- match_score из словарного matching: {candidate.match_score:.3f}
- matched_field: {candidate.matched_field}
- matched_value: {candidate.matched_value}

Новость:
- title: {candidate.title}
- body: {body}
- tags: {json.dumps(tags, ensure_ascii=False)}
- published_date: {candidate.published_date}
- published_time: {candidate.published_time}

Верни строго один JSON-объект без markdown и без пояснений вне JSON:
{{
  "relevance_score": число от 0 до 1,
  "criticality_score": число от 0 до 1,
  "sentiment": "positive" | "negative" | "neutral" | "mixed" | "unknown",
  "event_type": "corporate" | "macro" | "regulatory" | "sector" | "market" | "other",
  "impact_horizon": "intraday" | "short_term" | "medium_term" | "long_term" | "unknown",
  "confidence": число от 0 до 1,
  "reason": "краткое объяснение на русском языке"
}}

Правила:
- Не придумывай новые тикеры и компании.
- relevance_score отражает связь новости именно с указанной компанией.
- criticality_score отражает потенциальную важность новости для ликвидности/стакана/краткосрочной рыночной реакции, а не просто тональность.
- Если компания упомянута случайно, relevance_score и criticality_score должны быть низкими.
""".strip()


class GigaChatProvider:
    provider_name = "gigachat"

    def __init__(self):
        try:
            from gigachat import GigaChat  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Install gigachat package or use LLM_PROVIDER=mock") from exc

        credentials = os.getenv("GIGACHAT_CREDENTIALS") or os.getenv("GIGACHAT_AUTH_KEY")
        if not credentials:
            raise RuntimeError("Set GIGACHAT_CREDENTIALS or use LLM_PROVIDER=mock")

        self.model_name = os.getenv("GIGACHAT_MODEL", "GigaChat")
        verify_ssl = os.getenv("GIGACHAT_VERIFY_SSL_CERTS", "false").lower() == "true"
        self._max_body_chars = int(os.getenv("LLM_MAX_BODY_CHARS", "3500"))
        self._client = GigaChat(credentials=credentials, model=self.model_name, verify_ssl_certs=verify_ssl)

    def assess(self, candidate: NewsCandidate) -> dict[str, Any]:
        prompt = build_prompt(candidate, self._max_body_chars)
        response = self._client.chat(prompt)
        content = response.choices[0].message.content
        parsed = safe_json_loads(content)
        if not isinstance(parsed, dict):
            raise ValueError(f"GigaChat returned non-object JSON: {content}")
        return parsed


def make_provider() -> LLMProvider:
    provider_name = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    if provider_name == "mock":
        return MockLLMProvider()
    if provider_name == "gigachat":
        return GigaChatProvider()
    raise ValueError("Unsupported LLM_PROVIDER. Use 'mock' or 'gigachat'.")


def fetch_candidates(
    client,
    from_date: str | None,
    to_date: str | None,
    secid: str | None,
    min_score: float,
    limit: int,
    force: bool,
) -> list[NewsCandidate]:
    where = ["c.match_score >= {min_score:Float32}"]
    params: dict[str, Any] = {"min_score": min_score, "limit": limit}

    if from_date:
        where.append("c.published_date >= {from_date:Date}")
        params["from_date"] = from_date

    if to_date:
        where.append("c.published_date <= {to_date:Date}")
        params["to_date"] = to_date

    if secid:
        where.append("c.secid = {secid:String}")
        params["secid"] = secid.upper()

    if not force:
        where.append("a.news_id = ''")

    result = client.query(
        f"""
        SELECT
            c.news_id AS news_id,
            c.secid AS secid,
            c.boardid AS boardid,
            ifNull(c.shortname, '') AS shortname,
            ifNull(c.secname, '') AS secname,
            ifNull(c.title, '') AS title,
            ifNull(n.body, '') AS body,
            c.tags AS tags,
            c.published_date AS published_date,
            c.published_time AS published_time,
            c.published_at AS published_at,
            c.match_score AS match_score,
            c.match_method AS match_method,
            c.matched_field AS matched_field,
            c.matched_value AS matched_value
        FROM mart.v_news_company_candidates AS c
        LEFT JOIN stg.v_news_events AS n
            ON c.news_id = n.news_id
        LEFT JOIN dwh.news_llm_assessment AS a
            ON c.news_id = a.news_id
           AND c.secid = a.secid
        WHERE {' AND '.join(where)}
        ORDER BY
            c.published_date DESC,
            c.match_score DESC,
            c.news_id,
            c.secid
        LIMIT {{limit:UInt32}}
        """,
        parameters=params,
    )

    columns = [name.split(".")[-1] for name in result.column_names]
    rows = [dict(zip(columns, row, strict=False)) for row in result.result_rows]

    return [NewsCandidate(**row) for row in rows]


def finish_run(client, run_id: str, provider: LLMProvider, status: str, processed: int, inserted: int, error: str = ""):
    client.insert(
        "dwh.news_llm_runs",
        [(run_id, provider.provider_name, provider.model_name, PROMPT_VERSION, datetime.utcnow(), status, processed, inserted, error[:4000])],
        column_names=[
            "run_id",
            "provider",
            "model_name",
            "prompt_version",
            "finished_at",
            "status",
            "records_processed",
            "records_inserted",
            "error_message",
        ],
    )


def main():
    parser = argparse.ArgumentParser(description="Assess news criticality for matched company candidates")
    parser.add_argument("--from-date", default=None, help="Filter candidates from publication date YYYY-MM-DD")
    parser.add_argument("--to-date", default=None, help="Filter candidates to publication date YYYY-MM-DD")
    parser.add_argument("--secid", default=None, help="Optional ticker filter, for example SBER")
    parser.add_argument("--min-score", type=float, default=float(os.getenv("LLM_MIN_MATCH_SCORE", "0.65")))
    parser.add_argument("--limit", type=int, default=int(os.getenv("LLM_ASSESS_LIMIT", "100")))
    parser.add_argument("--force", action="store_true", help="Re-assess already assessed news-company pairs")
    parser.add_argument("--dry-run", action="store_true", help="Print candidates and assessments without inserting")
    args = parser.parse_args()

    client = get_client()
    provider = make_provider()
    run_id = hashlib.sha1(f"{uuid.uuid4()}".encode()).hexdigest()
    candidates = fetch_candidates(
        client=client,
        from_date=args.from_date,
        to_date=args.to_date,
        secid=args.secid,
        min_score=args.min_score,
        limit=args.limit,
        force=args.force,
    )
    print(f"Provider={provider.provider_name}, model={provider.model_name}, candidates={len(candidates)}")

    rows = []
    processed = 0
    try:
        for candidate in candidates:
            processed += 1
            raw = provider.assess(candidate)
            response_json = json.dumps(raw, ensure_ascii=False)
            row = normalize_assessment(raw, candidate, provider.provider_name, provider.model_name, response_json)
            rows.append(row)
            print(
                f"{processed}/{len(candidates)} {candidate.news_id[:8]} {candidate.secid}: "
                f"relevance={row[2]:.2f}, criticality={row[3]:.2f}, sentiment={row[4]}, event={row[5]}"
            )

        if args.dry_run:
            print(json.dumps(rows[:5], ensure_ascii=False, default=str, indent=2))
            return

        if rows:
            client.insert(
                "dwh.news_llm_assessment",
                rows,
                column_names=[
                    "news_id",
                    "secid",
                    "relevance_score",
                    "criticality_score",
                    "sentiment",
                    "event_type",
                    "impact_horizon",
                    "confidence",
                    "reason",
                    "model_name",
                    "prompt_version",
                    "response_json",
                ],
            )
        finish_run(client, run_id, provider, "success", processed, len(rows))
        print(f"Inserted {len(rows)} assessments")
    except Exception as exc:  # noqa: BLE001
        if not args.dry_run:
            finish_run(client, run_id, provider, "failed", processed, len(rows), str(exc))
        raise


if __name__ == "__main__":
    main()
