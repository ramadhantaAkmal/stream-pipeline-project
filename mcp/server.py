#!/usr/bin/env python3
"""
ACommerce - MCP Server
=================================
Model Context Protocol server providing tools, resources, and prompts
for e-commerce analytics.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional
from datetime import datetime
import clickhouse_connect

# MCP SDK imports
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel,
    CallToolRequest,
    ListResourcesRequest,
    ListToolsRequest,
    ReadResourceRequest,
    GetPromptRequest,
    ListPromptsRequest,
    Prompt,
    PromptArgument,
    PromptMessage,
    Role,
)
from mcp.server.stdio import stdio_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("acommerce-mcp-server")

# Configuration
CLICKHOUSE_HOST     = os.getenv("CLICKHOUSE_HOST",     "clickhouse")
CLICKHOUSE_PORT     = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB       = os.getenv("CLICKHOUSE_DB",       "pipeline_db")
CLICKHOUSE_USER     = os.getenv("CLICKHOUSE_USER",     "admin")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "admin123")
MAX_QUERY_ROWS      = int(os.getenv("MAX_QUERY_ROWS",  "1000"))


# ── Database Manager ──────────────────────────────────────────────────────────
class DatabaseManager:
    """ClickHouse connection manager."""

    def __init__(self):
        self._client: clickhouse_connect.driver.Client | None = None
        self._connect()

    def _connect(self, max_retries: int = 5):
        import time
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
                self._client.command("SELECT 1")
                logger.info(f"✅ ClickHouse connected at {CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/{CLICKHOUSE_DB}")
                return
            except Exception as e:
                last_error = e
                wait = 0.5 * (2 ** attempt)
                logger.warning(f"Connection attempt {attempt + 1}/{max_retries} failed, retrying in {wait}s: {e}")
                time.sleep(wait)
        raise ConnectionError(f"Cannot connect to ClickHouse: {last_error}")

    def execute_query(self, query: str, limit: Optional[int] = None) -> Dict[str, Any]:
        """Execute a SQL query and return structured results."""
        try:
            query_upper = query.upper().strip()
            if limit and "LIMIT" not in query_upper:
                if query_upper.startswith(("SELECT", "WITH")):
                    query = f"{query.rstrip(';')} LIMIT {limit}"

            start_time = datetime.now()
            result     = self._client.query(query)
            exec_ms    = (datetime.now() - start_time).total_seconds() * 1000
            columns    = list(result.column_names)

            rows = []
            for row in result.result_rows:
                row_dict = {}
                for i, value in enumerate(row):
                    col = columns[i]
                    row_dict[col] = value.isoformat() if isinstance(value, datetime) else value
                rows.append(row_dict)

            return {
                "columns":           columns,
                "rows":              rows,
                "row_count":         len(rows),
                "execution_time_ms": round(exec_ms, 2),
                "query":             query,
            }

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise Exception(f"Query execution failed: {str(e)}")

    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Get column schema for a table using ClickHouse system.columns."""
        try:
            # Support both 'db.table' and plain 'table' formats
            if "." in table_name:
                db_name, tbl = table_name.split(".", 1)
            else:
                db_name, tbl = CLICKHOUSE_DB, table_name

            schema_query = f"""
            SELECT
                name             AS column_name,
                type             AS data_type,
                is_in_primary_key AS is_primary_key,
                default_expression AS column_default
            FROM system.columns
            WHERE database = '{db_name}'
              AND table    = '{tbl}'
            ORDER BY position
            """
            return self.execute_query(schema_query)
        except Exception as e:
            logger.error(f"Schema query failed for {table_name}: {e}")
            raise

    def list_tables(self) -> List[str]:
        """List all user tables in the configured ClickHouse database."""
        try:
            tables_query = f"""
            SELECT database || '.' || name AS full_name
            FROM system.tables
            WHERE database = '{CLICKHOUSE_DB}'
              AND engine NOT IN ('View', 'MaterializedView', 'Dictionary', 'Memory')
            ORDER BY database, name
            """
            result = self.execute_query(tables_query)
            return [row["full_name"] for row in result["rows"]]
        except Exception as e:
            logger.error(f"Failed to list tables: {e}")
            return []


