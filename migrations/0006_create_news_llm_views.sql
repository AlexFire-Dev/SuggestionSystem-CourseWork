CREATE TABLE IF NOT EXISTS dwh.news_llm_runs
(
    run_id String,
    provider LowCardinality(String),
    model_name String,
    prompt_version String,
    started_at DateTime DEFAULT now(),
    finished_at Nullable(DateTime),
    status LowCardinality(String) DEFAULT 'running',
    records_processed UInt32 DEFAULT 0,
    records_inserted UInt32 DEFAULT 0,
    error_message String DEFAULT ''
)
ENGINE = MergeTree
ORDER BY (started_at, run_id);

CREATE OR REPLACE VIEW mart.v_news_criticality AS
WITH latest_assessments AS
(
    SELECT
        news_id,
        secid,
        argMax(relevance_score, created_at) AS relevance_score,
        argMax(criticality_score, created_at) AS criticality_score,
        argMax(sentiment, created_at) AS sentiment,
        argMax(event_type, created_at) AS event_type,
        argMax(impact_horizon, created_at) AS impact_horizon,
        argMax(confidence, created_at) AS confidence,
        argMax(reason, created_at) AS reason,
        argMax(model_name, created_at) AS model_name,
        argMax(prompt_version, created_at) AS prompt_version,
        max(created_at) AS assessed_at
    FROM dwh.news_llm_assessment
    GROUP BY news_id, secid
)
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
    a.assessed_at
FROM latest_assessments AS a
LEFT JOIN stg.v_news_events AS n
    ON a.news_id = n.news_id
LEFT JOIN stg.v_instruments_latest AS i
    ON a.secid = i.secid;

CREATE OR REPLACE VIEW mart.v_news_criticality_pending AS
SELECT
    c.published_date,
    c.published_time,
    c.published_at,
    c.time_precision,
    c.news_id,
    c.secid,
    c.boardid,
    c.shortname,
    c.secname,
    c.title,
    n.body,
    c.tags,
    c.match_method,
    c.matched_field,
    c.matched_value,
    c.match_score,
    c.match_confidence
FROM mart.v_news_company_candidates AS c
LEFT JOIN stg.v_news_events AS n
    ON c.news_id = n.news_id
WHERE (c.news_id, c.secid) NOT IN
(
    SELECT news_id, secid
    FROM dwh.news_llm_assessment
);
