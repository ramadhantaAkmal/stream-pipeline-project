"""
consumer.py
───────────
Reads user-event messages from a Kafka topic and inserts
them in batches into ClickHouse for real-time analytics.

Batching strategy:
  - Accumulate up to BATCH_SIZE rows  OR
  - Flush after BATCH_TIMEOUT_SECONDS (whichever comes first)

This avoids hammering ClickHouse with one-row inserts, which
is the #1 beginner mistake when using ClickHouse.
"""

import json
import os
import time
import logging
from datetime import datetime

import clickhouse_connect
from confluent_kafka import Consumer, KafkaError, KafkaException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CONSUMER] %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC             = os.getenv("KAFKA_TOPIC", "user-events")
KAFKA_GROUP_ID          = os.getenv("KAFKA_GROUP_ID", "clickhouse-sink-group")

CLICKHOUSE_HOST     = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT     = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB       = os.getenv("CLICKHOUSE_DB", "pipeline_db")
CLICKHOUSE_USER     = os.getenv("CLICKHOUSE_USER", "admin")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "admin123")

BATCH_SIZE            = int(os.getenv("BATCH_SIZE", "100"))
BATCH_TIMEOUT_SECONDS = int(os.getenv("BATCH_TIMEOUT_SECONDS", "5"))

# ClickHouse column order must match the INSERT statement below
COLUMNS = [
    "event_id", "user_id", "event_type", "page",
    "product", "amount", "country", "city",
    "device", "browser", "timestamp",
]


def parse_message(raw_value: bytes) -> list | None:
    """Deserialise a Kafka message into an ordered row for ClickHouse."""
    try:
        data = json.loads(raw_value.decode("utf-8"))
        return [
            data.get("event_id", ""),
            data.get("user_id", ""),
            data.get("event_type", ""),
            data.get("page", ""),
            data.get("product") or "",          # NULL → empty string
            data.get("amount") or 0.0,          # NULL → 0.0
            data.get("country", ""),
            data.get("city", ""),
            data.get("device", ""),
            data.get("browser", ""),
            datetime.fromisoformat(
                data["timestamp"].replace("Z", "+00:00")
            ),
        ]
    except Exception as e:
        log.warning(f"Skipping malformed message: {e}")
        return None


def flush_batch(client, batch: list[list]) -> None:
    """Insert a batch of rows into ClickHouse."""
    if not batch:
        return
    try:
        client.insert(
            table=f"{CLICKHOUSE_DB}.user_events",
            data=batch,
            column_names=COLUMNS,
        )
        log.info(f"✓ Inserted {len(batch)} rows into ClickHouse")
    except Exception as e:
        log.error(f"ClickHouse insert failed: {e}")
        raise


def main():
    # ── Connect to ClickHouse ─────────────────────────────────────────────
    log.info(f"Connecting to ClickHouse at {CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}…")
    ch_client = clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        database=CLICKHOUSE_DB,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
    )
    log.info("ClickHouse connected ✓")

    # ── Connect to Kafka ──────────────────────────────────────────────────
    consumer = Consumer({
        "bootstrap.servers":        KAFKA_BOOTSTRAP_SERVERS,
        "group.id":                 KAFKA_GROUP_ID,
        "auto.offset.reset":        "earliest",   # replay from beginning on first run
        "enable.auto.commit":       False,         # manual commit after successful insert
        "max.poll.interval.ms":     300000,
        "session.timeout.ms":       30000,
    })
    consumer.subscribe([KAFKA_TOPIC])
    log.info(f"Subscribed to topic '{KAFKA_TOPIC}' with group '{KAFKA_GROUP_ID}'")

    batch: list[list] = []
    last_flush = time.time()
    total_processed = 0

    try:
        while True:
            # Poll with a short timeout so the flush timer still works
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                pass  # no new message, check flush timer below
            elif msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    log.debug("Reached end of partition")
                else:
                    raise KafkaException(msg.error())
            else:
                row = parse_message(msg.value())
                if row:
                    batch.append(row)

            # ── Flush if batch is full OR timeout elapsed ─────────────────
            elapsed = time.time() - last_flush
            should_flush = len(batch) >= BATCH_SIZE or (elapsed >= BATCH_TIMEOUT_SECONDS and batch)

            if should_flush:
                flush_batch(ch_client, batch)
                consumer.commit()           # commit only after successful insert
                total_processed += len(batch)
                log.info(f"Total rows processed: {total_processed}")
                batch = []
                last_flush = time.time()

    except KeyboardInterrupt:
        log.info("Shutting down consumer…")
        if batch:
            log.info(f"Flushing remaining {len(batch)} rows…")
            flush_batch(ch_client, batch)
            consumer.commit()
    finally:
        consumer.close()
        log.info("Consumer closed.")


if __name__ == "__main__":
    main()