# ── Business Analytics ────────────────────────────────────────────────────────
class BusinessAnalytics:
    """Business analytics and insights generator backed by ClickHouse."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def get_most_visited_pages(self) -> Dict[str, Any]:
        try:
            query = f"""
            SELECT
                page,
                event_type,
                COUNT(*) AS event_count
            FROM {CLICKHOUSE_DB}.user_events
            GROUP BY page
            ORDER BY event_count DESC;
            """

            result = self.db.execute_query(query)

            return {
                "top_visited_page": result["rows"][0] if  result["rows"] else {},
                "generated_at":   datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Executive summary generation failed: {e}")
            raise
    
    def get_traffic_revenue_trend(self) -> Dict[str, Any]:
        """Generate executive summary with key metrics."""
        try:
            query = f"""
            SELECT
                period,
                SUM(event_count) AS total_events,
                SUM(total_amount) AS total_revenue
            FROM
            (
                SELECT
                    'last_5_min' AS period,
                    event_count,
                    total_amount
                FROM {CLICKHOUSE_DB}.flink_window_counts
                WHERE window_start >= now() - INTERVAL 5 MINUTE

                UNION ALL

                SELECT
                    'prev_5_min' AS period,
                    event_count,
                    total_amount
                FROM {CLICKHOUSE_DB}.flink_window_counts
                WHERE window_start >= now() - INTERVAL 10 MINUTE
                AND window_start < now() - INTERVAL 5 MINUTE
            )
            GROUP BY period;
            """

            trends = self.db.execute_query(query)

            return {
                "trends":    trends["rows"][0] if trends["rows"] else {},
                "generated_at":   datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Traffic-Revenue trend generation failed: {e}")
            raise
        
    def get_conversion_rate(self) -> Dict[str, Any]:
        try:
            query = f"""
            SELECT
                COUNT(*) AS total_events,
                COUNTIf(is_purchase = 1) AS total_purchases,
                SUM(amount_usd) AS revenue,
                COUNTIf(is_purchase = 1) * 1.0 / COUNT(*) AS conversion_rate
            FROM {CLICKHOUSE_DB}.flink_enriched_events
            WHERE event_time >= now() - INTERVAL 15 MINUTE;
            """

            result = self.db.execute_query(query)

            return {
                "conversion_rate":result["rows"][0] if  result["rows"] else {},
                "generated_at":   datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Executive summary generation failed: {e}")
            raise
        
    # def generate_business_insights(self, focus_area: str = "general") -> Dict[str, Any]:
    #     """Generate business insights based on focus area."""
    #     insights = []

    #     try:
    #         if focus_area in ["general", "revenue"]:
    #             insights.extend(self._analyze_revenue_patterns())
    #         if focus_area in ["general", "customers"]:
    #             insights.extend(self._analyze_customer_patterns())
    #         if focus_area in ["general", "products"]:
    #             insights.extend(self._analyze_product_patterns())

    #         return {
    #             "insights":     insights,
    #             "focus_area":   focus_area,
    #             "generated_at": datetime.now().isoformat(),
    #         }

    #     except Exception as e:
    #         logger.error(f"Business insights generation failed: {e}")
    #         raise

    # def _analyze_revenue_patterns(self) -> List[Dict[str, Any]]:
    #     """Analyse revenue patterns and trends."""
    #     insights = []
    #     try:
    #         # ClickHouse window functions work the same as standard SQL
    #         growth_query = f"""
    #         WITH monthly_revenue AS (
    #             SELECT
    #                 order_year,
    #                 order_month,
    #                 sum(total_revenue) AS revenue
    #             FROM {CLICKHOUSE_DB}.fct_monthly_revenue
    #             GROUP BY order_year, order_month
    #             ORDER BY order_year, order_month
    #         ),
    #         growth_calc AS (
    #             SELECT
    #                 *,
    #                 lagInFrame(revenue) OVER (ORDER BY order_year, order_month) AS prev_revenue
    #             FROM monthly_revenue
    #         )
    #         SELECT
    #             concat(
    #                 toString(order_year), '-',
    #                 leftPad(toString(order_month), 2, '0')
    #             )                                               AS period,
    #             revenue,
    #             round(
    #                 (revenue - prev_revenue) / prev_revenue * 100, 2
    #             )                                               AS growth_rate
    #         FROM growth_calc
    #         WHERE prev_revenue IS NOT NULL
    #         ORDER BY order_year DESC, order_month DESC
    #         LIMIT 6
    #         """
    #         growth_data = self.db.execute_query(growth_query)

    #         if growth_data["rows"]:
    #             latest_growth = growth_data["rows"][0]["growth_rate"]
    #             avg_growth    = sum(r["growth_rate"] for r in growth_data["rows"]) / len(growth_data["rows"])

    #             if latest_growth and latest_growth > avg_growth * 1.2:
    #                 insights.append({
    #                     "type":        "revenue_acceleration",
    #                     "title":       "Revenue Growth Accelerating",
    #                     "description": f"Latest month shows {latest_growth}% growth vs {avg_growth:.1f}% average",
    #                     "confidence":  0.85,
    #                     "recommendations": [
    #                         "Investigate successful marketing channels",
    #                         "Scale winning strategies",
    #                         "Prepare inventory for increased demand",
    #                     ],
    #                 })
    #             elif latest_growth and latest_growth < avg_growth * 0.5:
    #                 insights.append({
    #                     "type":        "revenue_deceleration",
    #                     "title":       "Revenue Growth Slowing",
    #                     "description": f"Latest month shows {latest_growth}% growth vs {avg_growth:.1f}% average",
    #                     "confidence":  0.80,
    #                     "recommendations": [
    #                         "Review marketing effectiveness",
    #                         "Analyse customer acquisition costs",
    #                         "Consider promotional campaigns",
    #                     ],
    #                 })

    #     except Exception as e:
    #         logger.error(f"Revenue pattern analysis failed: {e}")

    #     return insights

    # def _analyze_customer_patterns(self) -> List[Dict[str, Any]]:
    #     """Analyse customer behaviour patterns."""
    #     insights = []
    #     try:
    #         at_risk_query = f"""
    #         SELECT
    #             count()                                AS at_risk_count,
    #             round(avg(lifetime_revenue), 2)        AS avg_value,
    #             round(sum(lifetime_revenue), 2)        AS total_at_risk_value
    #         FROM {CLICKHOUSE_DB}.dim_customers
    #         WHERE customer_segment = 'At Risk'
    #         """
    #         at_risk_data = self.db.execute_query(at_risk_query)

    #         if at_risk_data["rows"] and at_risk_data["rows"][0]["at_risk_count"] > 0:
    #             info = at_risk_data["rows"][0]
    #             insights.append({
    #                 "type":        "customer_at_risk",
    #                 "title":       "High-Value Customers At Risk",
    #                 "description": (
    #                     f"{info['at_risk_count']} customers at risk representing "
    #                     f"${info['total_at_risk_value']:,.2f} in potential lost revenue"
    #                 ),
    #                 "confidence":  0.90,
    #                 "recommendations": [
    #                     "Launch targeted win-back campaigns",
    #                     "Offer personalised incentives",
    #                     "Conduct customer satisfaction surveys",
    #                 ],
    #             })

    #     except Exception as e:
    #         logger.error(f"Customer pattern analysis failed: {e}")

    #     return insights

    # def _analyze_product_patterns(self) -> List[Dict[str, Any]]:
    #     """Analyse product performance patterns."""
    #     insights = []
    #     try:
    #         declining_query = f"""
    #         SELECT
    #             count()                                    AS low_performing_count,
    #             round(sum(total_revenue), 2)               AS low_performing_revenue,
    #             round(avg(days_since_last_sale), 2)        AS avg_days_since_sale
    #         FROM {CLICKHOUSE_DB}.fct_product_performance
    #         WHERE performance_tier = 'Other'
    #           AND days_since_last_sale > 30
    #         """
    #         declining_data = self.db.execute_query(declining_query)

    #         if declining_data["rows"] and declining_data["rows"][0]["low_performing_count"] > 0:
    #             info = declining_data["rows"][0]
    #             insights.append({
    #                 "type":        "product_low_performance",
    #                 "title":       "Low Performing Products Need Attention",
    #                 "description": (
    #                     f"{info['low_performing_count']} products with no recent sales "
    #                     f"(avg {info['avg_days_since_sale']:.0f} days), representing "
    #                     f"${info['low_performing_revenue']:,.2f} in revenue"
    #                 ),
    #                 "confidence": 0.85,
    #                 "recommendations": [
    #                     "Review pricing strategy for low-performing products",
    #                     "Consider promotional campaigns to boost sales",
    #                     "Evaluate inventory levels and discontinuation candidates",
    #                     "Analyse customer feedback for these products",
    #                 ],
    #             })

    #     except Exception as e:
    #         logger.error(f"Product pattern analysis failed: {e}")

    #     return insights


