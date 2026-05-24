CREATE OR REPLACE VIEW mart.v_news_criticality_pending AS
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

    c.match_method AS match_method,
    c.matched_field AS matched_field,
    c.matched_value AS matched_value,
    c.match_score AS match_score,
    c.match_confidence AS match_confidence
FROM mart.v_news_company_candidates AS c
LEFT JOIN
(
    SELECT DISTINCT
        news_id AS news_id,
        secid AS secid
    FROM dwh.news_llm_assessment
) AS a
    ON c.news_id = a.news_id
   AND c.secid = a.secid
WHERE a.news_id = '';
