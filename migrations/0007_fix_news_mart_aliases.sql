CREATE OR REPLACE VIEW mart.v_news_company_candidates AS
SELECT
    n.published_date AS published_date,
    n.published_time AS published_time,
    n.published_at AS published_at,
    n.time_precision AS time_precision,
    c.news_id AS news_id,
    c.secid AS secid,
    c.boardid AS boardid,
    ifNull(i.shortname, '') AS shortname,
    ifNull(i.secname, '') AS secname,
    ifNull(n.title, '') AS title,
    n.tags AS tags,
    c.match_method AS match_method,
    c.matched_field AS matched_field,
    c.matched_value AS matched_value,
    c.match_score AS match_score,
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
WITH latest_assessments AS
(
    SELECT
        news_id AS news_id,
        secid AS secid,
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
    GROUP BY
        news_id,
        secid
),
best_candidates AS
(
    SELECT
        news_id AS news_id,
        secid AS secid,
        argMax(boardid, match_score) AS boardid,
        max(match_score) AS match_score,
        argMax(match_method, match_score) AS match_method,
        argMax(matched_field, match_score) AS matched_field,
        argMax(matched_value, match_score) AS matched_value
    FROM dwh.news_company_candidates
    GROUP BY
        news_id,
        secid
)
SELECT
    n.published_date AS published_date,
    n.published_time AS published_time,
    n.published_at AS published_at,
    n.time_precision AS time_precision,
    a.news_id AS news_id,
    a.secid AS secid,
    ifNull(c.boardid, '') AS boardid,
    ifNull(i.shortname, '') AS shortname,
    ifNull(i.secname, '') AS secname,
    ifNull(n.title, '') AS title,
    n.tags AS tags,
    c.match_score AS match_score,
    c.match_method AS match_method,
    c.matched_field AS matched_field,
    c.matched_value AS matched_value,
    a.relevance_score AS relevance_score,
    a.criticality_score AS criticality_score,
    multiIf(
        a.criticality_score >= 0.80, 'critical',
        a.criticality_score >= 0.60, 'high',
        a.criticality_score >= 0.40, 'medium',
        a.criticality_score >= 0.20, 'low',
        'very_low'
    ) AS criticality_level,
    a.sentiment AS sentiment,
    a.event_type AS event_type,
    a.impact_horizon AS impact_horizon,
    a.confidence AS confidence,
    a.reason AS reason,
    a.model_name AS model_name,
    a.prompt_version AS prompt_version,
    a.assessed_at AS assessed_at
FROM latest_assessments AS a
LEFT JOIN stg.v_news_events AS n
    ON a.news_id = n.news_id
LEFT JOIN best_candidates AS c
    ON a.news_id = c.news_id
   AND a.secid = c.secid
LEFT JOIN stg.v_instruments_latest AS i
    ON a.secid = i.secid
   AND ifNull(c.boardid, i.boardid) = i.boardid;

CREATE OR REPLACE VIEW mart.v_news_criticality_pending AS
WITH assessed AS
(
    SELECT DISTINCT
        news_id AS news_id,
        secid AS secid
    FROM dwh.news_llm_assessment
)
SELECT
    c.published_date AS published_date,
    c.published_time AS published_time,
    c.published_at AS published_at,
    c.time_precision AS time_precision,
    c.news_id AS news_id,
    c.secid AS secid,
    c.boardid AS boardid,
    c.shortname AS shortname,
    c.secname AS secname,
    c.title AS title,
    n.body AS body,
    c.tags AS tags,
    c.match_method AS match_method,
    c.matched_field AS matched_field,
    c.matched_value AS matched_value,
    c.match_score AS match_score,
    c.match_confidence AS match_confidence
FROM mart.v_news_company_candidates AS c
LEFT JOIN stg.v_news_events AS n
    ON c.news_id = n.news_id
LEFT JOIN assessed AS a
    ON c.news_id = a.news_id
   AND c.secid = a.secid
WHERE a.news_id = '' OR isNull(a.news_id);
