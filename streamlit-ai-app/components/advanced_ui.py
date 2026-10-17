import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from typing import Dict, List, Any, Optional
import pandas as pd

class AdvancedUIComponents:
    """Advanced UI components for modern Streamlit applications"""
    
    def __init__(self):
        self.theme_colors = {
            "primary": "#667eea",
            "secondary": "#764ba2", 
            "success": "#10b981",
            "warning": "#f59e0b",
            "error": "#ef4444",
            "info": "#3b82f6"
        }
    
    def render_metric_card(self, title: str, value: str, change: Optional[str] = None, 
                          change_type: Optional[str] = None, icon: Optional[str] = None):
        """Render a modern metric card with optional change indicator"""
        
        change_color = ""
        change_icon = ""
        
        if change and change_type:
            if change_type == "positive":
                change_color = "color: #10b981;"
                change_icon = "↗️"
            elif change_type == "negative":
                change_color = "color: #ef4444;"
                change_icon = "↘️"
            else:
                change_color = "color: #64748b;"
                change_icon = "➡️"
        
        card_html = f"""
        <div class="metric-card">
            <div class="metric-label">{title}</div>
            <div class="metric-value">{value}</div>
            {f'<div class="metric-change" style="{change_color}">{change_icon} {change}</div>' if change else ''}
        </div>
        """
        
        st.markdown(card_html, unsafe_allow_html=True)
    
    def render_status_badge(self, status: str, text: str):
        """Render a status badge"""
        badge_class = f"status-indicator status-{status}"
        st.markdown(f'<div class="{badge_class}">{text}</div>', unsafe_allow_html=True)
    
    def render_progress_ring(self, percentage: float, title: str, color: str = "#667eea"):
        """Render a circular progress indicator"""
        fig = go.Figure(data=[
            go.Pie(
                values=[percentage, 100-percentage],
                hole=0.7,
                marker_colors=[color, "#e2e8f0"],
                showlegend=False,
                textinfo='none',
                hoverinfo='none'
            )
        ])
        
        fig.update_layout(
            annotations=[
                dict(
                    text=f"{percentage:.1f}%<br><span style='font-size:12px'>{title}</span>",
                    x=0.5, y=0.5,
                    font_size=20,
                    showarrow=False,
                    font_color=color
                )
            ],
            margin=dict(t=0, b=0, l=0, r=0),
            height=150,
            showlegend=False
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    def render_timeline(self, events: List[Dict[str, Any]]):
        """Render a timeline of events"""
        timeline_html = '<div class="timeline-container">'
        
        for i, event in enumerate(events):
            timeline_html += f"""
            <div class="timeline-item">
                <div class="timeline-marker"></div>
                <div class="timeline-content">
                    <h4>{event.get('title', 'Event')}</h4>
                    <p>{event.get('description', '')}</p>
                    <small>{event.get('timestamp', '')}</small>
                </div>
            </div>
            """
        
        timeline_html += '</div>'
        
        # Add timeline CSS
        timeline_css = """
        <style>
        .timeline-container {
            position: relative;
            padding-left: 2rem;
        }
        
        .timeline-container::before {
            content: '';
            position: absolute;
            left: 1rem;
            top: 0;
            bottom: 0;
            width: 2px;
            background: #e2e8f0;
        }
        
        .timeline-item {
            position: relative;
            margin-bottom: 2rem;
        }
        
        .timeline-marker {
            position: absolute;
            left: -2rem;
            top: 0.5rem;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #667eea;
            border: 3px solid white;
            box-shadow: 0 0 0 2px #e2e8f0;
        }
        
        .timeline-content {
            background: white;
            padding: 1rem;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        
        .timeline-content h4 {
            margin: 0 0 0.5rem 0;
            color: #1e293b;
        }
        
        .timeline-content p {
            margin: 0 0 0.5rem 0;
            color: #64748b;
        }
        
        .timeline-content small {
            color: #94a3b8;
        }
        </style>
        """
        
        st.markdown(timeline_css + timeline_html, unsafe_allow_html=True)
    
    def render_comparison_cards(self, comparisons: List[Dict[str, Any]]):
        """Render comparison cards side by side"""
        cols = st.columns(len(comparisons))
        
        for i, comparison in enumerate(comparisons):
            with cols[i]:
                current = comparison.get('current', 0)
                previous = comparison.get('previous', 0)
                change = ((current - previous) / previous * 100) if previous != 0 else 0
                
                self.render_metric_card(
                    title=comparison.get('title', 'Metric'),
                    value=str(current),
                    change=f"{change:+.1f}%",
                    change_type="positive" if change > 0 else "negative"
                )
    
    def render_alert(self, message: str, alert_type: str = "info", dismissible: bool = False):
        """Render an alert message"""
        alert_colors = {
            "info": {"bg": "#dbeafe", "border": "#3b82f6", "text": "#1e40af"},
            "success": {"bg": "#dcfce7", "border": "#10b981", "text": "#166534"},
            "warning": {"bg": "#fef3c7", "border": "#f59e0b", "text": "#d97706"},
            "error": {"bg": "#fef2f2", "border": "#ef4444", "text": "#dc2626"}
        }
        
        colors = alert_colors.get(alert_type, alert_colors["info"])
        
        alert_html = f"""
        <div style="
            background: {colors['bg']};
            border-left: 4px solid {colors['border']};
            color: {colors['text']};
            padding: 1rem;
            border-radius: 0 8px 8px 0;
            margin: 1rem 0;
            font-weight: 500;
        ">
            {message}
        </div>
        """
        
        st.markdown(alert_html, unsafe_allow_html=True)
    
    def render_loading_skeleton(self, height: int = 200):
        """Render a loading skeleton placeholder"""
        skeleton_html = f"""
        <div style="
            height: {height}px;
            background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
            background-size: 200% 100%;
            animation: loading 1.5s infinite;
            border-radius: 8px;
        "></div>
        
        <style>
        @keyframes loading {{
            0% {{ background-position: 200% 0; }}
            100% {{ background-position: -200% 0; }}
        }}
        </style>
        """
        
        st.markdown(skeleton_html, unsafe_allow_html=True)
    
    def render_feature_highlight(self, title: str, description: str, features: List[str]):
        """Render a feature highlight section"""
        feature_html = f"""
        <div style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
            border-radius: 16px;
            margin: 2rem 0;
            text-align: center;
        ">
            <h2 style="margin-bottom: 1rem; font-weight: 700;">{title}</h2>
            <p style="margin-bottom: 2rem; opacity: 0.9; font-size: 1.1rem;">{description}</p>
            <div style="display: flex; justify-content: center; flex-wrap: wrap; gap: 1rem;">
        """
        
        for feature in features:
            feature_html += f"""
                <div style="
                    background: rgba(255,255,255,0.2);
                    padding: 0.5rem 1rem;
                    border-radius: 20px;
                    font-weight: 500;
                    backdrop-filter: blur(10px);
                ">
                    ✨ {feature}
                </div>
            """
        
        feature_html += "</div></div>"
        
        st.markdown(feature_html, unsafe_allow_html=True)
    
    def render_data_quality_indicator(self, score: float, issues: List[str] = None):
        """Render data quality score with issues"""
        color = "#10b981" if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            self.render_progress_ring(score, "Data Quality", color)
        
        with col2:
            st.markdown(f"### Data Quality Score: {score:.1f}%")
            
            if issues:
                st.markdown("**Issues Found:**")
                for issue in issues:
                    st.markdown(f"• {issue}")
            else:
                st.markdown("✅ No data quality issues detected")
    
    def render_insight_card(self, insight: Dict[str, Any]):
        """Render an AI-generated insight card"""
        confidence_color = "#10b981" if insight.get('confidence', 0) >= 0.8 else "#f59e0b"
        
        insight_html = f"""
        <div style="
            background: white;
            border-radius: 12px;
            padding: 1.5rem;
            border-left: 4px solid {confidence_color};
            box-shadow: 0 4px 16px rgba(0,0,0,0.05);
            margin: 1rem 0;
        ">
            <div style="display: flex; justify-content: between; align-items: start; margin-bottom: 1rem;">
                <h4 style="margin: 0; color: #1e293b;">{insight.get('title', 'Insight')}</h4>
                <span style="
                    background: {confidence_color}20;
                    color: {confidence_color};
                    padding: 0.25rem 0.75rem;
                    border-radius: 12px;
                    font-size: 0.8rem;
                    font-weight: 600;
                ">
                    {insight.get('confidence', 0)*100:.0f}% confidence
                </span>
            </div>
            <p style="color: #64748b; margin-bottom: 1rem;">{insight.get('description', '')}</p>
        """
        
        if insight.get('recommendations'):
            insight_html += "<div><strong>💡 Recommendations:</strong><ul>"
            for rec in insight.get('recommendations', [])[:3]:
                insight_html += f"<li style='color: #64748b; margin: 0.25rem 0;'>{rec}</li>"
            insight_html += "</ul></div>"
        
        insight_html += "</div>"
        
        st.markdown(insight_html, unsafe_allow_html=True)