# ── Initialise services ───────────────────────────────────────────────────────
db_manager      = DatabaseManager()
analytics_engine = BusinessAnalytics(db_manager)
server           = Server("commerce-analysis")


# ── MCP Tools ─────────────────────────────────────────────────────────────────
@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    return [
        Tool(
            name="execute_sql_query",
            description="Execute SQL queries against the ClickHouse e-commerce data warehouse",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SQL query to execute"},
                    "limit": {"type": "integer", "description": "Maximum rows to return", "default": 100},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_table_schema",
            description="Get schema information for a specific ClickHouse table",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Table name (e.g. 'pipeline_db.dim_customers')"},
                },
                "required": ["table_name"],
            },
        ),
        Tool(
            name="get_most_visited_pages",
            description="Get pages data with the most visitor",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_traffic_revenue_trend",
            description="Get traffic or revenue is up/down n% ",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_conversion_rate",
            description="real-time snapshot of key business KPIs—traffic, purchases, revenue, and conversion rate",
            inputSchema={"type": "object", "properties": {}},
        ),
        # Tool(
        #     name="analyze_business_metrics",
        #     description="Generate comprehensive business analytics and insights",
        #     inputSchema={
        #         "type": "object",
        #         "properties": {
        #             "focus_area": {
        #                 "type": "string",
        #                 "enum": ["general", "revenue", "customers", "products"],
        #                 "default": "general",
        #             }
        #         },
        #     },
        # ),
        # Tool(
        #     name="get_executive_dashboard",
        #     description="Get executive dashboard with key business metrics",
        #     inputSchema={"type": "object", "properties": {}},
        # ),
        # Tool(
        #     name="analyze_customer_segments",
        #     description="Analyse customer segmentation and behaviour patterns",
        #     inputSchema={"type": "object", "properties": {}},
        # ),
        # Tool(
        #     name="analyze_product_performance",
        #     description="Analyse product performance and identify opportunities",
        #     inputSchema={"type": "object", "properties": {}},
        # ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> List[TextContent]:
    try:
        if name == "execute_sql_query":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 100)

            if not query.strip():
                return [TextContent(type="text", text="Error: Query cannot be empty")]

            dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "INSERT", "UPDATE", "ALTER", "CREATE"]
            for keyword in dangerous_keywords:
                if keyword in query.upper():
                    return [TextContent(type="text", text=f"Error: Query contains dangerous operation: {keyword}")]

            result = db_manager.execute_query(query, limit)
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        elif name == "get_table_schema":
            table_name = arguments.get("table_name", "")
            if not table_name:
                return [TextContent(type="text", text="Error: Table name is required")]
            schema = db_manager.get_table_schema(table_name)
            return [TextContent(type="text", text=json.dumps(schema, indent=2, default=str))]

        elif name == "get_most_visited_pages":
            top_visited_page   = analytics_engine.get_most_visited_pages()
            return [TextContent(type="text", text=json.dumps(top_visited_page, indent=2, default=str))]
        
        elif name == "get_traffic_revenue_trend":
            trends   = analytics_engine.get_traffic_revenue_trend()
            return [TextContent(type="text", text=json.dumps(trends, indent=2, default=str))]
        
        elif name == "get_conversion_rate":
            comversion_rate = analytics_engine.get_conversion_rate()
            return [TextContent(type="text", text=json.dumps(comversion_rate, indent=2, default=str))]
        
        # elif name == "analyze_business_metrics":
        #     focus_area = arguments.get("focus_area", "general")
        #     insights   = analytics_engine.generate_business_insights(focus_area)
        #     return [TextContent(type="text", text=json.dumps(insights, indent=2, default=str))]

        # elif name == "get_executive_dashboard":
        #     dashboard = analytics_engine.get_executive_summary()
        #     return [TextContent(type="text", text=json.dumps(dashboard, indent=2, default=str))]

        # elif name == "analyze_customer_segments":
        #     segments = analytics_engine.analyze_customer_segments()
        #     return [TextContent(type="text", text=json.dumps(segments, indent=2, default=str))]

        # elif name == "analyze_product_performance":
        #     products = analytics_engine.analyze_product_performance()
        #     return [TextContent(type="text", text=json.dumps(products, indent=2, default=str))]

        else:
            return [TextContent(type="text", text=f"Error: Unknown tool '{name}'")]

    except Exception as e:
        logger.error(f"Tool execution failed for {name}: {e}")
        return [TextContent(type="text", text=f"Error executing tool '{name}': {str(e)}")]


