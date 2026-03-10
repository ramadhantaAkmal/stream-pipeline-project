from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import uvicorn
import logging
import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import clickhouse_connect
import time
import threading
import asyncio

# Import AI service
from ai_service import AIService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("acommerce-http-server")

# Configuration
CLICKHOUSE_HOST     = os.getenv("CLICKHOUSE_HOST",     "clickhouse")
CLICKHOUSE_PORT     = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB       = os.getenv("CLICKHOUSE_DB",       "pipeline_db")
CLICKHOUSE_USER     = os.getenv("CLICKHOUSE_USER",     "admin")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "admin123")
MAX_QUERY_ROWS      = int(os.getenv("MAX_QUERY_ROWS",  "1000"))

app = FastAPI(
    title="ACommerce Commerce Analytics API",
    description="HTTP API for e-commerce data analysis with AI capabilities",
    version="2.0.0"
)

# ── Timeout Middleware ────────────────────────────────────────────────────────
class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle request timeouts with intelligent timeout values
    based on the endpoint being accessed.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path.startswith("/ai/"):
            timeout = 360   # 6 minutes — model loading + inference
        elif path == "/query":
            timeout = 120   # 2 minutes for complex analytical queries
        else:
            timeout = 60    # 1 minute for standard endpoints

        try:
            return await asyncio.wait_for(call_next(request), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"⏱️ Request timeout after {timeout}s for {path}")

            if path.startswith("/ai/"):
                error_detail = {
                    "error": "AI request timeout",
                    "timeout_seconds": timeout,
                    "endpoint": path,
                    "troubleshooting": [
                        "Ollama may be loading the model for the first time (can take 2-3 minutes)",
                        "Check if Ollama is running: docker logs ollama",
                        "Verify Ollama is responding: docker exec ollama ollama list",
                        "Consider using a smaller/faster model if timeouts persist"
                    ]
                }
            else:
                error_detail = {
                    "error": "Request timeout",
                    "timeout_seconds": timeout,
                    "endpoint": path
                }

            return JSONResponse(status_code=504, content=error_detail)

        except Exception as e:
            logger.error(f"❌ Middleware error for {path}: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"error": f"Internal server error: {str(e)}"}
            )

