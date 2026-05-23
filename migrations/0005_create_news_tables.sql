CREATE TABLE IF NOT EXISTS raw.news_raw
(
    news_id String,
    title String,
    body String,
    published_date Date DEFAULT toDate('1970-01-01'),
    published_time Nullable(String),
    published_at Nullable(DateTime),
    time_precision LowCardinality(String) DEFAULT 'unknown',
    tags Array(String),
    source_file String DEFAULT '',
    loaded_at DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (published_date, news_id);

CREATE OR REPLACE VIEW stg.v_news_events AS
SELECT
    news_id,
    nullIf(title, '') AS title,
    body,
    published_date,
    published_time,
    published_at,
    time_precision,
    tags,
    lengthUTF8(body) AS body_length,
    length(tags) AS tags_count,
    (title = '' OR lowerUTF8(title) IN ('no title', 'без заголовка', 'not stated')) AS title_is_missing,
    loaded_at
FROM raw.news_raw;

CREATE TABLE IF NOT EXISTS dwh.news_ticker_dictionary
(
    secid String,
    boardid String,
    alias String,
    alias_normalized String,
    alias_type LowCardinality(String),
    source LowCardinality(String) DEFAULT 'moex_instruments',
    weight Float32 DEFAULT 1.0,
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (secid, alias_normalized, alias_type);

CREATE TABLE IF NOT EXISTS dwh.news_company_candidates
(
    news_id String,
    secid String,
    boardid String,
    match_method LowCardinality(String),
    matched_field LowCardinality(String),
    matched_value String,
    match_score Float32,
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (news_id, secid, match_score);

CREATE TABLE IF NOT EXISTS dwh.news_llm_assessment
(
    news_id String,
    secid String,
    relevance_score Float32,
    criticality_score Float32,
    sentiment LowCardinality(String),
    event_type LowCardinality(String),
    impact_horizon LowCardinality(String),
    confidence Float32,
    reason String,
    model_name String,
    prompt_version String,
    response_json String,
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (news_id, secid, created_at);

CREATE OR REPLACE VIEW mart.v_news_company_candidates AS
SELECT
    n.published_date,
    n.published_time,
    n.published_at,
    n.time_precision,
    c.news_id,
    c.secid,
    c.boardid,
    i.shortname,
    i.secname,
    n.title,
    n.tags,
    c.match_method,
    c.matched_field,
    c.matched_value,
    c.match_score,
    multiIf(
        c.match_score >= 0.90, 'high',
        c.match_score >= 0.75, 'medium',
        c.match_score >= 0.60, 'low',
        'weak'
    ) AS match_confidence
FROM dwh.news_company_candidates AS c
LEFT JOIN stg.v_news_events AS n
    ON c.news_id = n.news_id
LEFT JOIN stg.v_instruments_latest AS i
    ON c.secid = i.secid
   AND c.boardid = i.boardid;

CREATE OR REPLACE VIEW mart.v_news_criticality AS
SELECT
    n.published_date,
    n.published_time,
    n.published_at,
    n.time_precision,
    a.news_id,
    a.secid,
    i.shortname,
    i.secname,
    n.title,
    n.tags,
    a.relevance_score,
    a.criticality_score,
    multiIf(
        a.criticality_score >= 0.80, 'critical',
        a.criticality_score >= 0.60, 'high',
        a.criticality_score >= 0.40, 'medium',
        a.criticality_score >= 0.20, 'low',
        'very_low'
    ) AS criticality_level,
    a.sentiment,
    a.event_type,
    a.impact_horizon,
    a.confidence,
    a.reason,
    a.model_name,
    a.prompt_version,
    a.created_at
FROM dwh.news_llm_assessment AS a
LEFT JOIN stg.v_news_events AS n
    ON a.news_id = n.news_id
LEFT JOIN stg.v_instruments_latest AS i
    ON a.secid = i.secid;
