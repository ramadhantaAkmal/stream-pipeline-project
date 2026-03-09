-- ─────────────────────────────────────────────────────────────────────────────
-- flink/sql/pipeline.sql
--
-- This Flink SQL job:
--   1. Reads raw user-events from Kafka
--   2. Enriches & filters the stream
--   3. Writes results to ClickHouse via JDBC
--
-- Run interactively via the SQL Client:
--   docker compose --profile sql-client up flink-sql-client
--   (then paste this file contents in, or use: sql-client.sh -f /opt/flink/sql/pipeline.sql)
-- ─────────────────────────────────────────────────────────────────────────────

-- ── STEP 1: Declare the Kafka source table ───────────────────────────────────
-- Flink will read from the 'user-events' topic.
-- The 'event_time' is watermarked so Flink knows how to handle late arrivals.

CREATE TABLE kafka_user_events (
    event_id    STRING,
    user_id     STRING,
    event_type  STRING,
    page        STRING,
    product     STRING,
    amount      DOUBLE,
    country     STRING,
    city        STRING,
    device      STRING,
    browser     STRING,
    `timestamp` STRING,                          -- arrives as ISO string from Faker
    event_time  AS TO_TIMESTAMP(`timestamp`, 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS+HH:mm'),
    WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
) WITH (
    'connector'                     = 'kafka',
    'topic'                         = 'user-events',
    'properties.bootstrap.servers'  = 'kafka:9092',
    'properties.group.id'           = 'flink-consumer-group',
    'scan.startup.mode'             = 'latest-offset',
    'format'                        = 'json',
    'json.ignore-parse-errors'      = 'true'    -- skip malformed messages gracefully
);


-- ── STEP 2: Declare the ClickHouse sink table (via JDBC) ─────────────────────
-- Flink writes processed rows here using the JDBC connector.
-- Make sure flink-connector-jdbc JAR is in /opt/flink/lib/extra/

CREATE TABLE clickhouse_enriched_events (
    event_id    STRING,
    user_id     STRING,
    event_type  STRING,
    page        STRING,
    product     STRING,
    amount      DOUBLE,
    country     STRING,
    city        STRING,
    device      STRING,
    browser     STRING,
    event_time  TIMESTAMP(3),
    is_purchase BOOLEAN,
    amount_usd  DOUBLE         -- could be enriched via currency conversion
) WITH (
    'connector'     = 'jdbc',
    'url'           = 'jdbc:clickhouse://clickhouse:8123/pipeline_db',
    'table-name'    = 'flink_enriched_events',
    'username'      = 'admin',
    'password'      = 'admin123',
    'sink.buffer-flush.max-rows'    = '500',
    'sink.buffer-flush.interval'    = '5s',
    'sink.max-retries'              = '3'
);


-- ── STEP 3: Declare a windowed aggregation sink ──────────────────────────────
-- Flink computes 1-minute tumbling window counts and writes to ClickHouse.

CREATE TABLE clickhouse_window_counts (
    window_start    TIMESTAMP(3),
    window_end      TIMESTAMP(3),
    event_type      STRING,
    device          STRING,
    country         STRING,
    event_count     BIGINT,
    total_amount    DOUBLE
) WITH (
    'connector'     = 'jdbc',
    'url'           = 'jdbc:clickhouse://clickhouse:8123/pipeline_db',
    'table-name'    = 'flink_window_counts',
    'username'      = 'admin',
    'password'      = 'admin123',
    'sink.buffer-flush.max-rows'    = '100',
    'sink.buffer-flush.interval'    = '10s'
);


-- ── STEP 4: Insert enriched individual events ────────────────────────────────

INSERT INTO clickhouse_enriched_events
SELECT
    event_id,
    user_id,
    event_type,
    page,
    COALESCE(product, '')               AS product,
    COALESCE(amount, 0.0)               AS amount,
    country,
    city,
    device,
    browser,
    event_time,
    (event_type = 'purchase')           AS is_purchase,
    COALESCE(amount, 0.0)               AS amount_usd   -- extend: multiply by FX rate
FROM kafka_user_events
WHERE event_id IS NOT NULL;             -- filter out any null/malformed events


-- ── STEP 5: Insert 1-minute tumbling window aggregations ────────────────────
-- Flink's TUMBLE() function groups events into fixed non-overlapping windows.
-- This is more powerful than ClickHouse materialised views because Flink
-- can handle late data, stateful joins, sessionisation, etc.

INSERT INTO clickhouse_window_counts
SELECT
    TUMBLE_START(event_time, INTERVAL '1' MINUTE)   AS window_start,
    TUMBLE_END(event_time,   INTERVAL '1' MINUTE)   AS window_end,
    event_type,
    device,
    country,
    COUNT(*)                                         AS event_count,
    SUM(COALESCE(amount, 0.0))                       AS total_amount
FROM kafka_user_events
GROUP BY
    TUMBLE(event_time, INTERVAL '1' MINUTE),
    event_type,
    device,
    country;
