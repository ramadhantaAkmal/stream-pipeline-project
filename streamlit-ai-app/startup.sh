#!/bin/bash
set -e

echo "🚀 Starting Streamlit Application..."

# Create data directory if it doesn't exist
mkdir -p /app/data

# ── Check if ClickHouse is reachable and the database exists ─────────────────
CLICKHOUSE_HOST="${CLICKHOUSE_HOST:-clickhouse}"
CLICKHOUSE_PORT="${CLICKHOUSE_PORT:-8123}"
CLICKHOUSE_DB="${CLICKHOUSE_DB:-pipeline_db}"
CLICKHOUSE_USER="${CLICKHOUSE_USER:-admin}"
CLICKHOUSE_PASSWORD="${CLICKHOUSE_PASSWORD:-admin123}"

echo "🔍 Checking ClickHouse connection at ${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}..."

# curl returns HTTP 200 with "1" if ClickHouse is up, non-zero exit code otherwise
if ! curl -sf \
    --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}" \
    "http://${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}/?query=SELECT+1" \
    > /dev/null 2>&1; then
    echo "⚠️  ClickHouse is not reachable at ${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}"
    echo "📋 Please ensure the ClickHouse container is running"
    echo "🔄 Run: docker compose up -d clickhouse"
    echo "📊 The application will start but queries may fail until ClickHouse is available"
else
    echo "✅ ClickHouse is reachable"

    # Check if the target database has any tables yet
    TABLE_COUNT=$(curl -sf \
        --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}" \
        "http://${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}/?query=SELECT+count()+FROM+system.tables+WHERE+database='${CLICKHOUSE_DB}'" \
        2>/dev/null || echo "0")

    if [ "${TABLE_COUNT}" = "0" ] || [ -z "${TABLE_COUNT}" ]; then
        echo "⚠️  Database '${CLICKHOUSE_DB}' exists but has no tables yet"
        echo "📋 Tables should be created by the init scripts on first ClickHouse startup"
        echo "🔄 Please ensure Flink jobs and the pipeline consumer have run successfully"
    else
        echo "✅ ClickHouse database '${CLICKHOUSE_DB}' is ready (${TABLE_COUNT} tables found)"
    fi
fi

echo "🔧 Starting metrics server..."
python3 /app/metrics_server.py &

echo "🌟 Starting Streamlit application..."
cd /app && streamlit run app.py --server.port=8501 --server.address=0.0.0.0