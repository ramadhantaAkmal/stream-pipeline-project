"""
flink/jobs/job_anomaly_detection.py
─────────────────────────────────────
PyFlink Job 3: Purchase Spike Anomaly Detection
────────────────────────────────────────────────
Reads user-events from Kafka and detects anomalies in real time:

  1. HIGH-VALUE PURCHASE ALERT
     Any single purchase over $400 is flagged immediately.

  2. PURCHASE RATE SPIKE
     If a user makes 3+ purchases within a 2-minute sliding window,
     flag them as a potential bot or fraud signal.

  3. RAPID COUNTRY SWITCHING
     If the same user_id appears from 2+ different countries within
     5 minutes, flag as a suspicious session.

Alerts are written to:
  - ClickHouse (flink_alerts table) for persistence & dashboards
  - Kafka topic 'alerts' for downstream consumers (e.g. Slack notifier)

Run:
  docker exec -it flink-jobmanager \
    /opt/flink/bin/flink run \
    --python /opt/flink/jobs/job_anomaly_detection.py
"""

import os
import logging
from datetime import datetime

from pyflink.datastream import StreamExecutionEnvironment, RuntimeExecutionMode
from pyflink.datastream.functions import KeyedProcessFunction
from pyflink.datastream.state import ValueStateDescriptor, ListStateDescriptor
from pyflink.common.typeinfo import Types
from pyflink.common import Row
from pyflink.table import StreamTableEnvironment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ANOMALY JOB] %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
KAFKA_BOOTSTRAP    = os.getenv("KAFKA_BOOTSTRAP_SERVERS",  "kafka:9092")
KAFKA_TOPIC        = os.getenv("KAFKA_TOPIC",              "user-events")
KAFKA_ALERT_TOPIC  = os.getenv("KAFKA_ALERT_TOPIC",        "alerts")
KAFKA_GROUP        = os.getenv("KAFKA_GROUP_ID",           "flink-anomaly-group")
CLICKHOUSE_URL     = os.getenv("CLICKHOUSE_JDBC_URL",      "jdbc:clickhouse://clickhouse:8123/pipeline_db")
CLICKHOUSE_USER    = os.getenv("CLICKHOUSE_USER",          "admin")
CLICKHOUSE_PASS    = os.getenv("CLICKHOUSE_PASSWORD",      "admin123")

HIGH_VALUE_THRESHOLD      = float(os.getenv("HIGH_VALUE_THRESHOLD",  "400.0"))
RAPID_PURCHASE_COUNT      = int(os.getenv("RAPID_PURCHASE_COUNT",    "3"))
RAPID_PURCHASE_WINDOW_MS  = int(os.getenv("RAPID_PURCHASE_WINDOW_MS","120000"))  # 2 min
COUNTRY_SWITCH_WINDOW_MS  = int(os.getenv("COUNTRY_SWITCH_WINDOW_MS","300000"))  # 5 min


# ── Helper: build a standard alert dict ───────────────────────────────────────
def make_alert(alert_type: str, user_id: str, detail: str, severity: str) -> dict:
    return {
        "alert_type": alert_type,
        "user_id":    user_id,
        "detail":     detail,
        "severity":   severity,          # LOW | MEDIUM | HIGH | CRITICAL
        "detected_at": datetime.utcnow().isoformat() + "Z",
    }


# ── Keyed Process Function: Rapid Purchase Detection ─────────────────────────
class RapidPurchaseDetector(KeyedProcessFunction):
    """
    Keeps a count of purchases per user in a rolling 2-minute window.
    Emits an alert if the count crosses RAPID_PURCHASE_COUNT.
    Uses Flink state (persisted in checkpoints) — survives restarts.
    """

    def open(self, runtime_context):
        # Store list of purchase timestamps for this user
        self.purchase_times = runtime_context.get_list_state(
            ListStateDescriptor("purchase_timestamps", Types.LONG())
        )

    def process_element(self, event: Row, ctx: KeyedProcessFunction.Context):
        if event.event_type != "purchase":
            return

        now_ms = ctx.timestamp()
        cutoff  = now_ms - RAPID_PURCHASE_WINDOW_MS

        # Collect timestamps still within the window
        recent = [t for t in self.purchase_times.get() if t >= cutoff]
        recent.append(now_ms)
        self.purchase_times.update(recent)

        if len(recent) == RAPID_PURCHASE_COUNT:
            alert = make_alert(
                alert_type = "RAPID_PURCHASE",
                user_id    = event.user_id,
                detail     = (
                    f"{len(recent)} purchases in "
                    f"{RAPID_PURCHASE_WINDOW_MS // 1000}s window. "
                    f"Last amount: ${event.amount:.2f}"
                ),
                severity   = "HIGH",
            )
            yield Row(
                alert["alert_type"],
                alert["user_id"],
                alert["detail"],
                alert["severity"],
                alert["detected_at"],
            )

        # Register a cleanup timer so old state doesn't accumulate forever
        ctx.timer_service().register_event_time_timer(now_ms + RAPID_PURCHASE_WINDOW_MS)

    def on_timer(self, timestamp: int, ctx: KeyedProcessFunction.OnTimerContext):
        # Prune timestamps older than the window when the timer fires
        cutoff = timestamp - RAPID_PURCHASE_WINDOW_MS
        fresh  = [t for t in self.purchase_times.get() if t >= cutoff]
        if fresh:
            self.purchase_times.update(fresh)
        else:
            self.purchase_times.clear()


