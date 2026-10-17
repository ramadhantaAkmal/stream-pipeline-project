import streamlit as st
import pandas as pd
from typing import Dict, List, Any, Optional

class DashboardManager:
    def __init__(self, mcp_client):
        self.mcp_client = mcp_client
        self.available_widgets = {
            "line_chart": self._render_line_chart,
            "bar_chart": self._render_bar_chart,
            "metric": self._render_metric,
            "table": self._render_table
        }
    
    def render_dashboard(self, dashboard_config: Dict):
        """Render a complete dashboard from config"""
        if not dashboard_config:
            st.warning("No dashboard configuration found")
            return
        
        # Dashboard title and description
        st.title(dashboard_config.get("title", "Dashboard"))
        if "description" in dashboard_config:
            st.markdown(dashboard_config["description"])
        
        # Render each widget in a grid
        columns = st.columns(dashboard_config.get("columns", 2))
        
        for i, widget in enumerate(dashboard_config.get("widgets", [])):
            with columns[i % len(columns)]:
                self._render_widget(widget)
    
    def _render_widget(self, widget_config: Dict):
        """Render a single widget based on its type"""
        widget_type = widget_config.get("type")
        render_func = self.available_widgets.get(widget_type)
        
        if not render_func:
            st.warning(f"Unknown widget type: {widget_type}")
            return
        
        with st.container():
            # Widget header
            st.subheader(widget_config.get("title", ""))
            
            # Add some spacing
            st.write("")
            
            # Fetch and render data
            with st.spinner("Loading data..."):
                try:
                    # Fetch data
                    query = widget_config.get("query")
                    if not query:
                        st.error("No query specified for widget")
                        return
                    
                    result = self.mcp_client.execute_query(query)
                    if "error" in result:
                        st.error(result["error"])
                        return
                    
                    # Render widget with data
                    render_func(result, widget_config)
                    
                except Exception as e:
                    st.error(f"Failed to render widget: {str(e)}")
    
    # Widget renderers
    def _render_line_chart(self, data: Dict, config: Dict):
        """Render a line chart widget"""
        df = pd.DataFrame(data.get("rows", []), columns=data.get("columns", []))
        if not df.empty:
            x_axis = config.get("x_axis")
            y_axis = config.get("y_axis")
            
            if not x_axis or not y_axis:
                st.error("Missing x_axis or y_axis configuration")
                return
            
            st.line_chart(
                df.set_index(x_axis)[y_axis],
                use_container_width=True
            )
    
    def _render_bar_chart(self, data: Dict, config: Dict):
        """Render a bar chart widget"""
        df = pd.DataFrame(data.get("rows", []), columns=data.get("columns", []))
        if not df.empty:
            x_axis = config.get("x_axis")
            y_axis = config.get("y_axis")
            
            if not x_axis or not y_axis:
                st.error("Missing x_axis or y_axis configuration")
                return
            
            st.bar_chart(
                df.set_index(x_axis)[y_axis],
                use_container_width=True
            )
    
    def _render_metric(self, data: Dict, config: Dict):
        """Render a metric widget"""
        if not data.get("rows") or len(data["rows"]) == 0:
            st.warning("No data available")
            return
        
        value = data["rows"][0][0]
        delta = None
        
        if len(data["rows"][0]) > 1:
            delta = float(data["rows"][0][1])
        
        st.metric(
            label=config.get("title", "Metric"),
            value=value,
            delta=delta
        )
    
    def _render_table(self, data: Dict, config: Dict):
        """Render a data table widget"""
        df = pd.DataFrame(data.get("rows", []), columns=data.get("columns", []))
        if df.empty:
            st.warning("No data available")
            return
        
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config=config.get("column_config", {})
        )