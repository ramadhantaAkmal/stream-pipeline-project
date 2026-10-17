from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import streamlit as st

@dataclass
class AppState:
    # Schema exploration
    selected_schema: str = "ecom_warehouse"
    selected_table: Optional[str] = None
    table_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Chat
    messages: List[Dict] = field(default_factory=list)
    chat_history: List[Dict] = field(default_factory=list)
    
    # Dashboard
    current_dashboard: Optional[str] = None
    dashboard_widgets: List[Dict] = field(default_factory=list)
    
    # UI State
    active_tab: str = "chat"  # "chat" | "dashboard" | "explore"
    sidebar_collapsed: bool = False

def get_app_state() -> AppState:
    if "app_state" not in st.session_state:
        st.session_state.app_state = AppState()
    return st.session_state.app_state