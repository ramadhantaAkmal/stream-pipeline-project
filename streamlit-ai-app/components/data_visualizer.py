import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional

class AdvancedDataVisualizer:
    """Advanced data visualization components for business analytics"""
    
    def __init__(self):
        self.theme_colors = {
            "primary": "#667eea",
            "secondary": "#764ba2",
            "success": "#10b981",
            "warning": "#f59e0b",
            "error": "#ef4444",
            "info": "#3b82f6"
        }
        
        self.color_palette = [
            "#667eea", "#764ba2", "#10b981", "#f59e0b", "#ef4444",
            "#8b5cf6", "#06b6d4", "#84cc16", "#f97316", "#ec4899"
        ]
    
    def create_revenue_trend_chart(self, df: pd.DataFrame) -> go.Figure:
        """Create an advanced revenue trend chart"""
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('Revenue Trend', 'Customer Growth'),
            vertical_spacing=0.1,
            row_heights=[0.7, 0.3]
        )
        
        # Revenue trend line
        fig.add_trace(
            go.Scatter(
                x=df['month'],
                y=df['revenue'],
                mode='lines+markers',
                name='Revenue',
                line=dict(color=self.theme_colors["primary"], width=3),
                marker=dict(size=8, color=self.theme_colors["primary"]),
                fill='tonexty',
                fillcolor=f"rgba(102, 126, 234, 0.1)"
            ),
            row=1, col=1
        )
        
        # Customer count bars
        if 'customers' in df.columns:
            fig.add_trace(
                go.Bar(
                    x=df['month'],
                    y=df['customers'],
                    name='Customers',
                    marker_color=self.theme_colors["success"],
                    opacity=0.7
                ),
                row=2, col=1
            )
        
        fig.update_layout(
            title="Revenue & Customer Trends",
            showlegend=True,
            height=500,
            template="plotly_white",
            font=dict(family="Inter, sans-serif"),
            hovermode='x unified'
        )
        
        fig.update_xaxes(title_text="Month", row=2, col=1)
        fig.update_yaxes(title_text="Revenue ($)", row=1, col=1)
        fig.update_yaxes(title_text="Customers", row=2, col=1)
        
        return fig
    
    def create_cohort_heatmap(self, df: pd.DataFrame) -> go.Figure:
        """Create a cohort retention heatmap"""
        # Pivot data for heatmap
        pivot_df = df.pivot(index='cohort_month', columns='period_number', values='retention_rate')
        
        fig = go.Figure(data=go.Heatmap(
            z=pivot_df.values,
            x=[f"Month {i}" for i in pivot_df.columns],
            y=pivot_df.index,
            colorscale='RdYlGn',
            text=pivot_df.values,
            texttemplate="%{text:.1f}%",
            textfont={"size": 10},
            colorbar=dict(title="Retention Rate (%)")
        ))
        
        fig.update_layout(
            title="Customer Cohort Retention Heatmap",
            xaxis_title="Period After Acquisition",
            yaxis_title="Acquisition Cohort",
            height=400,
            template="plotly_white",
            font=dict(family="Inter, sans-serif")
        )
        
        return fig
    
    def create_segment_distribution(self, df: pd.DataFrame) -> go.Figure:
        """Create customer segment distribution chart"""
        fig = make_subplots(
            rows=1, cols=2,
            specs=[[{"type": "domain"}, {"type": "xy"}]],
            subplot_titles=('Segment Distribution', 'Average CLV by Segment')
        )
        
        # Pie chart for segment distribution
        fig.add_trace(
            go.Pie(
                labels=df['customer_segment'],
                values=df['customer_count'],
                hole=0.4,
                marker_colors=self.color_palette[:len(df)],
                textinfo='label+percent',
                textposition='outside'
            ),
            row=1, col=1
        )
        
        # Bar chart for CLV
        if 'avg_clv' in df.columns:
            fig.add_trace(
                go.Bar(
                    x=df['customer_segment'],
                    y=df['avg_clv'],
                    marker_color=self.color_palette[:len(df)],
                    text=df['avg_clv'].round(2),
                    textposition='auto'
                ),
                row=1, col=2
            )
        
        fig.update_layout(
            title="Customer Segmentation Analysis",
            showlegend=False,
            height=400,
            template="plotly_white",
            font=dict(family="Inter, sans-serif")
        )
        
        return fig
    
    def create_product_performance_chart(self, df: pd.DataFrame) -> go.Figure:
        """
        Create product performance bubble chart with BCG Matrix-style quadrants.
        
        Uses revenue_last_30d from fct_product_performance to calculate recent performance metrics.
        Falls back to alternative metrics if revenue_last_30d is not available.
        
        Args:
            df: DataFrame with product performance data including columns:
                - revenue (required): Total product revenue
                - product_name (optional): Product names for labels
                - revenue_last_30d (optional): Recent 30-day revenue
                - days_since_last_sale (optional): Days since last sale
                - total_orders (optional): Total order count
        
        Returns:
            Plotly Figure object with bubble chart visualization
        """
        fig = go.Figure()
        
        # Validate input data
        if df is None or len(df) == 0:
            fig.add_annotation(
                text="No product data available",
                xref="paper", yref="paper",
                x=0.5, y=0.5,
                showarrow=False,
                font=dict(size=16, color="gray")
            )
            fig.update_layout(
                title="Product Performance Analysis",
                xaxis_title="Revenue ($)",
                yaxis_title="Performance Metric",
                height=500,
                template="plotly_white"
            )
            return fig
        
        # Ensure revenue column exists
        if 'revenue' not in df.columns:
            fig.add_annotation(
                text="Error: 'revenue' column not found in data",
                xref="paper", yref="paper",
                x=0.5, y=0.5,
                showarrow=False,
                font=dict(size=16, color="red")
            )
            fig.update_layout(
                title="Product Performance Analysis - Data Error",
                height=500,
                template="plotly_white"
            )
            return fig
        
        # Create working copy of dataframe
        df_copy = df.copy()
        
        # Determine which metric to use for Y-axis based on available columns
        # Priority: revenue_last_30d > days_since_last_sale > total_orders > revenue
        if 'revenue_last_30d' in df_copy.columns and 'revenue' in df_copy.columns:
            # Calculate percentage of recent revenue vs total revenue
            # This shows which products are currently performing well vs their lifetime performance
            df_copy['recent_performance_pct'] = (
                (df_copy['revenue_last_30d'] / df_copy['revenue'].replace(0, 1)) * 100
            ).fillna(0).clip(upper=100)
            
            y_column = 'recent_performance_pct'
            y_title = "Recent Performance (% of Total Revenue)"
            y_data = df_copy[y_column]
            
        elif 'days_since_last_sale' in df_copy.columns:
            # Invert days_since_last_sale to create a positive recency metric
            # Lower days = better (more recent) = higher score
            df_copy['recency_score'] = (90 - df_copy['days_since_last_sale']).clip(lower=0, upper=90)
            
            y_column = 'recency_score'
            y_title = "Recency Score (0-90 days)"
            y_data = df_copy[y_column]
            
        elif 'total_orders' in df_copy.columns:
            # Fallback to total_orders as a performance metric
            y_column = 'total_orders'
            y_title = "Total Orders"
            y_data = df_copy[y_column]
            
        else:
            # Final fallback: use revenue for both axes (creates diagonal line pattern)
            # Not ideal but prevents errors when data structure is unexpected
            y_column = 'revenue'
            y_title = "Revenue (Duplicate)"
            y_data = df_copy['revenue']
        
        # Create bubble chart with proper marker sizing
        # Calculate marker sizes based on revenue with proper scaling
        revenue_values = df_copy['revenue'].clip(lower=0)
        
        # Normalize sizes to a reasonable range (10-50 pixels)
        # Use square root to prevent very large bubbles from dominating
        if revenue_values.max() > 0:
            # Calculate size array with proper scaling
            size_array = np.sqrt(revenue_values)
            
            # Normalize to 10-50 range
            size_min = 10
            size_max = 50
            size_range = size_max - size_min
            
            # Scale sizes proportionally
            if size_array.max() > size_array.min():
                normalized_sizes = (
                    (size_array - size_array.min()) / 
                    (size_array.max() - size_array.min())
                ) * size_range + size_min
            else:
                # All values are the same, use middle size
                normalized_sizes = np.full(len(size_array), (size_min + size_max) / 2)
        else:
            # No revenue data, use default size
            normalized_sizes = np.full(len(revenue_values), 20)
        
        fig.add_trace(go.Scatter(
            x=df_copy['revenue'],
            y=y_data,
            mode='markers',
            marker=dict(
                size=normalized_sizes,  # Pre-calculated normalized sizes
                color=y_data,
                colorscale='RdYlGn',
                showscale=True,
                colorbar=dict(title=y_title),
                sizemode='diameter',  # Interpret size values as diameters in pixels
                line=dict(width=2, color='white'),
                opacity=0.7
            ),
            text=df_copy['product_name'] if 'product_name' in df_copy.columns else df_copy.index,
            hovertemplate=(
                "<b>%{text}</b><br>" +
                "Revenue: $%{x:,.0f}<br>" +
                f"{y_title}: %{{y:.1f}}<br>" +
                "<extra></extra>"
            )
        ))
        
        # Add quadrant lines at median values
        median_revenue = df_copy['revenue'].median()
        median_y = y_data.median()
        
        fig.add_hline(y=median_y, line_dash="dash", line_color="gray", opacity=0.5)
        fig.add_vline(x=median_revenue, line_dash="dash", line_color="gray", opacity=0.5)
        
        # Add quadrant labels for BCG-style matrix
        max_revenue = df_copy['revenue'].max()
        max_y = y_data.max()
        
        # Only add labels if we have valid data
        if max_revenue > 0 and max_y > 0:
            # BCG Matrix quadrant labels
            fig.add_annotation(
                x=max_revenue * 0.8,
                y=max_y * 0.8,
                text="Stars",
                showarrow=False,
                font=dict(size=14, color="green")
            )
            
            fig.add_annotation(
                x=max_revenue * 0.2,
                y=max_y * 0.8,
                text="Question Marks",
                showarrow=False,
                font=dict(size=14, color="orange")
            )
            
            fig.add_annotation(
                x=max_revenue * 0.8,
                y=max_y * 0.2,
                text="Cash Cows",
                showarrow=False,
                font=dict(size=14, color="blue")
            )
            
            fig.add_annotation(
                x=max_revenue * 0.2,
                y=max_y * 0.2,
                text="Dogs",
                showarrow=False,
                font=dict(size=14, color="red")
            )
        
        fig.update_layout(
            title="Product Performance Matrix",
            xaxis_title="Revenue ($)",
            yaxis_title=y_title,  # Use dynamic y-axis title based on available data
            height=500,
            template="plotly_white",
            font=dict(family="Inter, sans-serif")
        )
        
        return fig
    
    def create_funnel_chart(self, stages: List[str], values: List[int]) -> go.Figure:
        """Create a conversion funnel chart"""
        fig = go.Figure(go.Funnel(
            y=stages,
            x=values,
            textinfo="value+percent initial",
            marker=dict(
                color=self.color_palette[:len(stages)],
                line=dict(width=2, color="white")
            )
        ))
        
        fig.update_layout(
            title="Conversion Funnel",
            height=400,
            template="plotly_white",
            font=dict(family="Inter, sans-serif")
        )
        
        return fig
    
    def create_geographic_distribution(self, df: pd.DataFrame) -> go.Figure:
        """Create geographic distribution chart"""
        if 'country' in df.columns and 'value' in df.columns:
            fig = go.Figure(data=go.Choropleth(
                locations=df['country'],
                z=df['value'],
                locationmode='country names',
                colorscale='Blues',
                colorbar_title="Value"
            ))
            
            fig.update_layout(
                title="Geographic Distribution",
                geo=dict(showframe=False, showcoastlines=True),
                height=400
            )
        else:
            # Fallback to bar chart
            fig = px.bar(
                df, 
                x='region' if 'region' in df.columns else df.columns[0],
                y='value' if 'value' in df.columns else df.columns[1],
                title="Regional Distribution"
            )
        
        return fig
    
    def create_time_series_forecast(self, df: pd.DataFrame, forecast_periods: int = 12) -> go.Figure:
        """Create time series with forecast"""
        fig = go.Figure()
        
        # Historical data
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['value'],
            mode='lines+markers',
            name='Historical',
            line=dict(color=self.theme_colors["primary"], width=2)
        ))
        
        # Simple linear forecast (in production, use proper forecasting models)
        if len(df) > 3:
            try:
                from sklearn.linear_model import LinearRegression
                import datetime as dt
                
                # Prepare data for forecasting
                df['date_numeric'] = pd.to_datetime(df['date']).astype(int) / 10**9
                X = df['date_numeric'].values.reshape(-1, 1)
                y = df['value'].values
                
                # Fit model
                model = LinearRegression()
                model.fit(X, y)
                
                # Generate forecast dates
                last_date = pd.to_datetime(df['date'].iloc[-1])
                forecast_dates = pd.date_range(
                    start=last_date + pd.DateOffset(months=1),
                    periods=forecast_periods,
                    freq='M'
                )
                
                # Generate predictions
                forecast_numeric = pd.to_datetime(forecast_dates).astype(int) / 10**9
                forecast_values = model.predict(forecast_numeric.values.reshape(-1, 1))
                
                # Add forecast trace
                fig.add_trace(go.Scatter(
                    x=forecast_dates,
                    y=forecast_values,
                    mode='lines+markers',
                    name='Forecast',
                    line=dict(color=self.theme_colors["warning"], width=2, dash='dash')
                ))
            except ImportError:
                # Fallback to simple trend line if sklearn is not available
                last_date = pd.to_datetime(df['date'].iloc[-1])
                forecast_dates = pd.date_range(
                    start=last_date + pd.DateOffset(months=1),
                    periods=forecast_periods,
                    freq='M'
                )
                
                # Simple linear trend
                trend = np.polyfit(range(len(df)), df['value'], 1)
                forecast_values = [trend[0] * (len(df) + i) + trend[1] for i in range(1, forecast_periods + 1)]
                
                fig.add_trace(go.Scatter(
                    x=forecast_dates,
                    y=forecast_values,
                    mode='lines+markers',
                    name='Trend',
                    line=dict(color=self.theme_colors["warning"], width=2, dash='dash')
                ))
        
        fig.update_layout(
            title="Time Series with Forecast",
            xaxis_title="Date",
            yaxis_title="Value",
            height=400,
            template="plotly_white",
            font=dict(family="Inter, sans-serif"),
            showlegend=True
        )
        
        return fig
    
    def create_kpi_dashboard(self, kpis: List[Dict[str, Any]]) -> go.Figure:
        """Create a KPI dashboard with multiple metrics"""
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=[kpi['title'] for kpi in kpis[:4]],
            specs=[[{"type": "indicator"}, {"type": "indicator"}],
                   [{"type": "indicator"}, {"type": "indicator"}]]
        )
        
        positions = [(1, 1), (1, 2), (2, 1), (2, 2)]
        
        for i, kpi in enumerate(kpis[:4]):
            row, col = positions[i]
            
            fig.add_trace(
                go.Indicator(
                    mode="number+delta+gauge",
                    value=kpi['value'],
                    delta={'reference': kpi.get('target', kpi['value'] * 0.9)},
                    gauge={
                        'axis': {'range': [None, kpi.get('max_value', kpi['value'] * 1.2)]},
                        'bar': {'color': self.theme_colors["primary"]},
                        'steps': [
                            {'range': [0, kpi.get('target', kpi['value'] * 0.9)], 'color': "lightgray"},
                            {'range': [kpi.get('target', kpi['value'] * 0.9), kpi.get('max_value', kpi['value'] * 1.2)], 'color': "gray"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': kpi.get('threshold', kpi['value'] * 1.1)
                        }
                    },
                    title={'text': kpi['title']},
                    number={'suffix': kpi.get('suffix', '')}
                ),
                row=row, col=col
            )
        
        fig.update_layout(
            height=600,
            template="plotly_white",
            font=dict(family="Inter, sans-serif")
        )
        
        return fig
    
    def create_correlation_matrix(self, df: pd.DataFrame) -> go.Figure:
        """Create correlation matrix heatmap"""
        # Calculate correlation matrix
        corr_matrix = df.select_dtypes(include=[np.number]).corr()
        
        fig = go.Figure(data=go.Heatmap(
            z=corr_matrix.values,
            x=corr_matrix.columns,
            y=corr_matrix.columns,
            colorscale='RdBu',
            zmid=0,
            text=corr_matrix.round(2).values,
            texttemplate="%{text}",
            textfont={"size": 10},
            colorbar=dict(title="Correlation")
        ))
        
        fig.update_layout(
            title="Correlation Matrix",
            height=500,
            template="plotly_white",
            font=dict(family="Inter, sans-serif")
        )
        
        return fig