app.add_middleware(TimeoutMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Database Manager ──────────────────────────────────────────────────────────
class DatabaseManager:
    """Thread-safe ClickHouse connection manager."""

    def __init__(self):
        self._lock = threading.RLock()
        self._client: clickhouse_connect.driver.Client | None = None
        self._connect()

    def _connect(self, max_retries: int = 5):
        """Establish connection to ClickHouse with retry logic."""
        last_error = None
        for attempt in range(max_retries):
            try:
                self._client = clickhouse_connect.get_client(
                    host=CLICKHOUSE_HOST,
                    port=CLICKHOUSE_PORT,
                    database=CLICKHOUSE_DB,
                    username=CLICKHOUSE_USER,
                    password=CLICKHOUSE_PASSWORD,
                    connect_timeout=10,
                    send_receive_timeout=120,
                )
                # Verify connection
                self._client.command("SELECT 1")
                logger.info(f"✅ ClickHouse connected at {CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/{CLICKHOUSE_DB}")
                return
            except Exception as e:
                last_error = e
                wait = 0.5 * (2 ** attempt)
                logger.warning(f"ClickHouse connection attempt {attempt + 1}/{max_retries} failed, retrying in {wait}s: {e}")
                time.sleep(wait)

        logger.error(f"❌ ClickHouse connection failed after {max_retries} attempts: {last_error}")
        raise ConnectionError(f"Cannot connect to ClickHouse: {last_error}")

    def _ensure_connection(self):
        """Reconnect if the client has been lost."""
        try:
            self._client.command("SELECT 1")
        except Exception:
            logger.warning("ClickHouse connection lost, reconnecting…")
            self._connect()

    def execute_query(self, query: str, limit: Optional[int] = None) -> Dict[str, Any]:
        """Execute a read-only SQL query and return structured results."""
        with self._lock:
            try:
                self._ensure_connection()

                # Append LIMIT only for SELECT/WITH queries that don't already have one
                query_upper = query.upper().strip()
                if limit and "LIMIT" not in query_upper:
                    if query_upper.startswith(("SELECT", "WITH")):
                        query = f"{query.rstrip(';')} LIMIT {limit}"

                logger.info(f"Executing query: {query[:300]}…")
                start_time = datetime.now()

                result = self._client.query(query)

                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                columns = list(result.column_names)

                rows = []
                for row in result.result_rows:
                    row_dict = {}
                    for i, value in enumerate(row):
                        col = columns[i]
                        # Normalise non-JSON-serialisable types
                        if isinstance(value, datetime):
                            row_dict[col] = value.isoformat()
                        elif value is None:
                            row_dict[col] = None
                        else:
                            row_dict[col] = value
                    rows.append(row_dict)

                return {
                    "columns":          columns,
                    "rows":             rows,
                    "row_count":        len(rows),
                    "execution_time_ms": round(execution_time, 2),
                    "query":            query,
                }

            except Exception as e:
                logger.error(f"Query execution failed: {e}")
                raise Exception(f"Query execution failed: {str(e)}")

    def list_tables(self) -> List[str]:
        """List all user tables in the configured ClickHouse database."""
        try:
            # ClickHouse system.tables is the equivalent of information_schema.tables
            tables_query = f"""
            SELECT
                database || '.' || name AS full_name
            FROM system.tables
            WHERE database = '{CLICKHOUSE_DB}'
              AND engine NOT IN ('View', 'MaterializedView', 'Dictionary', 'Memory')
            ORDER BY database, name
            """
            result = self.execute_query(tables_query)
            return [row["full_name"] for row in result["rows"]]
        except Exception as e:
            logger.warning(f"Failed to list tables: {e}")
            return []


# ── Singleton instances ───────────────────────────────────────────────────────
db_manager = DatabaseManager()
ai_service = AIService()

# Metrics
request_count  = 0
query_count    = 0
error_count    = 0
last_query_time = 0.0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Health check endpoint."""
    global request_count
    request_count += 1
    return {
        "service":    "acommerce Commerce Analytics API",
        "status":     "healthy",
        "version":    "2.0.0",
        "database":   f"{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/{CLICKHOUSE_DB}",
        "ai_enabled": ai_service.is_available(),
        "timestamp":  datetime.now().isoformat(),
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    global request_count, query_count, error_count, last_query_time

    try:
        tables      = db_manager.list_tables()
        db_connected = 1
        table_count  = len(tables)
    except Exception:
        db_connected = 0
        table_count  = 0

    ai_available = 1 if ai_service.is_available() else 0

    metrics_text = f"""# HELP mcp_requests_total Total number of HTTP requests
                        # TYPE mcp_requests_total counter
                        mcp_requests_total {request_count}

                        # HELP mcp_queries_total Total number of database queries
                        # TYPE mcp_queries_total counter
                        mcp_queries_total {query_count}

                        # HELP mcp_errors_total Total number of errors
                        # TYPE mcp_errors_total counter
                        mcp_errors_total {error_count}

                        # HELP mcp_database_connected Database connection status
                        # TYPE mcp_database_connected gauge
                        mcp_database_connected {db_connected}

                        # HELP mcp_ai_available AI service availability
                        # TYPE mcp_ai_available gauge
                        mcp_ai_available {ai_available}

                        # HELP mcp_tables_count Number of database tables
                        # TYPE mcp_tables_count gauge
                        mcp_tables_count {table_count}

                        # HELP mcp_last_query_duration_seconds Duration of last query
                        # TYPE mcp_last_query_duration_seconds gauge
                        mcp_last_query_duration_seconds {last_query_time}

                        # HELP mcp_uptime_seconds Service uptime
                        # TYPE mcp_uptime_seconds counter
                        mcp_uptime_seconds {time.time()}
                    """
    return Response(content=metrics_text, media_type="text/plain")


@app.get("/health")
async def health_check():
    """Detailed health check."""
    try:
        tables = db_manager.list_tables()
        return {
            "status":             "healthy",
            "database_connected": True,
            "ai_available":       ai_service.is_available(),
            "tables_available":   len(tables),
            "timestamp":          datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "status":             "unhealthy",
            "database_connected": False,
            "ai_available":       ai_service.is_available(),
            "error":              str(e),
            "timestamp":          datetime.now().isoformat(),
        }


@app.get("/tables")
async def list_tables():
    """List all available database tables."""
    try:
        tables = db_manager.list_tables()
        return {
            "tables":    tables,
            "count":     len(tables),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query")
async def execute_query(request: Dict[str, Any]):
    """Execute a read-only SQL query against ClickHouse."""
    global query_count, error_count, last_query_time

    try:
        query = request.get("query", "").strip()
        limit = request.get("limit", 100)

        if not query:
            error_count += 1
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        # Security: block write operations
        dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "INSERT", "UPDATE", "ALTER", "CREATE"]
        query_upper = query.upper()
        for keyword in dangerous_keywords:
            if keyword in query_upper:
                error_count += 1
                raise HTTPException(
                    status_code=400,
                    detail=f"Query contains dangerous operation: {keyword}"
                )

        start_time = time.time()
        result = db_manager.execute_query(query, limit)
        last_query_time = time.time() - start_time
        query_count += 1

        return result

    except HTTPException:
        raise
    except Exception as e:
        error_count += 1
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/summary")
async def get_executive_summary():
    """Get executive dashboard summary from ClickHouse."""
    try:
        try:
            # ClickHouse uses concat() instead of || for older versions;
            # both work in modern ClickHouse (24+). Using concat() for safety.
            metrics_query = f"""
            SELECT
                uniq(customer_fk)                          AS total_customers,
                sum(total_orders)                          AS total_orders,
                round(sum(total_revenue), 2)               AS total_revenue,
                round(avg(avg_order_value), 2)             AS avg_order_value,
                max(concat(
                    toString(order_year), '-',
                    leftPad(toString(order_month), 2, '0')
                ))                                         AS latest_period
            FROM {CLICKHOUSE_DB}.fct_monthly_revenue
            """
            metrics = db_manager.execute_query(metrics_query)
            return {
                "key_metrics": metrics["rows"][0] if metrics["rows"] else {},
                "status":      "success",
                "timestamp":   datetime.now().isoformat(),
            }

        except Exception:
            return {
                "key_metrics": {
                    "total_customers":  0,
                    "total_orders":     0,
                    "total_revenue":    0,
                    "avg_order_value":  0,
                    "latest_period":    None,
                },
                "status":    "no_data",
                "message":   "Database is empty or tables not yet created",
                "timestamp": datetime.now().isoformat(),
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── AI Endpoints ──────────────────────────────────────────────────────────────

@app.get("/ai/status")
async def ai_status():
    """Check AI service availability."""
    return {
        "ai_available": ai_service.is_available(),
        "ollama_url":   ai_service.ollama_url,
        "model":        ai_service.model,
        "timestamp":    datetime.now().isoformat(),
    }


def _get_schema_context(max_tables: int = 10) -> str:
    """Helper: fetch schema context from ClickHouse for the AI prompt."""
    try:
        tables = db_manager.list_tables()
        main_tables = tables[:max_tables]
        schema_info = []

        for full_table in main_tables:
            db_name, table_name = full_table.split(".", 1)
            try:
                # ClickHouse system.columns is the canonical schema source
                schema_query = f"""
                SELECT name AS column_name, type AS data_type
                FROM system.columns
                WHERE database = '{db_name}'
                  AND table = '{table_name}'
                ORDER BY position
                LIMIT 20
                """
                schema_result = db_manager.execute_query(schema_query)
                if schema_result["rows"]:
                    cols = [
                        f"{r['column_name']} ({r['data_type']})"
                        for r in schema_result["rows"]
                    ]
                    schema_info.append(f"{full_table}: {', '.join(cols)}")
            except Exception:
                continue

        return "\n".join(schema_info) or "Schema information unavailable"

    except Exception as e:
        logger.warning(f"Failed to get schema context: {e}")
        return "Schema information unavailable"


@app.post("/ai/generate-sql")
async def generate_sql(request: Dict[str, Any]):
    """Generate SQL from a natural language question using AI."""
    global error_count

    try:
        question       = request.get("question", "").strip()
        include_schema = request.get("include_schema", True)

        if not question:
            error_count += 1
            raise HTTPException(status_code=400, detail="Question cannot be empty")

        if not ai_service.is_available():
            error_count += 1
            raise HTTPException(status_code=503, detail="AI service (Ollama) is not available.")

        schema_context = _get_schema_context() if include_schema else ""

        logger.info(f"Generating SQL for question: {question}")
        sql = ai_service.generate_sql(question, schema_context)

        if not sql:
            error_count += 1
            raise HTTPException(status_code=500, detail="Failed to generate SQL query.")

        return {
            "question":     question,
            "generated_sql": sql,
            "schema_used":  bool(schema_context),
            "timestamp":    datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        error_count += 1
        logger.error(f"SQL generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai/analyze-data")
async def analyze_data(request: Dict[str, Any]):
    """Analyze data and generate business insights using AI."""
    global error_count

    try:
        question = request.get("question", "").strip()
        data     = request.get("data", None)

        if not question:
            error_count += 1
            raise HTTPException(status_code=400, detail="Question cannot be empty")

        if not ai_service.is_available():
            error_count += 1
            raise HTTPException(status_code=503, detail="AI service (Ollama) is not available.")

        data_str = json.dumps(data, indent=2) if isinstance(data, dict) else str(data or "")

        logger.info(f"Generating business analysis for: {question}")
        analysis = ai_service.analyze_business_data(data_str, question)

        if not analysis:
            error_count += 1
            raise HTTPException(status_code=500, detail="Failed to generate analysis.")

        return {
            "question":      question,
            "analysis":      analysis,
            "data_analyzed": bool(data),
            "timestamp":     datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        error_count += 1
        logger.error(f"Data analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai/ask")
async def ask_ai(request: Dict[str, Any]):
    """
    Complete AI-powered question answering pipeline:
      1. Generate SQL from the question using Ollama
      2. Execute the query against ClickHouse
      3. Analyse results with AI
      4. Return comprehensive insights
    """
    global query_count, error_count

    try:
        question             = request.get("question", "").strip()
        execute_query_flag   = request.get("execute_query", True)
        analyze_results_flag = request.get("analyze_results", True)

        if not question:
            error_count += 1
            raise HTTPException(status_code=400, detail="Question cannot be empty")

        if not ai_service.is_available():
            error_count += 1
            raise HTTPException(status_code=503, detail="AI service (Ollama) is not available.")

        logger.info(f"📝 Processing AI question: {question}")

        response = {
            "question":  question,
            "timestamp": datetime.now().isoformat(),
            "success":   True,
        }

        # Step 1 – Schema context
        schema_context = _get_schema_context()

        # Step 2 – Generate SQL
        logger.info("🤖 Generating SQL query with AI…")
        sql = ai_service.generate_sql(question, schema_context)

        if not sql:
            error_count += 1
            raise HTTPException(status_code=500, detail="Failed to generate SQL query.")

        logger.info(f"✅ Generated SQL: {sql[:100]}…")
        response["generated_sql"] = sql
        response["sql_generated"] = True

        # Step 3 – Execute query
        if execute_query_flag:
            try:
                dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "INSERT", "UPDATE", "ALTER", "CREATE"]
                for keyword in dangerous_keywords:
                    if keyword in sql.upper():
                        error_count += 1
                        raise HTTPException(
                            status_code=400,
                            detail=f"Generated SQL contains dangerous operation: {keyword}"
                        )

                query_result = db_manager.execute_query(sql, limit=100)
                query_count += 1
                logger.info(f"✅ Query executed: {query_result['row_count']} rows in {query_result['execution_time_ms']}ms")

                response["query_result"]    = query_result
                response["query_executed"]  = True
                response["execution_time_ms"] = query_result.get("execution_time_ms", 0)

                # Step 4 – Analyse results
                if analyze_results_flag and query_result["rows"]:
                    logger.info("🧠 Generating AI analysis…")
                    result_summary = {
                        "row_count":   query_result["row_count"],
                        "columns":     query_result["columns"],
                        "sample_rows": query_result["rows"][:10],
                    }

                    # Add basic numeric stats
                    numeric_stats = {}
                    for col in query_result["columns"]:
                        values = [
                            r.get(col) for r in query_result["rows"]
                            if isinstance(r.get(col), (int, float))
                        ]
                        if values:
                            numeric_stats[col] = {
                                "min": min(values),
                                "max": max(values),
                                "avg": sum(values) / len(values),
                            }
                    if numeric_stats:
                        result_summary["numeric_statistics"] = numeric_stats

                    data_str = json.dumps(result_summary, indent=2, default=str)
                    analysis = ai_service.analyze_business_data(data_str, question)

                    if analysis:
                        response["ai_analysis"]        = analysis
                        response["analysis_generated"] = True
                    else:
                        response["analysis_generated"] = False
                        response["analysis_error"]     = "AI analysis could not be generated."

                elif analyze_results_flag and not query_result["rows"]:
                    response["analysis_generated"] = False
                    response["analysis_error"]     = "No data returned by the query to analyze"

            except HTTPException:
                raise
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Query execution failed: {e}", exc_info=True)
                response["query_executed"] = False
                response["query_error"]    = str(e)
                response["success"]        = False
        else:
            response["query_executed"] = False

        return response

    except HTTPException:
        raise
    except Exception as e:
        error_count += 1
        logger.error(f"❌ AI question answering failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == "__main__":
    logger.info("🚀 Starting acommerce Commerce HTTP API Server with AI")
    logger.info(f"📊 ClickHouse: {CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/{CLICKHOUSE_DB}")
    logger.info(f"🔧 Max query rows: {MAX_QUERY_ROWS}")
    logger.info(f"🤖 AI Service: {'✅ Available' if ai_service.is_available() else '❌ Not Available'}")

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=5000,
        log_level="info",
        timeout_keep_alive=300,
        timeout_graceful_shutdown=30,
        limit_concurrency=100,
    )
    server = uvicorn.Server(config)
    logger.info("🌐 Server listening on http://0.0.0.0:5000")
    server.run()