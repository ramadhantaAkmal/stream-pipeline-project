"""
flink/jobs/job_window_aggregation.py
──────────────────────────────────────
PyFlink Job 2: Tumbling Window Aggregation
───────────────────────────────────────────
Reads user-events from Kafka and computes real-time aggregations
using Flink's event-time tumbling windows:

  - 1-minute window:  event counts + revenue by type / device / country
  - 5-minute window:  unique user counts (HyperLogLog approximation)

Results are written to ClickHouse for dashboard queries.

This is more powerful than ClickHouse materialised views alone because:
  ✓ Handles late-arriving events (watermark-based)
  ✓ Supports exactly-once semantics via checkpointing
  ✓ Can join with other streams mid-flight

Run:
  docker exec -it flink-jobmanager \
    /opt/flink/bin/flink run \
    --python /opt/flink/jobs/job_window_aggregation.py
"""

import os
import logging

from pyflink.datastream import StreamExecutionEnvironment, RuntimeExecutionMode
from pyflink.table import StreamTableEnvironment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WINDOW AGG JOB] %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC     = os.getenv("KAFKA_TOPIC", "user-events")
KAFKA_GROUP     = os.getenv("KAFKA_GROUP_ID", "flink-window-agg-group")
CLICKHOUSE_URL  = os.getenv("CLICKHOUSE_JDBC_URL", "jdbc:clickhouse://clickhouse:8123/pipeline_db")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "admin")
CLICKHOUSE_PASS = os.getenv("CLICKHOUSE_PASSWORD", "admin123")


def main():
    # ── Environment ───────────────────────────────────────────────────────────
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)
    env.set_parallelism(2)
    env.enable_checkpointing(30_000)
    t_env = StreamTableEnvironment.create(env)

    # ── Kafka source ──────────────────────────────────────────────────────────
    t_env.execute_sql(f"""
        CREATE TEMPORARY TABLE kafka_source (
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
            `timestamp` STRING,
            event_time  AS TO_TIMESTAMP(`timestamp`, 'yyyy-MM-dd''T''HH:mm:ss.SSSSSSXXX'),
            WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
        ) WITH (
            'connector'                    = 'kafka',
            'topic'                        = '{KAFKA_TOPIC}',
            'properties.bootstrap.servers' = '{KAFKA_BOOTSTRAP}',
            'properties.group.id'          = '{KAFKA_GROUP}',
            'scan.startup.mode'            = 'latest-offset',
            'format'                       = 'json',
            'json.ignore-parse-errors'     = 'true'
        )
    """)

    # ── Sink: 1-minute window counts ──────────────────────────────────────────
    t_env.execute_sql(f"""
        CREATE TEMPORARY TABLE sink_1min (
            window_start    TIMESTAMP(3),
            window_end      TIMESTAMP(3),
            event_type      STRING,
            device          STRING,
            country         STRING,
            event_count     BIGINT,
            unique_users    BIGINT,
            total_amount    DOUBLE,
            avg_amount      DOUBLE,
            purchase_count  BIGINT
        ) WITH (
            'connector'                  = 'jdbc',
            'url'                        = '{CLICKHOUSE_URL}',
            'table-name'                 = 'flink_window_1min',
            'username'                   = '{CLICKHOUSE_USER}',
            'password'                   = '{CLICKHOUSE_PASS}',
            'sink.buffer-flush.max-rows' = '200',
            'sink.buffer-flush.interval' = '10s',
            'sink.max-retries'           = '3'
        )
    """)

    # ── Sink: 5-minute window counts ──────────────────────────────────────────
    t_env.execute_sql(f"""
        CREATE TEMPORARY TABLE sink_5min (
            window_start    TIMESTAMP(3),
            window_end      TIMESTAMP(3),
            country         STRING,
            device          STRING,
            event_count     BIGINT,
            unique_users    BIGINT,
            total_revenue   DOUBLE
        ) WITH (
            'connector'                  = 'jdbc',
            'url'                        = '{CLICKHOUSE_URL}',
            'table-name'                 = 'flink_window_5min',
            'username'                   = '{CLICKHOUSE_USER}',
            'password'                   = '{CLICKHOUSE_PASS}',
            'sink.buffer-flush.max-rows' = '100',
            'sink.buffer-flush.interval' = '15s',
            'sink.max-retries'           = '3'
        )
    """)

    # ── Job A: 1-minute tumbling window ───────────────────────────────────────
    # Groups by event_type + device + country inside each 1-minute window.
    # TUMBLE() is Flink's fixed-size, non-overlapping window function.
    statement_set = t_env.create_statement_set()

    statement_set.add_insert_sql("""
        INSERT INTO sink_1min
        SELECT
            TUMBLE_START(event_time, INTERVAL '1' MINUTE)   AS window_start,
            TUMBLE_END(event_time,   INTERVAL '1' MINUTE)   AS window_end,
            event_type,
            device,
            country,
            COUNT(*)                                         AS event_count,
            COUNT(DISTINCT user_id)                          AS unique_users,
            SUM(COALESCE(amount, 0.0))                       AS total_amount,
            AVG(CASE WHEN amount > 0 THEN amount END)        AS avg_amount,
            COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) AS purchase_count
        FROM kafka_source
        GROUP BY
            TUMBLE(event_time, INTERVAL '1' MINUTE),
            event_type,
            device,
            country
    """)

    # ── Job B: 5-minute tumbling window ───────────────────────────────────────
    # Broader window — useful for slower-moving country/device level trends.
    statement_set.add_insert_sql("""
        INSERT INTO sink_5min
        SELECT
            TUMBLE_START(event_time, INTERVAL '5' MINUTE)   AS window_start,
            TUMBLE_END(event_time,   INTERVAL '5' MINUTE)   AS window_end,
            country,
            device,
            COUNT(*)                                         AS event_count,
            COUNT(DISTINCT user_id)                          AS unique_users,
            SUM(COALESCE(amount, 0.0))                       AS total_revenue
        FROM kafka_source
        GROUP BY
            TUMBLE(event_time, INTERVAL '5' MINUTE),
            country,
            device
    """)

    # Submit both INSERT jobs in a single Flink pipeline (shared Kafka read)
    statement_set.execute().wait()
    log.info("Window aggregation job submitted successfully.")


if __name__ == "__main__":
    main()
