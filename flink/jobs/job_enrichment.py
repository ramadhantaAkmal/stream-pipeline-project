"""
flink/jobs/job_enrichment.py
─────────────────────────────
PyFlink Job 1: Event Enrichment Pipeline
─────────────────────────────────────────
Reads raw user-events from Kafka, enriches each record with:
  - is_purchase flag
  - revenue_tier  (low / medium / high based on amount)
  - session_hour  (hour of day extracted from timestamp)
  - platform      (derived from device + browser combo)

Then writes the enriched stream into ClickHouse (flink_enriched_events).

Run inside the Flink SQL Client container:
  docker exec -it flink-jobmanager \
    /opt/flink/bin/flink run \
    --python /opt/flink/jobs/job_enrichment.py

Or submit via Flink Web UI at http://localhost:8082
"""

import os
import logging

from pyflink.datastream import StreamExecutionEnvironment, RuntimeExecutionMode
from pyflink.datastream.connectors.kafka import (
    KafkaSource,
    KafkaOffsetsInitializer,
)
from pyflink.datastream.formats.json import JsonRowDeserializationSchema
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.table import DataTypes, StreamTableEnvironment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ENRICHMENT JOB] %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
KAFKA_BOOTSTRAP    = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC        = os.getenv("KAFKA_TOPIC", "user-events")
KAFKA_GROUP        = os.getenv("KAFKA_GROUP_ID", "flink-enrichment-group")
CLICKHOUSE_URL     = os.getenv("CLICKHOUSE_JDBC_URL", "jdbc:clickhouse://clickhouse:8123/pipeline_db")
CLICKHOUSE_USER    = os.getenv("CLICKHOUSE_USER", "admin")
CLICKHOUSE_PASS    = os.getenv("CLICKHOUSE_PASSWORD", "admin123")


def get_revenue_tier(amount: float | None) -> str:
    """Bucket purchase amounts into tiers for easier dashboard filtering."""
    if not amount or amount == 0.0:
        return "none"
    if amount < 50.0:
        return "low"
    if amount < 200.0:
        return "medium"
    return "high"


def get_platform(device: str, browser: str) -> str:
    """Derive a combined platform label from device + browser."""
    device  = (device  or "").lower()
    browser = (browser or "").lower()
    if device == "mobile":
        return f"mobile-{browser}"
    if device == "tablet":
        return f"tablet-{browser}"
    return f"desktop-{browser}"


def main():
    # ── Flink environment setup ───────────────────────────────────────────────
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)
    env.set_parallelism(2)                     # match your TaskManager task slots
    env.enable_checkpointing(30_000)           # checkpoint every 30 seconds
    t_env = StreamTableEnvironment.create(env)

    # ── Kafka source table (defined in Flink Table API) ───────────────────────
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

    # ── ClickHouse sink table ─────────────────────────────────────────────────
    t_env.execute_sql(f"""
        CREATE TEMPORARY TABLE clickhouse_sink (
            event_id        STRING,
            user_id         STRING,
            event_type      STRING,
            page            STRING,
            product         STRING,
            amount          DOUBLE,
            country         STRING,
            city            STRING,
            device          STRING,
            browser         STRING,
            event_time      TIMESTAMP(3),
            is_purchase     BOOLEAN,
            amount_usd      DOUBLE,
            revenue_tier    STRING,
            session_hour    BIGINT,
            platform        STRING
        ) WITH (
            'connector'                     = 'jdbc',
            'url'                           = '{CLICKHOUSE_URL}',
            'table-name'                    = 'flink_enriched_events',
            'username'                      = '{CLICKHOUSE_USER}',
            'password'                      = '{CLICKHOUSE_PASS}',
            'sink.buffer-flush.max-rows'    = '500',
            'sink.buffer-flush.interval'    = '5s',
            'sink.max-retries'              = '3'
        )
    """)

    # ── Register Python enrichment functions as UDFs ──────────────────────────
    from pyflink.table.udf import udf

    revenue_tier_udf = udf(get_revenue_tier, result_type=DataTypes.STRING())
    platform_udf     = udf(get_platform,     result_type=DataTypes.STRING())

    t_env.create_temporary_function("get_revenue_tier", revenue_tier_udf)
    t_env.create_temporary_function("get_platform",     platform_udf)

    # ── Enrichment query ──────────────────────────────────────────────────────
    t_env.execute_sql("""
        INSERT INTO clickhouse_sink
        SELECT
            event_id,
            user_id,
            event_type,
            page,
            COALESCE(product, '')                   AS product,
            COALESCE(amount,  0.0)                  AS amount,
            country,
            city,
            device,
            browser,
            event_time,
            (event_type = 'purchase')               AS is_purchase,
            COALESCE(amount, 0.0)                   AS amount_usd,
            get_revenue_tier(amount)                AS revenue_tier,
            HOUR(event_time)                        AS session_hour,
            get_platform(device, browser)           AS platform
        FROM kafka_source
        WHERE event_id IS NOT NULL
    """).wait()

    log.info("Enrichment job submitted successfully.")


if __name__ == "__main__":
    main()
