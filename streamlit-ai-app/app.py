import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import os
import asyncio
import logging
from datetime import datetime, timedelta
import json
from typing import Dict, List, Any, Optional

from services.mcp_client import get_mcp_client
from components.advanced_ui import AdvancedUIComponents
from components.data_visualizer import AdvancedDataVisualizer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Page config 
st.set_page_config(
    page_title="A-Commerce",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://docs.acommerce.com',
        'Report a bug': 'https://github.com/acommerce/issues',
        'About': "# A-Commerce \n### AI-Native E-commerce Analytics Platform"
    }
)

st.markdown("""
<style>
    /* Import modern fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Global styles */
    .main {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Header styling */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
        box-shadow: 0 8px 32px rgba(0,0,0,0.1);
    }
    
    .main-header h1 {
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }
    
    .main-header p {
        font-size: 1.2rem;
        opacity: 0.9;
        font-weight: 300;
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
        border-right: 1px solid #e2e8f0;
    }
    
    /* Metric cards */
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 16px rgba(0,0,0,0.05);
        margin-bottom: 1rem;
        transition: all 0.3s ease;
    }
    
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 32px rgba(0,0,0,0.1);
    }
    
    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 0.5rem;
    }
    
    .metric-label {
        font-size: 0.9rem;
        color: #64748b;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    .metric-change {
        font-size: 0.85rem;
        font-weight: 600;
        margin-top: 0.5rem;
    }
    
    .metric-change.positive {
        color: #10b981;
    }
    
    .metric-change.negative {
        color: #ef4444;
    }
    
    /* Status indicators */
    .status-indicator {
        display: inline-flex;
        align-items: center;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 0.25rem 0;
    }
    
    .status-connected {
        background: #dcfce7;
        color: #166534;
        border: 1px solid #bbf7d0;
    }
    
    .status-disconnected {
        background: #fef2f2;
        color: #dc2626;
        border: 1px solid #fecaca;
    }
    
    .status-warning {
        background: #fef3c7;
        color: #d97706;
        border: 1px solid #fed7aa;
    }
    
    /* Chat interface */
    .chat-container {
        background: white;
        border-radius: 16px;
        padding: 1.5rem;
        box-shadow: 0 4px 16px rgba(0,0,0,0.05);
        border: 1px solid #e2e8f0;
    }
    
    .chat-message {
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 12px;
        max-width: 80%;
    }
    
    .chat-message.user {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        margin-left: auto;
    }
    
    .chat-message.assistant {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        color: #1e293b;
    }
    
    /* Navigation tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: #f8fafc;
        padding: 0.5rem;
        border-radius: 12px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding: 0 24px;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
        color: #1e293b !important;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        color: #1e293b !important;
    }
    
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background: white;
        color: #667eea !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    
    /* Tab content */
    .stTabs [data-baseweb="tab-panel"] {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        margin-top: 1rem;
        box-shadow: 0 4px 16px rgba(0,0,0,0.05);
        border: 1px solid #e2e8f0;
        color: #1e293b !important;
    }
    
    /* Ensure all text in tabs is visible */
    .stTabs [data-baseweb="tab-panel"] * {
        color: #1e293b !important;
    }
    
    .stTabs [data-baseweb="tab-panel"] h1,
    .stTabs [data-baseweb="tab-panel"] h2,
    .stTabs [data-baseweb="tab-panel"] h3,
    .stTabs [data-baseweb="tab-panel"] h4,
    .stTabs [data-baseweb="tab-panel"] h5,
    .stTabs [data-baseweb="tab-panel"] h6 {
        color: #1e293b !important;
    }
    
    .stTabs [data-baseweb="tab-panel"] p {
        color: #64748b !important;
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
    }
    
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 16px rgba(102, 126, 234, 0.4);
    }
    
    /* Data tables */
    .dataframe {
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 4px 16px rgba(0,0,0,0.05);
    }
    
    /* Loading states */
    .loading-spinner {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 2rem;
    }
    
    /* Responsive design */
    @media (max-width: 768px) {
        .main-header h1 {
            font-size: 2rem;
        }
        
        .metric-card {
            padding: 1rem;
        }
        
        .metric-value {
            font-size: 2rem;
        }
    }
    
    /* Dark mode support */
    @media (prefers-color-scheme: dark) {
        .metric-card {
            background: #1e293b;
            border-color: #374151;
            color: white;
        }
        
        .chat-container {
            background: #1e293b;
            border-color: #374151;
        }
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.chat_history = []
    st.session_state.selected_dashboard = "executive"
    st.session_state.auto_refresh = False
    st.session_state.theme = "light"

# Initialize services
@st.cache_resource
def initialize_services():
    """Initialize and cache service connections"""
    ui_components = AdvancedUIComponents()
    visualizer = AdvancedDataVisualizer()
    
    return ui_components, visualizer

# Load services
ui_components, visualizer = initialize_services()

# Get MCP client (singleton)
mcp_client = get_mcp_client()

def render_main_header():
    """Render the main application header"""
    st.markdown("""
    <div class="main-header">
        <h1>🚀 A-Commerce Platform</h1>
        <p>AI-Native E-commerce Analytics Platform | Powered by Advanced Intelligence</p>
    </div>
    """, unsafe_allow_html=True)

def render_sidebar():
    """Render enhanced sidebar with navigation and status"""
    with st.sidebar:
        st.markdown("### 🎛️ Control Center")
        
        # Service status
        render_service_status()
        
        st.divider()
        
        # Navigation
        st.markdown("### 📊 Analytics Modules")
        nav_option = st.radio(
            "Select Module",
            ["🏠 Executive Dashboard", "🤖 AI Copilot", "📈 Advanced Analytics", "🔍 Data Explorer", "🎯 Customer Intelligence", "📦 Product Performance"],
            label_visibility="collapsed"
        )
        
        st.divider()
        
        # Settings
        st.markdown("### ⚙️ Settings")
        st.session_state.auto_refresh = st.toggle("Auto Refresh", value=st.session_state.auto_refresh)
        
        if st.session_state.auto_refresh:
            refresh_interval = st.selectbox("Refresh Interval", [30, 60, 300, 600], index=2, format_func=lambda x: f"{x}s")
        
        # Theme toggle
        theme_options = {"Light": "light", "Dark": "dark", "Auto": "auto"}
        selected_theme = st.selectbox("Theme", list(theme_options.keys()), index=0)
        st.session_state.theme = theme_options[selected_theme]
        
        return nav_option

def render_service_status():
    """Render service connection status"""
    st.markdown("**🔗 Service Status**")
    
    # MCP Server status
    mcp_status = mcp_client.get_connection_status()
    if mcp_status["connected"]:
        st.markdown(
            '<div class="status-indicator status-connected">✅ Analytics Engine</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="status-indicator status-disconnected">❌ Analytics Engine</div>',
            unsafe_allow_html=True
        )
    
    # AI Assistant status
    ai_available = mcp_status.get("ai_available", False)
    if ai_available:
        ai_model = mcp_status.get("ai_model", "unknown")
        st.markdown(
            f'<div class="status-indicator status-connected">✅ AI Assistant ({ai_model})</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="status-indicator status-warning">⚠️ AI Assistant (Fallback Mode)</div>',
            unsafe_allow_html=True
        )
        st.caption("💡 Start Ollama for full AI capabilities")

def render_executive_dashboard():
    """Render executive dashboard with key metrics"""
    st.markdown("## 📊 Executive Dashboard")
    st.markdown("*Real-time business intelligence and key performance indicators*")
    
    # Fetch dashboard data
    with st.spinner("Loading executive metrics..."):
        try:
            dashboard_data = mcp_client.get_executive_dashboard()
            if dashboard_data and "key_metrics" in dashboard_data:
                # Key metrics row
                col1, col2, col3, col4 = st.columns(4)
                
                metrics = dashboard_data.get("key_metrics", {})
                
                with col1:
                    ui_components.render_metric_card(
                        title="Total Revenue",
                        value=f"${metrics.get('total_revenue', 0):,.2f}",
                        change="+12.5%",
                        change_type="positive"
                    )
                
                with col2:
                    ui_components.render_metric_card(
                        title="Total Customers",
                        value=f"{metrics.get('total_customers', 0):,}",
                        change="+8.3%",
                        change_type="positive"
                    )
                
                with col3:
                    ui_components.render_metric_card(
                        title="Total Orders",
                        value=f"{metrics.get('total_orders', 0):,}",
                        change="+15.7%",
                        change_type="positive"
                    )
                
                with col4:
                    ui_components.render_metric_card(
                        title="Avg Order Value",
                        value=f"${metrics.get('avg_order_value', 0):.2f}",
                        change="-2.1%",
                        change_type="negative"
                    )
                
                st.markdown("---")
                
                # Revenue trend chart
                if "revenue_trends" in dashboard_data and dashboard_data["revenue_trends"]:
                    st.markdown("### 📈 Revenue Trend")
                    
                    trend_df = pd.DataFrame(dashboard_data["revenue_trends"])
                    if not trend_df.empty:
                        fig = visualizer.create_revenue_trend_chart(trend_df)
                        st.plotly_chart(fig, use_container_width=True)
                
            else:
                st.error("Failed to load dashboard data")
                
        except Exception as e:
            st.error(f"Error loading dashboard: {str(e)}")

def render_ai_copilot():
    """Render AI-powered chat interface"""
    st.markdown("## 🤖 AI Data Copilot")
    
    # Check AI status
    mcp_status = mcp_client.get_connection_status()
    ai_available = mcp_status.get("ai_available", False)
    
    if ai_available:
        ai_model = mcp_status.get("ai_model", "unknown")
        st.markdown(f"*Ask questions about your data in natural language - Powered by {ai_model.upper()} 🚀*")
    else:
        st.markdown("*Ask questions about your data - Using pattern matching (Start Ollama for full AI)*")
    
    # Chat container
    chat_container = st.container()
    
    with chat_container:
        # Display chat history
        for message in st.session_state.chat_history:
            if message["role"] == "user":
                st.markdown(f"""
                <div class="chat-message user">
                    <strong>You:</strong> {message["content"]}
                </div>
                """, unsafe_allow_html=True)
            elif message["role"] == "assistant":
                st.markdown(f"""
                <div class="chat-message assistant">
                    <strong>AI Assistant:</strong> {message["content"]}
                </div>
                """, unsafe_allow_html=True)
            elif message["role"] == "data":
                # Display data results
                st.markdown('<div class="chat-message assistant">', unsafe_allow_html=True)
                st.markdown("**📊 Query Results:**")
                
                if "dataframe" in message:
                    st.dataframe(message["dataframe"], use_container_width=True)
                
                if "metrics" in message:
                    cols = st.columns(len(message["metrics"]))
                    for i, (label, value) in enumerate(message["metrics"].items()):
                        with cols[i]:
                            st.metric(label, value)
                
                st.markdown('</div>', unsafe_allow_html=True)
    
    # Chat input
    user_input = st.chat_input("Ask me anything about your e-commerce data...")
    
    if user_input:
        # Add user message to history
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        
        # Generate AI response
        with st.spinner("🤖 AI is analyzing your question..."):
            try:
                # Try AI-powered question answering first
                if ai_available:
                    logger.info(f"Using AI to answer: {user_input}")
                    ai_response = mcp_client.ask_ai_question(
                        question=user_input,
                        execute_query=True,
                        analyze_results=True
                    )
                    
                    if ai_response and ai_response.get("success", True):
                        response_parts = []
                        
                        # Show generated SQL
                        if "generated_sql" in ai_response:
                            sql_text = ai_response["generated_sql"]
                            response_parts.append("**🔍 Generated SQL Query:**")
                            response_parts.append(f"```sql\n{sql_text}\n```")
                            
                            # Show execution time if available
                            if "execution_time_ms" in ai_response:
                                exec_time = ai_response["execution_time_ms"]
                                response_parts.append(f"*Query executed in {exec_time:.2f}ms*")
                        
                        # Show query results
                        if ai_response.get("query_executed") and "query_result" in ai_response:
                            query_result = ai_response["query_result"]
                            
                            if query_result.get("rows"):
                                row_count = query_result["row_count"]
                                response_parts.append(f"\n**📊 Query Results** ({row_count} rows)")
                                
                                # Add data message to history for table display
                                import pandas as pd
                                df = pd.DataFrame(query_result["rows"])
                                st.session_state.chat_history.append({
                                    "role": "data",
                                    "dataframe": df
                                })
                            else:
                                response_parts.append("\n**ℹ️ No results found** - The query executed successfully but returned no data.")
                        
                        # Show AI analysis
                        if ai_response.get("analysis_generated") and "ai_analysis" in ai_response:
                            analysis = ai_response["ai_analysis"]
                            response_parts.append("\n---\n\n**💡 AI Business Analysis:**\n")
                            response_parts.append(analysis)
                        elif ai_response.get("analysis_error"):
                            response_parts.append(f"\n**⚠️ Analysis Note:** {ai_response['analysis_error']}")
                        
                        # Show query error if any
                        if ai_response.get("query_error"):
                            response_parts.append(f"\n**⚠️ Query Execution Error:**\n```\n{ai_response['query_error']}\n```")
                        
                        # Combine all parts
                        response = "\n\n".join(response_parts)
                        
                        if not response:
                            response = "I processed your question but couldn't generate a meaningful response. Please try rephrasing your question or check the Data Explorer for manual queries."
                        
                        # Add AI response to history
                        st.session_state.chat_history.append({"role": "assistant", "content": response})
                        
                        # Rerun to display new messages
                        st.rerun()
                    elif ai_response and "error" in ai_response:
                        # Handle error response from MCP server
                        error_msg = ai_response.get("error", "Unknown error")
                        response = f"**❌ Error:** {error_msg}\n\n"
                        response += "**Troubleshooting:**\n"
                        response += "- Ensure Ollama is running and accessible\n"
                        response += "- Check that the model is loaded (try `ollama list`)\n"
                        response += "- Verify database connectivity\n"
                        response += "- Try rephrasing your question"
                        
                        st.session_state.chat_history.append({"role": "assistant", "content": response})
                        st.rerun()
                    else:
                        # AI failed, fall back to pattern matching
                        logger.warning("AI response failed, falling back to pattern matching")
                        ai_available = False
                
                # Fallback to pattern matching
                if not ai_available:
                    logger.info(f"Using pattern matching for: {user_input}")
                    insights_response = mcp_client.get_business_insights(user_input)
                    
                    if insights_response and "insights" in insights_response:
                        insights = insights_response["insights"]
                        
                        if insights:
                            response = "Here's what I found:\n\n"
                            for insight in insights[:3]:  # Limit to top 3 insights
                                response += f"**{insight['title']}**\n"
                                response += f"{insight['description']}\n\n"
                                
                                # Add metrics if available
                                if insight.get('metrics'):
                                    response += "📊 **Key Metrics:**\n"
                                    for metric in insight['metrics']:
                                        response += f"- {metric}\n"
                                    response += "\n"
                                
                                # Add recommendations if available
                                if insight.get('recommendations'):
                                    response += "💡 **Recommendations:**\n"
                                    for rec in insight['recommendations'][:2]:
                                        response += f"- {rec}\n"
                                    response += "\n"
                        else:
                            # Fallback to SQL generation
                            sql_prompt = mcp_client.generate_sql_prompt(user_input)
                            
                            if sql_prompt:
                                response = f"I can help you with that question. Here's a suggested approach:\n\n{sql_prompt}"
                            else:
                                response = "I couldn't understand your question. Please try asking about revenue, customers, or products."
                    else:
                        response = "I'm having trouble accessing the analytics engine. Please try again."
                    
                    # Add response to history
                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                    
                    # Rerun to display new messages
                    st.rerun()
                
            except Exception as e:
                logger.error(f"Error in AI copilot: {e}", exc_info=True)
                st.error(f"Error generating response: {str(e)}")

def render_advanced_analytics():
    """Render advanced analytics with multiple chart types"""
    st.markdown("## 📈 Advanced Analytics")
    st.markdown("*Deep-dive analytics with interactive visualizations*")
    
    # Analytics tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Cohort Analysis", "🎯 Customer Segmentation", "📦 Product Performance", "🔄 Journey Analytics"])
    
    with tab1:
        render_cohort_analysis()
    
    with tab2:
        render_customer_segmentation()
    
    with tab3:
        render_product_performance()
    
    with tab4:
        render_journey_analytics()

def render_cohort_analysis():
    """Render cohort analysis dashboard"""
    st.markdown("### 📊 Customer Cohort Analysis")
    
    with st.spinner("Loading cohort data..."):
        try:
            # Query cohort data directly
            cohort_query = """
            SELECT 
                cohort_month,
                period_number,
                retention_rate,
                cohort_health,
                estimated_annual_ltv
            FROM main.fct_cohort_analysis
            WHERE cohort_type = 'monthly'
              AND period_number <= 12
            ORDER BY cohort_month, period_number
            """
            
            cohort_result = mcp_client.execute_query(cohort_query)
            
            if cohort_result and cohort_result.get("success") and cohort_result.get("data", {}).get("rows"):
                cohorts = cohort_result["data"]["rows"]
                
                if cohorts:
                    df = pd.DataFrame(cohorts)
                    
                    # Create cohort heatmap
                    fig = visualizer.create_cohort_heatmap(df)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Cohort summary table
                    st.markdown("#### Cohort Summary")
                    summary_df = df.groupby('cohort_month').agg({
                        'retention_rate': 'mean',
                        'cohort_health': 'first',
                        'estimated_annual_ltv': 'mean'
                    }).round(2)
                    
                    st.dataframe(summary_df, use_container_width=True)
                else:
                    st.info("No cohort data available")
            else:
                st.info("No cohort data available yet. Please ensure the dbt pipeline has run.")
                
        except Exception as e:
            st.error(f"Error loading cohort analysis: {str(e)}")

def render_customer_segmentation():
    """Render customer segmentation analysis"""
    st.markdown("### 🎯 Customer Segmentation")
    
    with st.spinner("Loading customer segments..."):
        try:
            customer_data = mcp_client.get_customer_segments()
            
            if customer_data and "segments" in customer_data:
                segments = customer_data["segments"]
                
                if segments:
                    df = pd.DataFrame(segments)
                    
                    # Customer segment distribution
                    fig = visualizer.create_segment_distribution(df)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Segment metrics table
                    st.markdown("#### Segment Metrics")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No customer segment data available")
            else:
                st.error("Failed to load customer data")
                
        except Exception as e:
            st.error(f"Error loading customer segmentation: {str(e)}")

def render_product_performance():
    """Render product performance analysis"""
    st.markdown("### 📦 Product Performance Analysis")
    
    with st.spinner("Loading product data..."):
        try:
            product_data = mcp_client.get_product_performance()
            
            if product_data and "top_products" in product_data:
                products = product_data["top_products"]
                
                if products:
                    df = pd.DataFrame(products)
                    
                    # Product performance chart
                    fig = visualizer.create_product_performance_chart(df)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Top products table
                    st.markdown("#### Top Performing Products")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No product data available")
            else:
                st.error("Failed to load product data")
                
        except Exception as e:
            st.error(f"Error loading product performance: {str(e)}")

def render_journey_analytics():
    """Render customer journey analytics"""
    st.markdown("### 🔄 Customer Journey Analytics")
    
    with st.spinner("Loading customer journey data..."):
        try:
            # Query customer journey data
            journey_query = """
            SELECT 
                journey_stage,
                COUNT(*) as event_count,
                COUNT(DISTINCT customer_fk) as unique_customers,
                AVG(journey_efficiency_score) as avg_efficiency
            FROM main.fct_customer_journey
            GROUP BY journey_stage
            ORDER BY event_count DESC
            """
            
            journey_result = mcp_client.execute_query(journey_query)
            
            if journey_result and journey_result.get("success") and journey_result.get("data", {}).get("rows"):
                df = pd.DataFrame(journey_result["data"]["rows"])
                
                # Journey funnel chart
                fig = px.funnel(
                    df, 
                    x='event_count', 
                    y='journey_stage',
                    title="Customer Journey Funnel"
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)
                
                # Journey metrics table
                st.markdown("#### Journey Stage Metrics")
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No customer journey data available yet. Please ensure the dbt pipeline has run.")
                
        except Exception as e:
            st.error(f"Error loading journey analytics: {str(e)}")

def render_data_explorer():
    """Render interactive data explorer"""
    st.markdown("## 🔍 Data Explorer")
    st.markdown("*Explore your data with interactive queries and visualizations*")
    
    # Get available tables
    with st.spinner("Loading database schema..."):
        try:
            available_tables = mcp_client.get_database_tables()
            if not available_tables:
                available_tables = ["main.dim_customers", "main.fct_monthly_revenue", "main.fct_product_performance"]
        except:
            available_tables = ["main.dim_customers", "main.fct_monthly_revenue", "main.fct_product_performance"]
    
    # Table selector
    selected_table = st.selectbox("Select a table to explore:", available_tables)
    
    if selected_table:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Sample data
            st.markdown(f"### 📊 Sample Data from {selected_table}")
            with st.spinner("Loading sample data..."):
                try:
                    sample_query = f"SELECT * FROM {selected_table} LIMIT 10"
                    sample_result = mcp_client.execute_query(sample_query)
                    
                    if sample_result and sample_result.get("success") and sample_result.get("data", {}).get("rows"):
                        df = pd.DataFrame(sample_result["data"]["rows"])
                        st.dataframe(df, use_container_width=True)
                    else:
                        st.info("No data available in this table.")
                except Exception as e:
                    st.error(f"Error loading sample data: {str(e)}")
        
        with col2:
            # Table statistics
            st.markdown("### 📈 Table Statistics")
            with st.spinner("Loading statistics..."):
                try:
                    stats_query = f"SELECT COUNT(*) as row_count FROM {selected_table}"
                    stats_result = mcp_client.execute_query(stats_query)
                    
                    if stats_result and stats_result.get("success") and stats_result.get("data", {}).get("rows"):
                        row_count = stats_result["data"]["rows"][0]["row_count"]
                        st.metric("Total Rows", f"{row_count:,}")
                    
                    # Column count
                    if 'df' in locals() and not df.empty:
                        st.metric("Columns", len(df.columns))
                        
                        # Column types
                        st.markdown("**Column Types:**")
                        for col, dtype in df.dtypes.items():
                            st.text(f"• {col}: {dtype}")
                            
                except Exception as e:
                    st.error(f"Error loading statistics: {str(e)}")
    
    # Custom query section
    st.markdown("---")
    st.markdown("### 🔧 Custom Query")
    
    # Query examples
    with st.expander("📝 Query Examples"):
        st.code("""
-- Top customers by revenue
SELECT customer_name, SUM(lifetime_revenue) as total_revenue
FROM main.dim_customers 
GROUP BY customer_name
ORDER BY total_revenue DESC 
LIMIT 10;

-- Monthly revenue trend
SELECT order_year, order_month, SUM(total_revenue) as revenue
FROM main.fct_monthly_revenue 
GROUP BY order_year, order_month 
ORDER BY order_year, order_month;

-- Product performance by category
SELECT category, COUNT(*) as product_count, AVG(total_revenue) as avg_revenue
FROM main.fct_product_performance 
GROUP BY category 
ORDER BY avg_revenue DESC;
        """)
    
    # Query input
    custom_query = st.text_area(
        "Enter your SQL query:",
        height=150,
        placeholder="SELECT * FROM main.dim_customers LIMIT 10;"
    )
    
    col1, col2 = st.columns([1, 4])
    with col1:
        execute_query = st.button("🚀 Execute Query", type="primary")
    with col2:
        limit_results = st.number_input("Limit results", min_value=1, max_value=1000, value=100)
    
    if execute_query and custom_query.strip():
        with st.spinner("Executing query..."):
            try:
                # Add limit if not present
                if "LIMIT" not in custom_query.upper():
                    custom_query = f"{custom_query.rstrip(';')} LIMIT {limit_results}"
                
                result = mcp_client.execute_query(custom_query)
                
                if result and result.get("success") and result.get("data", {}).get("rows"):
                    df = pd.DataFrame(result["data"]["rows"])
                    
                    st.success(f"Query executed successfully! Found {len(df)} rows.")
                    st.dataframe(df, use_container_width=True)
                    
                    # Download option
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download as CSV",
                        data=csv,
                        file_name="query_results.csv",
                        mime="text/csv"
                    )
                elif result and result.get("success"):
                    st.info("Query executed successfully but returned no results.")
                else:
                    error_msg = result.get("error", "Unknown error") if result else "Query execution failed"
                    st.error(f"Query execution failed: {error_msg}")
                    
            except Exception as e:
                st.error(f"Error executing query: {str(e)}")

def render_customer_intelligence():
    """Render customer intelligence dashboard"""
    st.markdown("## 🎯 Customer Intelligence Dashboard")
    st.markdown("*Deep insights into customer behavior, segmentation, and lifetime value*")
    
    # Customer overview metrics
    with st.spinner("Loading customer intelligence..."):
        try:
            customer_data = mcp_client.get_customer_segments()
            
            if customer_data and "segments" in customer_data:
                segments = customer_data["segments"]
                
                # Customer segment distribution
                if segments:
                    st.markdown("### 🎯 Customer Segmentation")
                    
                    segments_df = pd.DataFrame(segments)
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Segment pie chart
                        fig = px.pie(
                            segments_df, 
                            values='customer_count', 
                            names='customer_segment',
                            title="Customer Distribution by Segment"
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        # Segment value chart
                        fig = px.bar(
                            segments_df, 
                            x='customer_segment', 
                            y='avg_lifetime_revenue',
                            title="Average Lifetime Value by Segment"
                        )
                        fig.update_xaxes(tickangle=45)
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # Segment details table
                    st.markdown("#### Customer Segment Details")
                    st.dataframe(segments_df, use_container_width=True)
                
                else:
                    st.info("Customer segmentation data is not available yet.")
            
            # Customer lifecycle analysis
            st.markdown("---")
            st.markdown("### 📊 Customer Lifecycle Analysis")
            
            lifecycle_query = """
            SELECT 
                CASE 
                    WHEN days_since_last_order <= 30 THEN 'Active (0-30 days)'
                    WHEN days_since_last_order <= 90 THEN 'At Risk (31-90 days)'
                    WHEN days_since_last_order <= 180 THEN 'Dormant (91-180 days)'
                    ELSE 'Lost (180+ days)'
                END as lifecycle_stage,
                COUNT(*) as customer_count,
                AVG(lifetime_revenue) as avg_revenue
            FROM main.dim_customers
            GROUP BY lifecycle_stage
            ORDER BY customer_count DESC
            """
            
            lifecycle_result = mcp_client.execute_query(lifecycle_query)
            
            if lifecycle_result and lifecycle_result.get("success") and lifecycle_result.get("data", {}).get("rows"):
                lifecycle_df = pd.DataFrame(lifecycle_result["data"]["rows"])
                
                col1, col2 = st.columns(2)
                
                with col1:
                    fig = px.bar(
                        lifecycle_df, 
                        x='lifecycle_stage', 
                        y='customer_count',
                        title="Customer Count by Lifecycle Stage",
                        color='lifecycle_stage'
                    )
                    fig.update_xaxes(tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    fig = px.bar(
                        lifecycle_df, 
                        x='lifecycle_stage', 
                        y='avg_revenue',
                        title="Average Revenue by Lifecycle Stage",
                        color='lifecycle_stage'
                    )
                    fig.update_xaxes(tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)
            
        except Exception as e:
            st.error(f"Error loading customer intelligence: {str(e)}")

def render_product_performance_dashboard():
    """Render dedicated product performance dashboard"""
    st.markdown("## 📦 Product Performance Dashboard")
    st.markdown("*Comprehensive product analytics, trends, and optimization insights*")
    
    with st.spinner("Loading product performance data..."):
        try:
            product_data = mcp_client.get_product_performance()
            
            if product_data and "data" in product_data:
                data = product_data["data"]
                
                if "top_products" in data and data["top_products"]:
                    products_df = pd.DataFrame(data["top_products"])
                    
                    # Product performance overview
                    st.markdown("### 🏆 Top Performing Products")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        total_products = len(products_df)
                        st.metric("Total Products", total_products)
                    
                    with col2:
                        total_revenue = products_df['revenue'].sum()
                        st.metric("Total Revenue", f"${total_revenue:,.2f}")
                    
                    with col3:
                        avg_revenue = products_df['revenue'].mean()
                        st.metric("Avg Revenue per Product", f"${avg_revenue:,.2f}")
                    
                    # Product performance charts
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Top products by revenue
                        top_10 = products_df.head(10)
                        fig = px.bar(
                            top_10, 
                            x='revenue', 
                            y='product_name',
                            title="Top 10 Products by Revenue",
                            orientation='h'
                        )
                        fig.update_layout(height=500)
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        # Performance tier distribution
                        tier_counts = products_df['performance_tier'].value_counts()
                        fig = px.pie(
                            values=tier_counts.values, 
                            names=tier_counts.index,
                            title="Product Distribution by Performance Tier"
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # Category performance
                    if 'category' in products_df.columns:
                        st.markdown("### 📊 Category Performance")
                        category_stats = products_df.groupby('category').agg({
                            'revenue': ['sum', 'mean', 'count']
                        }).round(2)
                        category_stats.columns = ['Total Revenue', 'Avg Revenue', 'Product Count']
                        category_stats = category_stats.sort_values('Total Revenue', ascending=False)
                        
                        st.dataframe(category_stats, use_container_width=True)
                    
                    # Detailed product table
                    st.markdown("### 📋 Product Performance Details")
                    st.dataframe(products_df, use_container_width=True)
                
                else:
                    st.info("Product performance data is not available yet.")
            
        except Exception as e:
            st.error(f"Error loading product performance dashboard: {str(e)}")

def main():
    """Main application entry point"""
    # Render header
    render_main_header()
    
    # Render sidebar and get navigation choice
    nav_option = render_sidebar()
    
    # Route to appropriate page
    if nav_option == "🏠 Executive Dashboard":
        render_executive_dashboard()
    elif nav_option == "🤖 AI Copilot":
        render_ai_copilot()
    elif nav_option == "📈 Advanced Analytics":
        render_advanced_analytics()
    elif nav_option == "🔍 Data Explorer":
        render_data_explorer()
    elif nav_option == "🎯 Customer Intelligence":
        render_customer_intelligence()
    elif nav_option == "📦 Product Performance":
        render_product_performance_dashboard()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #64748b; font-size: 0.85rem; padding: 1rem;">
        🚀 A-Commerce v1.0 | Built with ❤️ using Streamlit, Clickhouse & AI
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()