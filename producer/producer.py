"""
producer.py
───────────
Generates fake user-event data with Faker and publishes
JSON messages to a Kafka topic at a configurable rate.

Event schema:
  event_id       – UUID
  user_id        – UUID
  event_type     – page_view | click | purchase | signup | logout
  page           – URL path
  product        – product name (nullable)
  amount         – purchase amount in USD (nullable)
  country        – ISO country code
  device         – desktop | mobile | tablet
  browser        – Chrome | Firefox | Safari | Edge
  timestamp      – ISO-8601 UTC
"""

import json
import os
import time
import uuid
import random
import logging
from datetime import datetime, timezone

from faker import Faker
from confluent_kafka import Producer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PRODUCER] %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# ── Config (from environment / .env) ─────────────────────────────────────────
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC             = os.getenv("KAFKA_TOPIC", "user-events")
EVENTS_PER_SECOND       = float(os.getenv("EVENTS_PER_SECOND", "5"))

fake = Faker()

EVENT_TYPES = ["page_view", "click", "purchase", "signup", "logout"]
DEVICES     = ["desktop", "mobile", "tablet"]
BROWSERS    = ["Chrome", "Firefox", "Safari", "Edge"]
PAGES       = [
    "/home", "/products", "/about", "/contact",
    "/cart", "/checkout", "/profile", "/blog",
    "/search", "/categories",
]


def generate_event() -> dict:
    event_type = random.choice(EVENT_TYPES)
    is_purchase = event_type == "purchase"

    return {
        "event_id":   str(uuid.uuid4()),
        "user_id":    str(uuid.uuid4()),
        "event_type": event_type,
        "page":       random.choice(PAGES),
        "product":    fake.bs() if is_purchase else None,
        "amount":     round(random.uniform(5.0, 500.0), 2) if is_purchase else None,
        "country":    fake.country_code(),
        "city":       fake.city(),
        "device":     random.choice(DEVICES),
        "browser":    random.choice(BROWSERS),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }


def delivery_report(err, msg):
    """Callback fired by Kafka after a message is acknowledged."""
    if err:
        log.error(f"Delivery failed for event: {err}")
    else:
        log.debug(f"Delivered → topic={msg.topic()} partition={msg.partition()} offset={msg.offset()}")


def main():
    producer = Producer({
        "bootstrap.servers":   KAFKA_BOOTSTRAP_SERVERS,
        "acks":                "all",          # wait for full replication
        "retries":             5,
        "retry.backoff.ms":    500,
        "linger.ms":           10,             # batch messages for 10ms before send
        "batch.size":          16384,          # batch up to 16 KB
        "compression.type":    "snappy",       # compress for scale
    })

    sleep_interval = 1.0 / EVENTS_PER_SECOND
    sent = 0

    log.info(f"Starting producer → topic='{KAFKA_TOPIC}' @ {EVENTS_PER_SECOND} events/s")

    try:
        while True:
            event = generate_event()
            payload = json.dumps(event).encode("utf-8")

            producer.produce(
                topic=KAFKA_TOPIC,
                key=event["user_id"].encode("utf-8"),  # partition by user
                value=payload,
                callback=delivery_report,
            )

            # Poll to fire delivery callbacks without blocking
            producer.poll(0)

            sent += 1
            if sent % 100 == 0:
                log.info(f"Published {sent} events so far…")

            time.sleep(sleep_interval)

    except KeyboardInterrupt:
        log.info("Shutting down producer…")
    finally:
        producer.flush()
        log.info(f"Done. Total events published: {sent}")


if __name__ == "__main__":
    main()