# ── MCP Resources ─────────────────────────────────────────────────────────────
@server.list_resources()
async def handle_list_resources() -> List[Resource]:
    return [
        Resource(
            uri="acommerce://database/tables",
            name="Database Tables",
            description="List of all available ClickHouse tables",
            mimeType="application/json",
        ),
        Resource(
            uri="acommerce://analytics/most-visited-page",
            name="Most Visited Page",
            description="List of most visited page",
            mimeType="application/json",
        ),
        Resource(
            uri="acommerce://analytics/traffic-revenue-trend",
            name="Traffic & Revenue Trend",
            description="Get analysis of traffic revenue trend",
            mimeType="application/json",
        ),
        Resource(
            uri="acommerce://analytics/conversion-rate",
            name="Action Convertion Rate",
            description="Get list of total events convert into revenue",
            mimeType="application/json",
        ),
        # Resource(
        #     uri="acommerce://analytics/executive-summary",
        #     name="Executive Summary",
        #     description="High-level business metrics and KPIs",
        #     mimeType="application/json",
        # ),
        # Resource(
        #     uri="acommerce://analytics/customer-segments",
        #     name="Customer Segments",
        #     description="Customer segmentation analysis",
        #     mimeType="application/json",
        # ),
        # Resource(
        #     uri="acommerce://analytics/product-performance",
        #     name="Product Performance",
        #     description="Product performance metrics and analysis",
        #     mimeType="application/json",
        # ),
        Resource(
            uri="acommerce://schema/warehouse",
            name="Data Warehouse Schema",
            description="Complete schema of the ClickHouse data warehouse",
            mimeType="application/json",
        ),
    ]


