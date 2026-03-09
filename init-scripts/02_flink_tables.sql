-- init-scripts/02_flink_tables.sql
-- Tables that Flink writes into (via JDBC connector).
-- These run on ClickHouse first start, AFTER 01_create_tables.sql.

-- ── Flink enriched events (row-level, written by Flink INSERT job) ──────────
CREATE TABLE IF NOT EXISTS pipeline_db.flink_enriched_events
(
    event_id    String,
    user_id     String,
    event_type  LowCardinality(String),
    page        String,
    product     String,
    amount      Float64,
    country     LowCardinality(String),
    city        String,
    device      LowCardinality(String),
    browser     LowCardinality(String),
    event_time  DateTime64(3, 'UTC'),
    is_purchase UInt8,                    -- BOOLEAN maps to UInt8 in ClickHouse
    amount_usd  Float64
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(event_time)
ORDER BY (event_type, user_id, event_time)
TTL event_time + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;


-- ── Flink window aggregations (1-min tumbling windows) ──────────────────────
CREATE TABLE IF NOT EXISTS pipeline_db.flink_window_counts
(
    window_start    DateTime64(3, 'UTC'),
    window_end      DateTime64(3, 'UTC'),
    event_type      LowCardinality(String),
    device          LowCardinality(String),
    country         LowCardinality(String),
    event_count     UInt64,
    total_amount    Float64
)
ENGINE = ReplacingMergeTree()             -- Flink may re-emit windows; dedup on merge
PARTITION BY toYYYYMMDD(window_start)
ORDER BY (window_start, event_type, device, country)
TTL window_start + INTERVAL 60 DAY
SETTINGS index_granularity = 8192;
