CREATE OR REPLACE VIEW mart.v_news_company_candidates AS
WITH ranked_candidates AS
(
    SELECT
        news_id AS news_id,
        secid AS secid,
        boardid AS boardid,
        match_method AS match_method,
        matched_field AS matched_field,
        matched_value AS matched_value,
        match_score AS match_score,
        row_number() OVER (
            PARTITION BY news_id, secid
            ORDER BY match_score DESC, matched_field ASC, matched_value ASC
        ) AS rn
    FROM dwh.news_company_candidates
)
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

    -- dwh.news_company_candidates does not contain match_confidence in the current schema.
    -- We expose it for API compatibility and use match_score as the confidence proxy.
    toFloat32(c.match_score) AS match_confidence
FROM ranked_candidates AS c
LEFT JOIN stg.v_news_events AS n
    ON c.news_id = n.news_id
LEFT JOIN stg.v_instruments_latest AS i
    ON c.secid = i.secid
   AND c.boardid = i.boardid
WHERE c.rn = 1;


CREATE OR REPLACE VIEW mart.v_news_criticality AS
WITH latest_assessment AS
(
    SELECT
        news_id AS news_id,
        secid AS secid,

        argMax(relevance_score, assessed_at) AS relevance_score,
        argMax(criticality_score, assessed_at) AS criticality_score,
        argMax(sentiment, assessed_at) AS sentiment,
        argMax(event_type, assessed_at) AS event_type,
        argMax(impact_horizon, assessed_at) AS impact_horizon,
        argMax(confidence, assessed_at) AS confidence,
        argMax(reason, assessed_at) AS reason,
        argMax(model_name, assessed_at) AS model_name,
        argMax(prompt_version, assessed_at) AS prompt_version,
        argMax(response_json, assessed_at) AS response_json,
        max(assessed_at) AS latest_assessed_at
    FROM dwh.news_llm_assessment
    GROUP BY
        news_id,
        secid
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
    c.tags AS tags,

    c.match_score AS match_score,
    c.match_method AS match_method,
    c.matched_field AS matched_field,
    c.matched_value AS matched_value,

    a.relevance_score AS relevance_score,
    a.criticality_score AS criticality_score,

    multiIf(
        ifNull(a.criticality_score, 0) >= 0.80, 'critical',
        ifNull(a.criticality_score, 0) >= 0.60, 'high',
        ifNull(a.criticality_score, 0) >= 0.40, 'medium',
        ifNull(a.criticality_score, 0) >= 0.20, 'low',
        'minimal'
    ) AS criticality_level,

    a.sentiment AS sentiment,
    a.event_type AS event_type,
    a.impact_horizon AS impact_horizon,
    a.confidence AS confidence,
    a.reason AS reason,
    a.model_name AS model_name,
    a.prompt_version AS prompt_version,
    a.latest_assessed_at AS assessed_at
FROM mart.v_news_company_candidates AS c
INNER JOIN latest_assessment AS a
    ON c.news_id = a.news_id
   AND c.secid = a.secid;


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
    c.tags AS tags,

    c.match_score AS match_score,
    c.match_method AS match_method,
    c.matched_field AS matched_field,
    c.matched_value AS matched_value
FROM mart.v_news_company_candidates AS c
LEFT JOIN assessed AS a
    ON c.news_id = a.news_id
   AND c.secid = a.secid
WHERE isNull(a.news_id) OR a.news_id = '';