@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    try:
        if uri == "acommerce://database/tables":
            tables = db_manager.list_tables()
            return json.dumps({
                "tables":       tables,
                "count":        len(tables),
                "last_updated": datetime.now().isoformat(),
            }, indent=2)

        elif uri == "acommerce://analytics/most-visited-page":
            return json.dumps(analytics_engine.get_most_visited_pages(), indent=2, default=str)
        
        elif uri == "acommerce://analytics/traffic-revenue-trend":
            return json.dumps(analytics_engine.get_traffic_revenue_trend(), indent=2, default=str)
        
        elif uri == "acommerce://analytics/conversion-rate":
            return json.dumps(analytics_engine.get_conversion_rate(), indent=2, default=str)
        
        # elif uri == "acommerce://analytics/executive-summary":
        #     return json.dumps(analytics_engine.get_executive_summary(), indent=2, default=str)

        # elif uri == "acommerce://analytics/customer-segments":
        #     return json.dumps(analytics_engine.analyze_customer_segments(), indent=2, default=str)

        # elif uri == "acommerce://analytics/product-performance":
        #     return json.dumps(analytics_engine.analyze_product_performance(), indent=2, default=str)

        elif uri == "acommerce://schema/warehouse":
            tables      = db_manager.list_tables()
            schema_info = {}
            for table in tables[:10]:
                try:
                    schema_info[table] = db_manager.get_table_schema(table)
                except Exception as e:
                    schema_info[table] = {"error": str(e)}
            return json.dumps({
                "schemas":      schema_info,
                "total_tables": len(tables),
                "generated_at": datetime.now().isoformat(),
            }, indent=2, default=str)

        else:
            raise Exception(f"Unknown resource URI: {uri}")

    except Exception as e:
        logger.error(f"Resource read failed for {uri}: {e}")
        return json.dumps({"error": str(e)}, indent=2)


# ── MCP Prompts ───────────────────────────────────────────────────────────────
@server.list_prompts()
async def handle_list_prompts() -> List[Prompt]:
    return [
        Prompt(
            name="business_analyst",
            description="Act as a senior business analyst for e-commerce web event data analysis",
            arguments=[
                PromptArgument(name="question", description="Business question to analyse", required=True),
                PromptArgument(name="context",  description="Additional context or constraints", required=False),
            ],
        ),
        Prompt(
            name="sql_generator",
            description="Generate ClickHouse SQL queries for business questions",
            arguments=[
                PromptArgument(name="question", description="Business question to convert to SQL", required=True),
                PromptArgument(name="tables",   description="Specific tables to focus on", required=False),
            ],
        ),
        Prompt(
            name="data_storyteller",
            description="Create compelling narratives from data insights",
            arguments=[
                PromptArgument(name="data",     description="Data or insights to create story from", required=True),
                PromptArgument(name="audience", description="Target audience (executives, analysts, etc.)", required=False),
            ],
        ),
    ]


