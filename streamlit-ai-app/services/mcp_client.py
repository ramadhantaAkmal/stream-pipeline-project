"""
HTTP-based MCP Client for Streamlit
==================================

This client communicates with the MCP server via HTTP REST API,
following proper separation of concerns in the MCP architecture.
"""

import json
import logging
import os
import requests
from typing import Any, Dict, List, Optional
from datetime import datetime
import streamlit as st

logger = logging.getLogger(__name__)

class MCPClient:
    """
    HTTP-based MCP client that communicates with the MCP server
    via REST API endpoints.
    """
    
    def __init__(self, mcp_server_url: str = None):
        """Initialize HTTP-based MCP client"""
        self.mcp_server_url = mcp_server_url or os.getenv("MCP_SERVER_URL", "http://mcp-server:5000")
        self._connection_status = {"connected": False, "error": None}
        self._test_connection()
    
    def _test_connection(self):
        """Test MCP server connection - checks current status, not cached"""
        try:
            response = requests.get(f"{self.mcp_server_url}/health", timeout=5)
            response.raise_for_status()
            self._connection_status = {"connected": True, "error": None}
            logger.info(f"✅ MCP server connected: {self.mcp_server_url}")
            return True
        except Exception as e:
            self._connection_status = {"connected": False, "error": str(e)}
            logger.warning(f"⚠️ MCP server not available: {e}")
            logger.info("📋 Will use fallback mode - ensure MCP server is running")
            return False
    
    def _is_connected(self):
        """
        Check if MCP server is currently connected.
        This performs a live check rather than relying on cached status,
        which is critical for Streamlit's caching behavior.
        """
        try:
            response = requests.get(f"{self.mcp_server_url}/health", timeout=2)
            response.raise_for_status()
            return True
        except Exception:
            return False
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status"""
        status = self._connection_status.copy()
        
        # Check AI availability
        try:
            ai_status = self._make_mcp_request("/ai/status")
            if ai_status:
                status["ai_available"] = ai_status.get("ai_available", False)
                status["ai_model"] = ai_status.get("model", "unknown")
            else:
                status["ai_available"] = False
        except:
            status["ai_available"] = False
        
        return status
    
    def _make_mcp_request(self, endpoint: str, method: str = "GET", data: Dict = None, timeout: int = None) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request to MCP server with intelligent timeout handling
        
        Args:
            endpoint: API endpoint path
            method: HTTP method (GET or POST)
            data: Request payload for POST requests
            timeout: Custom timeout in seconds (auto-calculated if None)
        
        Returns:
            Response dict or error dict with 'error' key
        """
        try:
            url = f"{self.mcp_server_url}{endpoint}"
            
            # Intelligent timeout based on endpoint type
            if timeout is None:
                if endpoint.startswith("/ai/"):
                    # AI endpoints need much longer timeout due to:
                    # - Model loading/warmup (first request: 60-180s)
                    # - Inference time (30-120s per request)
                    # - Query execution + analysis (10-30s)
                    timeout = 300  # 5 minutes for AI operations
                elif endpoint == "/query":
                    # Database queries can be complex
                    timeout = 60  # 1 minute for queries
                else:
                    # Standard endpoints (health, status, tables, etc.)
                    timeout = 30  # 30 seconds default
            
            logger.info(f"🔄 MCP request: {method} {endpoint} (timeout: {timeout}s)")
            start_time = datetime.now()
            
            if method == "GET":
                response = requests.get(url, timeout=timeout)
            elif method == "POST":
                response = requests.post(url, json=data, timeout=timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"✅ MCP response: {method} {endpoint} completed in {elapsed:.2f}s")
            
            response.raise_for_status()
            result = response.json()
            return result
            
        except requests.exceptions.HTTPError as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"❌ MCP HTTP error {e.response.status_code} on {endpoint} after {elapsed:.2f}s: {error_detail}")
            
            # Try to parse error response
            try:
                error_json = e.response.json()
                return {"error": error_json.get("detail", error_detail)}
            except:
                return {"error": f"HTTP {e.response.status_code}: {error_detail}"}
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ MCP connection error on {endpoint}: Cannot connect to {self.mcp_server_url}")
            logger.error(f"   Ensure MCP server is running: docker ps | grep mcp-server")
            return {"error": f"Cannot connect to MCP server at {self.mcp_server_url}. Is the service running?"}
            
        except requests.exceptions.Timeout as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ MCP timeout on {endpoint} after {elapsed:.2f}s (limit: {timeout}s)")
            
            # Provide specific guidance based on endpoint
            if endpoint.startswith("/ai/"):
                error_msg = f"AI request timeout after {elapsed:.0f}s. This usually means:\n"
                error_msg += "1. Ollama model is loading for the first time (can take 2-3 minutes)\n"
                error_msg += "2. Ollama service is not running or not responding\n"
                error_msg += "3. The model is overloaded with requests\n\n"
                error_msg += "Check Ollama status: docker logs ollama"
            else:
                error_msg = f"Request timeout after {elapsed:.0f}s. The MCP server may be overloaded."
            
            return {"error": error_msg}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ MCP request failed on {endpoint}: {e}", exc_info=True)
            return {"error": f"Request failed: {str(e)}"}
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ MCP response parsing error on {endpoint}: Invalid JSON response")
            return {"error": "Invalid JSON response from MCP server"}
            
        except Exception as e:
            logger.error(f"❌ Unexpected error in MCP request to {endpoint}: {e}", exc_info=True)
            return {"error": f"Unexpected error: {str(e)}"}
    
    def execute_query(self, query: str, limit: int = 100) -> Optional[Dict[str, Any]]:
        """Execute SQL query via MCP server"""
        if not self._is_connected():
            logger.warning("MCP server not available for query execution")
            return {
                "success": False,
                "error": "MCP server not available",
                "data": {
                    "columns": [],
                    "rows": [],
                    "row_count": 0
                }
            }
        
        data = {
            "query": query,
            "limit": limit
        }
        
        result = self._make_mcp_request("/query", "POST", data)
        
        if result and "columns" in result and "rows" in result:
            # MCP server returns flat structure, convert to expected nested format
            return {
                "success": True,
                "data": {
                    "columns": result.get("columns", []),
                    "rows": result.get("rows", []),
                    "row_count": result.get("row_count", 0)
                },
                "execution_time_ms": result.get("execution_time_ms", 0)
            }
        elif result and "error" in result:
            # Server returned an error response
            error_msg = result.get("error", "Unknown error")
            logger.error(f"Query execution failed: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "data": {
                    "columns": [],
                    "rows": [],
                    "row_count": 0
                }
            }
        else:
            # Unexpected response format or None result
            logger.error(f"Query execution failed: Invalid response format - {result}")
            return {
                "success": False,
                "error": "Failed to execute query via MCP server - Invalid response",
                "data": {
                    "columns": [],
                    "rows": [],
                    "row_count": 0
                }
            }
    
    def get_table_schema(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Get table schema via MCP server"""
        if not self._is_connected():
            return None
        
        # Table schema endpoint not implemented in simplified server
        # Return None for now - will implement if needed
        return None
        return result
    
    def get_executive_dashboard(self) -> Optional[Dict[str, Any]]:
        """Get executive dashboard data via MCP server"""
        if not self._is_connected():
            logger.warning("MCP server not available - dashboard data unavailable")
            return None
        
        result = self._make_mcp_request("/analytics/summary")
        
        if result and "key_metrics" in result:
            # Return in expected format
            return {
                "key_metrics": result["key_metrics"],
                "revenue_trends": []  # Will be populated by separate query
            }
        
        return None
    
    def get_customer_segments(self) -> Optional[Dict[str, Any]]:
        """Get customer segmentation data via MCP server"""
        if not self._is_connected():
            logger.warning("MCP server not available - customer data unavailable")
            return None
        
        # Query customer segments directly
        query = """
        SELECT 
            customer_segment,
            COUNT(*) as customer_count,
            AVG(lifetime_revenue) as avg_lifetime_revenue,
            AVG(estimated_clv) as avg_clv
        FROM main.dim_customers
        WHERE customer_segment IS NOT NULL
        GROUP BY customer_segment
        ORDER BY customer_count DESC
        """
        
        result = self.execute_query(query)
        
        if result and result.get("success") and result.get("data", {}).get("rows"):
            return {
                "segments": result["data"]["rows"]
            }
        
        return None
    
    def get_product_performance(self) -> Optional[Dict[str, Any]]:
        """Get product performance data via MCP server"""
        if not self._is_connected():
            logger.warning("MCP server not available - product data unavailable")
            return None
        
        # Query product performance directly
        query = """
        SELECT 
            product_name,
            category,
            total_revenue as revenue,
            total_orders,
            total_units_sold,
            ROUND(total_revenue / NULLIF(total_orders, 0), 2) as avg_order_value,
            performance_tier,
            revenue_rank,
            revenue_last_30d,
            days_since_last_sale
        FROM main.fct_product_performance
        ORDER BY total_revenue DESC
        LIMIT 50
        """
        
        result = self.execute_query(query)
        
        if result and result.get("success") and result.get("data", {}).get("rows"):
            return {
                "top_products": result["data"]["rows"],
                "data": {
                    "top_products": result["data"]["rows"]
                }
            }
        
        return None
    
    def get_database_tables(self) -> List[str]:
        """Get list of available tables via MCP server"""
        if not self._is_connected():
            logger.warning("MCP server not available - cannot list tables")
            return []
        
        result = self._make_mcp_request("/tables")
        
        if result and "tables" in result:
            return result["tables"]
        else:
            logger.warning("Failed to retrieve tables list from MCP server")
            return []
    
    def get_business_insights(self, question: str = "general") -> Optional[Dict[str, Any]]:
        """
        Get business insights by analyzing the user's question and querying the database.
        
        This method parses natural language questions and executes appropriate SQL queries
        to provide data-driven answers.
        """
        if not self._is_connected():
            logger.warning("MCP server not available - cannot generate insights")
            return None
        
        # Normalize the question for analysis
        question_lower = question.lower().strip()
        
        # Pattern matching for common questions
        insights = []
        
        # Customer count questions
        if any(keyword in question_lower for keyword in ["how many customer", "number of customer", "total customer", "customer count"]):
            query = """
            SELECT 
                COUNT(DISTINCT customer_sk) as total_customers,
                COUNT(DISTINCT CASE WHEN is_active_customer THEN customer_sk END) as active_customers,
                COUNT(DISTINCT CASE WHEN customer_segment = 'Champions' THEN customer_sk END) as champion_customers,
                COUNT(DISTINCT CASE WHEN is_at_risk_customer THEN customer_sk END) as at_risk_customers
            FROM main.dim_customers
            """
            result = self.execute_query(query)
            
            if result and result.get("success") and result.get("data", {}).get("rows"):
                data = result["data"]["rows"][0]
                insights.append({
                    "title": "Customer Base Overview",
                    "description": f"You have **{data['total_customers']:,}** total customers in your database.",
                    "metrics": [
                        f"Active Customers: {data['active_customers']:,}",
                        f"Champion Customers: {data['champion_customers']:,}",
                        f"At-Risk Customers: {data['at_risk_customers']:,}"
                    ],
                    "recommendations": [
                        "Focus on retaining your champion customers",
                        "Develop re-engagement campaigns for at-risk customers"
                    ]
                })
        
        # Revenue questions
        elif any(keyword in question_lower for keyword in ["revenue", "sales", "income", "earnings"]):
            query = """
            SELECT 
                ROUND(SUM(total_revenue), 2) as total_revenue,
                COUNT(DISTINCT customer_fk) as customers,
                SUM(total_orders) as total_orders,
                ROUND(AVG(avg_order_value), 2) as avg_order_value
            FROM main.fct_monthly_revenue
            """
            result = self.execute_query(query)
            
            if result and result.get("success") and result.get("data", {}).get("rows"):
                data = result["data"]["rows"][0]
                insights.append({
                    "title": "Revenue Overview",
                    "description": f"Your total revenue is **${data['total_revenue']:,.2f}** across {data['total_orders']:,} orders.",
                    "metrics": [
                        f"Average Order Value: ${data['avg_order_value']:,.2f}",
                        f"Total Customers: {data['customers']:,}"
                    ],
                    "recommendations": [
                        "Analyze top-performing products to replicate success",
                        "Consider upselling strategies to increase AOV"
                    ]
                })
        
        # Product questions
        elif any(keyword in question_lower for keyword in ["product", "item", "merchandise"]):
            query = """
            SELECT 
                COUNT(DISTINCT product_sk) as total_products,
                COUNT(DISTINCT CASE WHEN performance_tier = 'Top 10' THEN product_sk END) as top_products,
                ROUND(SUM(total_revenue), 2) as total_revenue,
                SUM(total_units_sold) as total_units
            FROM main.fct_product_performance
            """
            result = self.execute_query(query)
            
            if result and result.get("success") and result.get("data", {}).get("rows"):
                data = result["data"]["rows"][0]
                insights.append({
                    "title": "Product Performance",
                    "description": f"You have **{data['total_products']:,}** products with {data['total_units']:,} units sold.",
                    "metrics": [
                        f"Total Revenue: ${data['total_revenue']:,.2f}",
                        f"Top 10 Products: {data['top_products']}"
                    ],
                    "recommendations": [
                        "Review product performance in the Product Analytics section",
                        "Consider discontinuing low-performing products"
                    ]
                })
        
        # Order questions
        elif any(keyword in question_lower for keyword in ["order", "transaction", "purchase"]):
            query = """
            SELECT 
                SUM(total_orders) as total_orders,
                COUNT(DISTINCT customer_fk) as unique_customers,
                ROUND(AVG(avg_order_value), 2) as avg_order_value,
                ROUND(SUM(total_revenue), 2) as total_revenue
            FROM main.fct_monthly_revenue
            """
            result = self.execute_query(query)
            
            if result and result.get("success") and result.get("data", {}).get("rows"):
                data = result["data"]["rows"][0]
                insights.append({
                    "title": "Order Statistics",
                    "description": f"You have processed **{data['total_orders']:,}** orders from {data['unique_customers']:,} customers.",
                    "metrics": [
                        f"Total Revenue: ${data['total_revenue']:,.2f}",
                        f"Average Order Value: ${data['avg_order_value']:,.2f}"
                    ],
                    "recommendations": [
                        "Analyze order patterns in the Advanced Analytics section",
                        "Consider implementing order frequency campaigns"
                    ]
                })
        
        # Default response if no pattern matched
        else:
            insights.append({
                "title": "Data Analysis",
                "description": "I can help you analyze your e-commerce data. Try asking about:",
                "metrics": [
                    "Customer counts and segments",
                    "Revenue and sales performance",
                    "Product analytics",
                    "Order statistics"
                ],
                "recommendations": [
                    "Use the Data Explorer to run custom SQL queries",
                    "Check the Advanced Analytics section for detailed insights"
                ]
            })
        
        return {
            "insights": insights
        }
    
    def ask_ai_question(self, question: str, execute_query: bool = True, analyze_results: bool = True) -> Optional[Dict[str, Any]]:
        """
        Complete AI-powered question answering:
        - Generates SQL from natural language using Ollama
        - Executes the query against Clickhouse
        - Analyzes results with AI
        - Returns comprehensive insights
        
        Args:
            question: Natural language question about the data
            execute_query: Whether to execute the generated SQL (default: True)
            analyze_results: Whether to generate AI analysis of results (default: True)
            
        Returns:
            Dict with keys:
                - success: bool
                - question: str
                - generated_sql: str
                - query_executed: bool
                - query_result: dict (if executed)
                - ai_analysis: str (if analyzed)
                - error: str (if failed)
        """
        if not self._is_connected():
            logger.warning("MCP server not available for AI question answering")
            return {
                "success": False,
                "error": "MCP server is not connected. Please check the service status."
            }
        
        logger.info(f"Sending AI question to MCP server: {question[:100]}...")
        
        data = {
            "question": question,
            "execute_query": execute_query,
            "analyze_results": analyze_results
        }
        
        result = self._make_mcp_request("/ai/ask", "POST", data)
        
        if result:
            # Check if result contains an error
            if "error" in result:
                logger.error(f"AI question answering failed: {result['error']}")
                return {
                    "success": False,
                    "question": question,
                    "error": result["error"]
                }
            
            # Ensure success flag is set
            if "success" not in result:
                result["success"] = True
            
            logger.info(f"AI question answered successfully: SQL generated={result.get('sql_generated', False)}, Query executed={result.get('query_executed', False)}, Analysis generated={result.get('analysis_generated', False)}")
            return result
        else:
            logger.error("AI question answering failed: No response from MCP server")
            return {
                "success": False,
                "question": question,
                "error": "No response from MCP server. The service may be down or overloaded."
            }
    
    def generate_sql_with_ai(self, question: str, include_schema: bool = True) -> Optional[str]:
        """Generate SQL query from natural language using AI"""
        if not self._is_connected():
            logger.warning("MCP server not available for SQL generation")
            return None
        
        data = {
            "question": question,
            "include_schema": include_schema
        }
        
        result = self._make_mcp_request("/ai/generate-sql", "POST", data)
        
        if result and "generated_sql" in result:
            return result["generated_sql"]
        else:
            logger.error(f"SQL generation failed")
            return None
    
    def analyze_data_with_ai(self, question: str, data: Dict = None) -> Optional[str]:
        """Analyze data and generate business insights using AI"""
        if not self._is_connected():
            logger.warning("MCP server not available for data analysis")
            return None
        
        request_data = {
            "question": question
        }
        
        if data:
            request_data["data"] = data
        
        result = self._make_mcp_request("/ai/analyze-data", "POST", request_data)
        
        if result and "analysis" in result:
            return result["analysis"]
        else:
            logger.error(f"Data analysis failed")
            return None
    
    def generate_sql_prompt(self, question: str) -> Optional[str]:
        """Generate SQL prompt via MCP server"""
        if not self._connection_status["connected"]:
            return f"""
                    I can help you write SQL queries to answer your question: "{question}"

                    Common tables available:
                    - **main.dim_customers**: Customer data and segments
                    - **main.fct_monthly_revenue**: Monthly revenue by customer  
                    - **main.fct_product_performance**: Product performance metrics
                    - **main.fct_customer_journey**: Customer behavior data
                    - **main.fct_orders**: Order details and transactions

                    Use the Data Explorer to write and execute custom SQL queries.
                    """
        
        # Generate a helpful SQL template based on the question
        question_lower = question.lower()
        
        if "revenue" in question_lower or "sales" in question_lower:
            return f"""
                    To analyze revenue for: "{question}"

                    Try this query:
                    ```sql
                    SELECT 
                        order_year,
                        order_month,
                        SUM(total_revenue) as revenue,
                        COUNT(DISTINCT customer_fk) as customers,
                        SUM(total_orders) as orders
                    FROM main.fct_monthly_revenue
                    GROUP BY order_year, order_month
                    ORDER BY order_year DESC, order_month DESC
                    LIMIT 12
                    ```
                    """
        elif "customer" in question_lower:
            return f"""
                    To analyze customers for: "{question}"

                    Try this query:
                    ```sql
                    SELECT 
                        customer_segment,
                        COUNT(*) as customer_count,
                        AVG(lifetime_revenue) as avg_revenue,
                        AVG(lifetime_orders) as avg_orders
                    FROM main.dim_customers
                    GROUP BY customer_segment
                    ORDER BY customer_count DESC
                    ```
                    """
        elif "product" in question_lower:
            return f"""
                    To analyze products for: "{question}"

                    Try this query:
                    ```sql
                    SELECT 
                        product_name,
                        category,
                        total_revenue,
                        total_orders,
                        performance_tier
                    FROM main.fct_product_performance
                    ORDER BY total_revenue DESC
                    LIMIT 20
                    ```
                    """
        else:
            return f"""
                    For your question: "{question}"

                    I recommend exploring these tables:
                    - main.dim_customers (customer information)
                    - main.fct_monthly_revenue (revenue metrics)
                    - main.fct_product_performance (product analytics)

                    Use the Data Explorer to write custom SQL queries.
                    """

# Singleton pattern for Streamlit
@st.cache_resource
def get_mcp_client() -> MCPClient:
    """Get or create MCP client instance"""
    return MCPClient()