# ── Keyed Process Function: Country Switch Detection ──────────────────────────
class CountrySwitchDetector(KeyedProcessFunction):
    """
    Tracks distinct countries seen per user within a 5-minute window.
    If 2+ countries appear for the same user, emits a suspicious session alert.
    """

    def open(self, runtime_context):
        self.seen_countries = runtime_context.get_list_state(
            ListStateDescriptor("seen_countries", Types.STRING())
        )
        self.last_seen_ms = runtime_context.get_state(
            ValueStateDescriptor("last_seen_ms", Types.LONG())
        )

    def process_element(self, event: Row, ctx: KeyedProcessFunction.Context):
        if not event.country:
            return

        now_ms   = ctx.timestamp()
        last_ms  = self.last_seen_ms.value() or 0

        # Reset if outside the window
        if now_ms - last_ms > COUNTRY_SWITCH_WINDOW_MS:
            self.seen_countries.clear()

        self.last_seen_ms.update(now_ms)

        countries = list(self.seen_countries.get())
        if event.country not in countries:
            countries.append(event.country)
            self.seen_countries.update(countries)

        if len(countries) >= 2:
            alert = make_alert(
                alert_type = "COUNTRY_SWITCH",
                user_id    = event.user_id,
                detail     = (
                    f"User seen from {len(countries)} countries in "
                    f"{COUNTRY_SWITCH_WINDOW_MS // 60000} min: "
                    f"{', '.join(countries)}"
                ),
                severity   = "MEDIUM",
            )
            yield Row(
                alert["alert_type"],
                alert["user_id"],
                alert["detail"],
                alert["severity"],
                alert["detected_at"],
            )


def main():
    # ── Environment ───────────────────────────────────────────────────────────
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)
    env.set_parallelism(2)
    env.enable_checkpointing(30_000)
    t_env = StreamTableEnvironment.create(env)
    t_env.get_config().get_configuration().set_string(
        "pipeline.name", "flink-anomaly-detection"
    )

    # ── Kafka source (Table API) ──────────────────────────────────────────────
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

    # ── ClickHouse alerts sink ────────────────────────────────────────────────
    t_env.execute_sql(f"""
        CREATE TEMPORARY TABLE clickhouse_alerts (
            alert_type  STRING,
            user_id     STRING,
            detail      STRING,
            severity    STRING,
            detected_at STRING
        ) WITH (
            'connector'                  = 'jdbc',
            'url'                        = '{CLICKHOUSE_URL}',
            'table-name'                 = 'flink_alerts',
            'username'                   = '{CLICKHOUSE_USER}',
            'password'                   = '{CLICKHOUSE_PASS}',
            'sink.buffer-flush.max-rows' = '50',
            'sink.buffer-flush.interval' = '5s',
            'sink.max-retries'           = '3'
        )
    """)

    # ── Kafka alerts sink (for downstream consumers e.g. Slack notifier) ─────
    t_env.execute_sql(f"""
        CREATE TEMPORARY TABLE kafka_alerts (
            alert_type  STRING,
            user_id     STRING,
            detail      STRING,
            severity    STRING,
            detected_at STRING
        ) WITH (
            'connector'                    = 'kafka',
            'topic'                        = '{KAFKA_ALERT_TOPIC}',
            'properties.bootstrap.servers' = '{KAFKA_BOOTSTRAP}',
            'format'                       = 'json'
        )
    """)

    # Convert the Kafka table once so every detector receives the same events.
    event_table  = t_env.from_path("kafka_source")
    event_stream = t_env.to_data_stream(event_table).filter(
        lambda event: event.user_id is not None
    )

    alert_type_info = Types.ROW_NAMED(
        ["alert_type", "user_id", "detail", "severity", "detected_at"],
        [Types.STRING(), Types.STRING(), Types.STRING(), Types.STRING(), Types.STRING()]
    )

    # High-value purchases share the same source and sink path as stateful alerts.
    def make_high_value_alert(event: Row) -> Row:
        amount = event.amount or 0.0
        severity = "CRITICAL" if amount >= 450 else "HIGH"
        return Row(
            "HIGH_VALUE_PURCHASE",
            event.user_id,
            f"Purchase of ${amount:.2f} on {event.page} from {event.country}",
            severity,
            str(event.event_time),
        )

    high_value_alerts = (
        event_stream
        .filter(
            lambda event: event.event_type == "purchase"
            and event.amount is not None
            and event.amount >= HIGH_VALUE_THRESHOLD
        )
        .map(make_high_value_alert, output_type=alert_type_info)
    )

    rapid_purchase_alerts = (
        event_stream
        .filter(lambda r: r.event_type == "purchase")
        .key_by(lambda r: r.user_id)
        .process(RapidPurchaseDetector(), output_type=alert_type_info)
    )

    # Country switch detector — keyed by user_id
    country_switch_alerts = (
        event_stream
        .key_by(lambda r: r.user_id)
        .process(CountrySwitchDetector(), output_type=alert_type_info)
    )

    all_alerts = high_value_alerts.union(
        rapid_purchase_alerts, country_switch_alerts
    )
    alerts_table = t_env.from_data_stream(all_alerts)
    t_env.create_temporary_view("all_alerts", alerts_table)

    statement_set = t_env.create_statement_set()
    statement_set.add_insert_sql("""
        INSERT INTO clickhouse_alerts
        SELECT alert_type, user_id, detail, severity, detected_at
        FROM all_alerts
    """)
    statement_set.add_insert_sql("""
        INSERT INTO kafka_alerts
        SELECT alert_type, user_id, detail, severity, detected_at
        FROM all_alerts
    """)
    statement_set.execute().wait()

    log.info("Anomaly detection job submitted successfully.")


if __name__ == "__main__":
    main()
