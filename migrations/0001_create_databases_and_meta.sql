CREATE DATABASE IF NOT EXISTS meta;
CREATE DATABASE IF NOT EXISTS raw;
CREATE DATABASE IF NOT EXISTS stg;
CREATE DATABASE IF NOT EXISTS dwh;
CREATE DATABASE IF NOT EXISTS mart;

CREATE TABLE IF NOT EXISTS meta.schema_migrations
(
    version String,
    filename String,
    checksum String,
    applied_at DateTime DEFAULT now(),
    execution_ms UInt64
)
ENGINE = MergeTree
ORDER BY version;

CREATE TABLE IF NOT EXISTS meta.pipeline_runs
(
    run_id UUID DEFAULT generateUUIDv4(),
    pipeline_name LowCardinality(String),
    source LowCardinality(String),
    status LowCardinality(String),
    started_at DateTime DEFAULT now(),
    finished_at Nullable(DateTime),
    rows_loaded UInt64 DEFAULT 0,
    message Nullable(String)
)
ENGINE = MergeTree
ORDER BY (pipeline_name, started_at);
