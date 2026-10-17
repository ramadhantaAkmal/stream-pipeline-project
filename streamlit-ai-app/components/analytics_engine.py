import streamlit as st
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json

class StreamlitAnalyticsEngine:
    """Advanced analytics engine for Streamlit applications"""
    
    def __init__(self, mcp_client):
        self.mcp_client = mcp_client
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    def get_cached_data(self, key: str) -> Optional[Any]:
        """Get cached data if still valid"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.now().timestamp() - timestamp < self.cache_ttl:
                return data
            else:
                del self.cache[key]
        return None
    
    def set_cached_data(self, key: str, data: Any):
        """Cache data with timestamp"""
        self.cache[key] = (data, datetime.now().timestamp())
    
    def get_business_metrics(self) -> Dict[str, Any]:
        """Get key business metrics"""
        cache_key = "business_metrics"
        cached = self.get_cached_data(cache_key)
        if cached:
            return cached
        
        try:
            # Get executive dashboard data
            dashboard_data = self.mcp_client.get_dashboard_data("executive")
            
            if dashboard_data and "data" in dashboard_data:
                metrics = dashboard_data["data"].get("key_metrics", {})
                
                # Calculate additional metrics
                enhanced_metrics = {
                    **metrics,
                    "conversion_rate": self._calculate_conversion_rate(),
                    "customer_acquisition_cost": self._calculate_cac(),
                    "lifetime_value": self._calculate_ltv(),
                    "churn_rate": self._calculate_churn_rate()
                }
                
                self.set_cached_data(cache_key, enhanced_metrics)
                return enhanced_metrics
            
        except Exception as e:
            st.error(f"Failed to get business metrics: {str(e)}")
            return {}
    
    def _calculate_conversion_rate(self) -> float:
        """Calculate overall conversion rate"""
        try:
            query = """
            SELECT 
                COUNT(DISTINCT CASE WHEN journey_stage = 'Purchase' THEN customer_fk END) as converters,
                COUNT(DISTINCT customer_fk) as total_visitors
            FROM main.fct_customer_journey
            """
            
            result = self.mcp_client.execute_query(query)
            if result and "data" in result and result["data"]["rows"]:
                row = result["data"]["rows"][0]
                if row["total_visitors"] > 0:
                    return (row["converters"] / row["total_visitors"]) * 100
            
        except Exception:
            pass
        
        return 0.0
    
    def _calculate_cac(self) -> float:
        """Calculate Customer Acquisition Cost (simplified)"""
        # This would typically use marketing spend data
        # For now, return a placeholder calculation
        return 25.50
    
    def _calculate_ltv(self) -> float:
        """Calculate average Customer Lifetime Value"""
        try:
            query = """
            SELECT AVG(estimated_clv) as avg_ltv
            FROM main.dim_customers
            WHERE estimated_clv IS NOT NULL
            """
            
            result = self.mcp_client.execute_query(query)
            if result and "data" in result and result["data"]["rows"]:
                return result["data"]["rows"][0]["avg_ltv"] or 0.0
            
        except Exception:
            pass
        
        return 0.0
    
    def _calculate_churn_rate(self) -> float:
        """Calculate customer churn rate"""
        try:
            query = """
            SELECT 
                COUNT(CASE WHEN customer_segment = 'Lost' THEN 1 END) as churned,
                COUNT(*) as total
            FROM main.dim_customers
            """
            
            result = self.mcp_client.execute_query(query)
            if result and "data" in result and result["data"]["rows"]:
                row = result["data"]["rows"][0]
                if row["total"] > 0:
                    return (row["churned"] / row["total"]) * 100
            
        except Exception:
            pass
        
        return 0.0
    
    def analyze_revenue_trends(self, period: str = "monthly") -> Dict[str, Any]:
        """Analyze revenue trends and patterns"""
        cache_key = f"revenue_trends_{period}"
        cached = self.get_cached_data(cache_key)
        if cached:
            return cached
        
        try:
            query = """
            SELECT 
                order_year || '-' || LPAD(order_month::TEXT, 2, '0') as period,
                SUM(total_revenue) as revenue,
                COUNT(DISTINCT customer_fk) as customers,
                SUM(total_orders) as orders,
                ROUND(SUM(total_revenue) / SUM(total_orders), 2) as avg_order_value
            FROM main.fct_monthly_revenue
            GROUP BY order_year, order_month
            ORDER BY order_year, order_month
            """
            
            result = self.mcp_client.execute_query(query)
            
            if result and "data" in result:
                df = pd.DataFrame(result["data"]["rows"])
                
                if not df.empty:
                    # Calculate growth rates
                    df['revenue_growth'] = df['revenue'].pct_change() * 100
                    df['customer_growth'] = df['customers'].pct_change() * 100
                    
                    analysis = {
                        "data": df.to_dict('records'),
                        "insights": self._generate_revenue_insights(df),
                        "summary": {
                            "total_revenue": df['revenue'].sum(),
                            "avg_monthly_revenue": df['revenue'].mean(),
                            "revenue_growth_rate": df['revenue_growth'].mean(),
                            "best_month": df.loc[df['revenue'].idxmax(), 'period'],
                            "worst_month": df.loc[df['revenue'].idxmin(), 'period']
                        }
                    }
                    
                    self.set_cached_data(cache_key, analysis)
                    return analysis
            
        except Exception as e:
            st.error(f"Failed to analyze revenue trends: {str(e)}")
        
        return {"data": [], "insights": [], "summary": {}}
    
    def _generate_revenue_insights(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Generate insights from revenue data"""
        insights = []
        
        if len(df) < 2:
            return insights
        
        # Revenue growth insight
        latest_growth = df['revenue_growth'].iloc[-1]
        avg_growth = df['revenue_growth'].mean()
        
        if not pd.isna(latest_growth) and not pd.isna(avg_growth):
            if latest_growth > avg_growth * 1.5:
                insights.append({
                    "type": "positive",
                    "title": "Accelerating Revenue Growth",
                    "description": f"Latest month shows {latest_growth:.1f}% growth vs {avg_growth:.1f}% average",
                    "recommendation": "Investigate successful strategies and scale them"
                })
            elif latest_growth < avg_growth * 0.5:
                insights.append({
                    "type": "warning",
                    "title": "Slowing Revenue Growth",
                    "description": f"Latest month shows {latest_growth:.1f}% growth vs {avg_growth:.1f}% average",
                    "recommendation": "Review recent changes and market conditions"
                })
        
        # Seasonality insight
        if len(df) >= 12:
            monthly_avg = df.groupby(df['period'].str[-2:])['revenue'].mean()
            best_month = monthly_avg.idxmax()
            worst_month = monthly_avg.idxmin()
            
            insights.append({
                "type": "info",
                "title": "Seasonal Patterns Detected",
                "description": f"Month {best_month} typically performs best, month {worst_month} worst",
                "recommendation": "Plan inventory and marketing campaigns around seasonal trends"
            })
        
        return insights
    
    def analyze_customer_segments(self) -> Dict[str, Any]:
        """Analyze customer segmentation"""
        cache_key = "customer_segments"
        cached = self.get_cached_data(cache_key)
        if cached:
            return cached
        
        try:
            query = """
            SELECT 
                customer_segment,
                COUNT(*) as customer_count,
                ROUND(AVG(lifetime_revenue), 2) as avg_lifetime_revenue,
                ROUND(AVG(estimated_clv), 2) as avg_clv,
                ROUND(AVG(days_since_last_order), 0) as avg_days_since_last_order
            FROM main.dim_customers
            GROUP BY customer_segment
            ORDER BY customer_count DESC
            """
            
            result = self.mcp_client.execute_query(query)
            
            if result and "data" in result:
                df = pd.DataFrame(result["data"]["rows"])
                
                analysis = {
                    "data": df.to_dict('records'),
                    "insights": self._generate_segment_insights(df),
                    "summary": {
                        "total_customers": df['customer_count'].sum(),
                        "segments_count": len(df),
                        "highest_value_segment": df.loc[df['avg_clv'].idxmax(), 'customer_segment'] if not df.empty else None,
                        "largest_segment": df.loc[df['customer_count'].idxmax(), 'customer_segment'] if not df.empty else None
                    }
                }
                
                self.set_cached_data(cache_key, analysis)
                return analysis
            
        except Exception as e:
            st.error(f"Failed to analyze customer segments: {str(e)}")
        
        return {"data": [], "insights": [], "summary": {}}
    
    def _generate_segment_insights(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Generate insights from customer segmentation data"""
        insights = []
        
        if df.empty:
            return insights
        
        # High-value segments
        high_value_segments = df[df['avg_clv'] > df['avg_clv'].mean() * 1.5]
        if not high_value_segments.empty:
            for _, segment in high_value_segments.iterrows():
                insights.append({
                    "type": "positive",
                    "title": f"High-Value Segment: {segment['customer_segment']}",
                    "description": f"${segment['avg_clv']:.2f} average CLV with {segment['customer_count']} customers",
                    "recommendation": "Focus retention efforts on this segment"
                })
        
        # At-risk segments
        at_risk = df[df['customer_segment'].str.contains('At Risk|Lost', case=False, na=False)]
        if not at_risk.empty:
            total_at_risk = at_risk['customer_count'].sum()
            total_value = at_risk['avg_lifetime_revenue'].sum()
            
            insights.append({
                "type": "warning",
                "title": "Customers at Risk",
                "description": f"{total_at_risk} customers at risk representing ${total_value:.2f} in potential lost revenue",
                "recommendation": "Implement win-back campaigns immediately"
            })
        
        return insights
    
    def get_product_insights(self) -> Dict[str, Any]:
        """Get product performance insights"""
        cache_key = "product_insights"
        cached = self.get_cached_data(cache_key)
        if cached:
            return cached
        
        try:
            query = """
            SELECT 
                product_name,
                category,
                performance_tier,
                ROUND(total_revenue, 2) as revenue,
                ROUND(revenue_last_30d, 2) as revenue_last_30d,
                total_units_sold,
                days_since_last_sale,
                total_orders
            FROM main.fct_product_performance
            ORDER BY total_revenue DESC
            LIMIT 50
            """
            
            result = self.mcp_client.execute_query(query)
            
            if result and "data" in result:
                df = pd.DataFrame(result["data"]["rows"])
                
                analysis = {
                    "data": df.to_dict('records'),
                    "insights": self._generate_product_insights(df),
                    "summary": {
                        "total_products": len(df),
                        "top_performer": df.iloc[0]['product_name'] if not df.empty else None,
                        "avg_revenue_last_30d": df['revenue_last_30d'].mean() if 'revenue_last_30d' in df.columns else 0,
                        "low_performing_products": len(df[df['days_since_last_sale'] > 30]) if 'days_since_last_sale' in df.columns else 0
                    }
                }
                
                self.set_cached_data(cache_key, analysis)
                return analysis
            
        except Exception as e:
            st.error(f"Failed to get product insights: {str(e)}")
        
        return {"data": [], "insights": [], "summary": {}}
    
    def _generate_product_insights(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Generate insights from product performance data"""
        insights = []
        
        if df.empty:
            return insights
        
        # Top performers
        top_products = df.head(5)
        insights.append({
            "type": "positive",
            "title": "Top Performing Products",
            "description": f"Top 5 products generate ${top_products['revenue'].sum():,.2f} in revenue",
            "recommendation": "Increase marketing focus on these high-performers"
        })
        
        # Low performing products (no recent sales)
        if 'days_since_last_sale' in df.columns:
            low_performing = df[df['days_since_last_sale'] > 30]
            if not low_performing.empty:
                insights.append({
                    "type": "warning",
                    "title": "Products with No Recent Sales",
                    "description": f"{len(low_performing)} products haven't sold in 30+ days",
                    "recommendation": "Review pricing strategy, run promotions, or consider discontinuation"
                })
        
        # Recent revenue performance
        if 'revenue_last_30d' in df.columns:
            high_recent_revenue = df[df['revenue_last_30d'] > df['revenue_last_30d'].quantile(0.75)]
            if not high_recent_revenue.empty:
                insights.append({
                    "type": "positive",
                    "title": "Strong Recent Performance",
                    "description": f"{len(high_recent_revenue)} products showing strong revenue in last 30 days",
                    "recommendation": "Invest in inventory and marketing for these trending products"
                })
        
        return insights
    
    def generate_executive_summary(self) -> Dict[str, Any]:
        """Generate executive summary with key insights"""
        try:
            # Get all analysis data
            metrics = self.get_business_metrics()
            revenue_analysis = self.analyze_revenue_trends()
            customer_analysis = self.analyze_customer_segments()
            product_analysis = self.get_product_insights()
            
            # Compile executive summary
            summary = {
                "timestamp": datetime.now().isoformat(),
                "key_metrics": metrics,
                "top_insights": [],
                "recommendations": [],
                "alerts": []
            }
            
            # Collect top insights from all analyses
            all_insights = []
            all_insights.extend(revenue_analysis.get("insights", []))
            all_insights.extend(customer_analysis.get("insights", []))
            all_insights.extend(product_analysis.get("insights", []))
            
            # Sort by type priority and take top 5
            priority_order = {"warning": 0, "positive": 1, "info": 2}
            all_insights.sort(key=lambda x: priority_order.get(x.get("type", "info"), 2))
            summary["top_insights"] = all_insights[:5]
            
            # Generate recommendations
            summary["recommendations"] = [
                insight.get("recommendation", "") 
                for insight in all_insights 
                if insight.get("recommendation")
            ][:3]
            
            # Generate alerts for urgent items
            summary["alerts"] = [
                insight for insight in all_insights 
                if insight.get("type") == "warning"
            ][:3]
            
            return summary
            
        except Exception as e:
            st.error(f"Failed to generate executive summary: {str(e)}")
            return {"timestamp": datetime.now().isoformat(), "error": str(e)}