-- init-scripts/create_tables.sql
-- This file runs automatically when ClickHouse starts for the first time.

CREATE DATABASE IF NOT EXISTS pipeline_db;

-- Main events table 
-- MergeTree is ClickHouse's core engine.
-- ORDER BY defines the primary index (how data is sorted on disk).
-- PARTITION BY organises data into daily folders for fast range queries.
CREATE TABLE IF NOT EXISTS pipeline_db.user_events
(
    event_id    String,
    user_id     String,
    event_type  LowCardinality(String),   -- LowCardinality = dict-encoded, great for enums
    page        String,
    product     String,
    amount      Float64,
    country     LowCardinality(String),
    city        String,
    device      LowCardinality(String),
    browser     LowCardinality(String),
    timestamp   DateTime64(3, 'UTC')      -- millisecond precision, UTC
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)        -- one partition per day
ORDER BY (event_type, user_id, timestamp) -- primary sort key
TTL toDateTime(timestamp) + INTERVAL 30 DAY           -- auto-delete data older than 30 days
SETTINGS
    index_granularity = 8192;             -- default, tune for your query patterns


-- ── Materialised view: event counts per minute ────────────────────────────
-- ClickHouse materialised views update INCREMENTALLY as new rows arrive.
-- This is how you build real-time aggregations without re-scanning history.

CREATE TABLE IF NOT EXISTS pipeline_db.events_per_minute
(
    minute       DateTime,
    event_type   LowCardinality(String),
    device       LowCardinality(String),
    event_count  UInt64,
    total_amount Float64
)
ENGINE = SummingMergeTree()               -- auto-sums numeric columns on merge
PARTITION BY toYYYYMMDD(minute)
ORDER BY (minute, event_type, device);

CREATE MATERIALIZED VIEW IF NOT EXISTS pipeline_db.mv_events_per_minute
TO pipeline_db.events_per_minute
AS
SELECT
    toStartOfMinute(timestamp) AS minute,
    event_type,
    device,
    count()                    AS event_count,
    sum(amount)                AS total_amount
FROM pipeline_db.user_events
GROUP BY minute, event_type, device;


-- ── Materialised view: top countries ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_db.events_by_country
(
    country      LowCardinality(String),
    event_type   LowCardinality(String),
    event_count  UInt64,
    total_amount Float64
)
ENGINE = SummingMergeTree()
ORDER BY (country, event_type);

CREATE MATERIALIZED VIEW IF NOT EXISTS pipeline_db.mv_events_by_country
TO pipeline_db.events_by_country
AS
SELECT
    country,
    event_type,
    count()    AS event_count,
    sum(amount) AS total_amount
FROM pipeline_db.user_events
GROUP BY country, event_type;
