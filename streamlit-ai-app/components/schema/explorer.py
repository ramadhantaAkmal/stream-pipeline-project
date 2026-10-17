import streamlit as st
from typing import Dict, List, Optional, Tuple
import networkx as nx
# from streamlit_agraph import agraph, Node, Edge, Config
import json

import streamlit as st
from typing import Dict, List, Optional
import networkx as nx
from pyvis.network import Network
import tempfile
import os
import pandas as pd

class SchemaExplorer:
    def __init__(self, mcp_client):
        self.mcp_client = mcp_client
        self.schema_data = self._load_schema()
    
    def _load_schema(self) -> Dict:
        """Load schema data from MCP server"""
        try:
            return self.mcp_client.get_schema()
        except Exception as e:
            st.error(f"Failed to load schema: {str(e)}")
            return {"tables": [], "relationships": []}
    
    def render(self):
        """Render the interactive schema explorer"""
        state = st.session_state.get("app_state", {})
        
        # Schema selection
        schemas = list(set(tbl.get("schema", "public") 
                          for tbl in self.schema_data.get("tables", [])))
        selected_schema = st.selectbox(
            "Select Schema",
            schemas,
            index=0
        )
        
        # Filter tables by selected schema
        schema_tables = [
            tbl for tbl in self.schema_data.get("tables", [])
            if tbl.get("schema") == selected_schema
        ]
        
        # Table selection
        selected_table = st.selectbox(
            "Select Table",
            [""] + [tbl["name"] for tbl in schema_tables],
            format_func=lambda x: x if x else "-- Select a table --"
        )
        
        if selected_table:
            self._render_table_info(selected_table)
        
        # Schema graph
        st.subheader("Database Schema Graph")
        self._render_schema_graph(selected_schema)
    
    def _render_table_info(self, table_name: str):
        """Render detailed table information"""
        table_info = self.mcp_client.get_table_info(table_name)
        if not table_info:
            return
        
        st.subheader(f"Table: {table_name}")
        
        # Display table metadata
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Rows", table_info.get("row_count", "N/A"))
        with col2:
            st.metric("Size", f"{table_info.get('size_mb', 0):.2f} MB")
        
        # Display columns
        st.subheader("Columns")
        columns = table_info.get("columns", [])
        if columns:
            st.table(pd.DataFrame(columns))
        else:
            st.warning("No column information available")
        
        # Display sample data
        if st.button("Preview Data", key=f"preview_{table_name}"):
            result = self.mcp_client.execute_query(
                f"SELECT * FROM {table_name} LIMIT 10"
            )
            if result and "rows" in result:
                st.dataframe(
                    pd.DataFrame(
                        result["rows"],
                        columns=result.get("columns", [])
                    ),
                    use_container_width=True
                )
    
    def _render_schema_graph(self, schema: str):
            """Render interactive schema graph using pyvis"""
            # Create a directed graph
            G = nx.DiGraph()
            
            # Add tables as nodes
            for table in self.schema_data.get("tables", []):
                if table.get("schema") == schema:
                    G.add_node(
                        table["name"],
                        label=table["name"],
                        title=table["name"],
                        color="#4e79a7",
                        shape="box"
                    )
            
            # Add relationships as edges
            for rel in self.schema_data.get("relationships", []):
                if (rel.get("source_schema") == schema and 
                    rel.get("target_schema") == schema):
                    G.add_edge(
                        rel["source_table"],
                        rel["target_table"],
                        label=rel.get("constraint_name", ""),
                        arrows="to"
                    )
            
            # Create pyvis network
            net = Network(
                height="600px",
                width="100%",
                bgcolor="#ffffff",
                font_color="black",
                directed=True
            )
            
            # Convert networkx to pyvis
            net.from_nx(G)
            
            # Save to temp file and display
            with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmpfile:
                net.save_graph(tmpfile.name)
                html_string = open(tmpfile.name, 'r', encoding='utf-8').read()
                st.components.v1.html(html_string, height=600, scrolling=True)
                os.unlink(tmpfile.name)        