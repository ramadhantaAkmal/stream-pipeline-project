import streamlit as st
import pandas as pd
from typing import Dict, List, Optional, Any    
import json
from datetime import datetime

class ChatInterface:
    def __init__(self, mcp_client):
        """Initialize chat interface with MCP client only"""
        self.mcp_client = mcp_client
        self.message_handlers = {
            "text": self._render_text_message,
            "sql": self._render_sql_message,
            "data": self._render_data_message,
            "error": self._render_error_message
        }
    
    def render(self):
        """Render the chat interface"""
        # Initialize session state if needed
        if "app_state" not in st.session_state:
            st.session_state.app_state = {
                "messages": [],
                "current_table": None,
                "schema": {},
                "chat_open": True
            }
        
        # Display chat messages
        self._render_messages()
        
        # Chat input
        self._render_chat_input()
    
    def _render_messages(self):
        """Render all chat messages"""
        messages = st.session_state.app_state.get("messages", [])
        
        for msg in messages:
            with st.chat_message(msg["role"]):
                # Handle different message types
                handler = self.message_handlers.get(msg.get("type", "text"))
                if handler:
                    handler(msg)
    
    def _render_chat_input(self):
        """Render chat input and handle user messages"""
        if prompt := st.chat_input("Ask about your data..."):
            self._handle_user_message(prompt)
    
    def _handle_user_message(self, text: str):
        """Process and respond to user messages"""
        # Add user message to chat
        self._add_message("user", "text", text)
        
        # Generate and process response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    # 1. Generate SQL prompt using MCP server
                    sql_prompt = self.mcp_client.generate_sql_prompt(text)
                    if not sql_prompt:
                        raise ValueError("Failed to generate SQL prompt")
                    
                    # 2. Display the SQL prompt to help user
                    self._add_message("assistant", "text", sql_prompt)
                    
                    # 3. For now, suggest user to write SQL manually
                    # In future, this will be enhanced with full AI integration
                    suggestion = f"""
                                    💡 **AI-Powered SQL Generation Coming Soon!**

                                    Based on your question: "{text}"

                                    Please use the **Data Explorer** tab to:
                                    1. Write and execute SQL queries
                                    2. Explore your data interactively
                                    3. Create visualizations

                                    The MCP server is ready for full AI integration once the AI models are properly connected.
                                    """
                    self._add_message("assistant", "text", suggestion)
                    
                except Exception as e:
                    error_msg = str(e)
                    st.error(f"Error: {error_msg}")
                    self._add_message("assistant", "error", error_msg)
    
    # Message renderers
    def _render_text_message(self, msg: Dict):
        st.markdown(msg["content"])
    
    def _render_sql_message(self, msg: Dict):
        st.code(msg["content"], language="sql")
    
    def _render_data_message(self, msg: Dict):
        data = msg["content"].get("data", {})
        if not data or "rows" not in data:
            st.warning("No data available")
            return
        
        df = pd.DataFrame(data["rows"], columns=data.get("columns", []))
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            
            # Auto-suggest visualization
            if len(df) > 1 and len(df.columns) >= 2:
                self._suggest_visualization(df)
    
    def _render_error_message(self, msg: Dict):
        st.error(msg["content"])
    
    # Helper methods
    def _get_schema_context(self) -> str:
        """Get relevant schema information for the current context"""
        try:
            tables = self.mcp_client.get_database_tables()
            return json.dumps({
                "tables": tables,
                "message": "Schema information available via MCP server"
            })
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    def _add_message(self, role: str, msg_type: str, content: Any):
        """Add a message to the chat history"""
        if "app_state" not in st.session_state:
            st.session_state.app_state = {"messages": []}
        
        st.session_state.app_state["messages"].append({
            "role": role,
            "type": msg_type,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def _suggest_visualization(self, df: pd.DataFrame):
        """Suggest visualizations based on data"""
        if len(df) <= 1:
            return
        
        # Simple heuristic to suggest chart type
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        if len(numeric_cols) >= 2:
            st.write("### Suggested Visualization")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📈 Line Chart", use_container_width=True):
                    self._show_line_chart(df, numeric_cols[0], numeric_cols[1])
            
            with col2:
                if st.button("📊 Bar Chart", use_container_width=True):
                    self._show_bar_chart(df, numeric_cols[0], numeric_cols[1])
    
    def _show_line_chart(self, df: pd.DataFrame, x_col: str, y_col: str):
        """Display a line chart"""
        st.line_chart(
            df.set_index(x_col)[y_col],
            use_container_width=True
        )
    
    def _show_bar_chart(self, df: pd.DataFrame, x_col: str, y_col: str):
        """Display a bar chart"""
        st.bar_chart(
            df.set_index(x_col)[y_col],
            use_container_width=True
        )