@server.get_prompt()
async def handle_get_prompt(name: str, arguments: dict) -> PromptMessage:
    try:
        if name == "business_analyst":
            question        = arguments.get("question", "")
            context         = arguments.get("context", "")
            top_visited_page = analytics_engine.get_most_visited_pages()
            traffic_revenue_trend = analytics_engine.get_traffic_revenue_trend()
            events_conversion_rate = analytics_engine.get_conversion_rate()

            system_prompt = f"""You are a senior business analyst for ACommerce, an e-commerce company.
                You have access to comprehensive business data stored in ClickHouse and should provide data-driven insights.

                Current Business Context:
                - Most Visited Page: ${top_visited_page['top_visited_page']}
                - Traffic Revenue Trend: {traffic_revenue_trend['trends']}
                - Events Conversion Rate: {events_conversion_rate['conversion_rate']}

                Question: {question}
                {f'Additional Context: {context}' if context else ''}

                Please provide:
                1. Data-driven analysis
                2. Key insights and trends
                3. Actionable recommendations
                4. Potential risks or opportunities
                5. Specific metrics to support your analysis

                Use the available MCP tools to query ClickHouse as needed."""

            return PromptMessage(role=Role.user, content=TextContent(type="text", text=system_prompt))

        elif name == "sql_generator":
            question        = arguments.get("question", "")
            tables          = arguments.get("tables", "")
            available_tables = db_manager.list_tables()

            system_prompt = f"""You are an expert ClickHouse SQL analyst. Generate SQL queries to answer business questions.

                                Note: This is ClickHouse, not standard SQL. Key differences:
                                - Use count() not COUNT(*) (though both work)
                                - Use uniq() for approximate distinct counts, uniqExact() for exact
                                - Use leftPad(toString(month), 2, '0') instead of LPAD for zero-padding
                                - Use lagInFrame() for window lag functions
                                - Use system.tables and system.columns instead of information_schema

                                Available Tables:
                                {chr(10).join(f'- {table}' for table in available_tables)}

                                Key Tables:
                                - {CLICKHOUSE_DB}.user_events: Main events table 
                                - {CLICKHOUSE_DB}.events_per_minute: Materialised view for event counts per minute
                                - {CLICKHOUSE_DB}.events_by_country: Materialised view for top countries
                                - {CLICKHOUSE_DB}.flink_enriched_events: row-level enriched version of the raw user_events table
                                - {CLICKHOUSE_DB}.flink_window_counts: Basic 1-min aggregations, kept for compatibility

                                Question: {question}
                                {f'Focus on tables: {tables}' if tables else ''}

                                Generate a ClickHouse SQL query that:
                                1. Answers the business question accurately
                                2. Uses ClickHouse-idiomatic functions
                                3. Includes appropriate GROUP BY and ORDER BY
                                4. Limits results to a reasonable size (LIMIT 100)
                                5. Uses clear column aliases

                                Return only the SQL query, no explanations."""

            return PromptMessage(role=Role.user, content=TextContent(type="text", text=system_prompt))

        elif name == "data_storyteller":
            data     = arguments.get("data", "")
            audience = arguments.get("audience", "executives")

            system_prompt = f"""You are a data storytelling expert who creates compelling narratives from business data.

                                Data to analyse: {data}
                                Target audience: {audience}

                                Create a compelling data story that:
                                1. Starts with a clear headline/key message
                                2. Provides context and background
                                3. Highlights the most important insights
                                4. Uses storytelling techniques to engage the audience
                                5. Ends with clear, actionable recommendations
                                6. Adapts tone and complexity for the target audience

                                Structure:
                                - Executive Summary (2-3 sentences)
                                - Key Findings (3-5 bullet points)
                                - Deep Dive Analysis (2-3 paragraphs)
                                - Recommendations (3-5 actionable items)
                                - Next Steps

                                Make it engaging and actionable for {audience}."""

            return PromptMessage(role=Role.user, content=TextContent(type="text", text=system_prompt))

        else:
            raise Exception(f"Unknown prompt: {name}")

    except Exception as e:
        logger.error(f"Prompt generation failed for {name}: {e}")
        return PromptMessage(
            role=Role.user,
            content=TextContent(type="text", text=f"Error generating prompt '{name}': {str(e)}")
        )


# ── Entry point ───────────────────────────────────────────────────────────────
async def main():
    logger.info("🚀 Starting  ACommerce MCP Server")
    logger.info(f"📊 ClickHouse: {CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/{CLICKHOUSE_DB}")
    logger.info(f"🔧 Max query rows: {MAX_QUERY_ROWS}")

    try:
        tables = db_manager.list_tables()
        logger.info(f"✅ ClickHouse connected — {len(tables)} tables available")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        sys.exit(1)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="commerce-analysis",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())