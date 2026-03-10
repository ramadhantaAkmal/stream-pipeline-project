#!/usr/bin/env python3
"""
AI Service for MCP Server
=========================

This service handles all AI functionality including:
- Natural language to SQL conversion
- Business insights generation
- Data analysis and recommendations

Only the MCP server should communicate with AI services (Ollama).
"""

import logging
import os
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
import time

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AIService:
    """
    AI service that handles Ollama integration and AI-powered features
    """
    
    def __init__(self, ollama_url: str = None, model: str = "mistral"):
        self.ollama_url = ollama_url or os.getenv("OLLAMA_URL", "http://ollama:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "mistral")
        self.available = self._test_connection()
        self._model_loaded = False
        
        # Warmup: preload the model in background to avoid first-request timeout
        if self.available:
            self._warmup_model()
    
    def _test_connection(self) -> bool:
        """Test connection to Ollama server"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            response.raise_for_status()
            logger.info(f"✅ Ollama connected: {self.ollama_url}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Ollama not available: {e}")
            return False
    
    def is_available(self) -> bool:
        """Check if AI service is available"""
        return self.available
    
    def _warmup_model(self):
        """
        Warmup the model by sending a simple request to preload it into memory.
        This prevents timeout on the first real request.
        """
        try:
            logger.info(f"🔥 Warming up Ollama model: {self.model}")
            start_time = time.time()
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "Hello, this is a warmup request. Please respond with 'OK'.",
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 10
                    }
                },
                timeout=180  # Generous timeout for initial model loading
            )
            
            warmup_time = time.time() - start_time
            
            if response.status_code == 200:
                self._model_loaded = True
                logger.info(f"✅ Model {self.model} warmed up and ready in {warmup_time:.2f}s")
            else:
                logger.warning(f"⚠️ Model warmup returned status {response.status_code} after {warmup_time:.2f}s")
                
        except requests.exceptions.Timeout as e:
            logger.warning(f"⚠️ Model warmup timeout after 180s - model may need more time to load")
        except Exception as e:
            logger.warning(f"⚠️ Model warmup failed (will retry on first request): {e}")
    
    def generate_sql(self, question: str, schema_context: str = "") -> Optional[str]:
        """
        Generate SQL query from natural language question
        
        Args:
            question: Natural language question
            schema_context: Database schema information
            
        Returns:
            Generated SQL query or None if failed
        """
        if not self.available:
            logger.warning("AI service not available for SQL generation")
            return None
        
        try:
            prompt = f"""You are a SQL expert for Clickhouse. Generate a SQL query to answer this question.

                        Question: {question}

                        Database Schema:
                        {schema_context}

                        Rules:
                        1. Use only the tables and columns mentioned in the schema
                        2. Write clean, efficient Clickhouse-compatible SQL
                        3. Include appropriate JOINs if needed
                        4. Use LIMIT clause to prevent large result sets (max 100 rows)
                        5. Return ONLY the SQL query without any explanations or markdown formatting
                        6. Do not include ```sql or ``` markers

                        SQL Query:"""
            
            logger.info(f"Sending SQL generation request to Ollama for: {question[:100]}...")
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # Low temperature for more deterministic SQL
                        "top_p": 0.9,
                        "num_predict": 500
                    }
                },
                timeout=180  # Generous timeout for model processing
            )
            
            if response.status_code == 200:
                result = response.json()
                sql = result.get("response", "").strip()
                
                # Clean up the SQL (remove markdown formatting if present)
                if sql.startswith("```sql"):
                    sql = sql.replace("```sql", "").replace("```", "").strip()
                elif sql.startswith("```"):
                    sql = sql.replace("```", "").strip()
                
                # Remove any leading/trailing explanations
                lines = sql.split('\n')
                sql_lines = []
                in_sql = False
                
                for line in lines:
                    line_upper = line.strip().upper()
                    # Start capturing when we see SQL keywords
                    if line_upper.startswith(('SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE')):
                        in_sql = True
                    
                    if in_sql:
                        sql_lines.append(line)
                
                if sql_lines:
                    sql = '\n'.join(sql_lines).strip()
                
                logger.info(f"✅ Generated SQL successfully: {sql[:100]}...")
                return sql
            else:
                logger.error(f"❌ Ollama API error: {response.status_code} - {response.text[:200]}")
                return None
                
        except requests.exceptions.Timeout as e:
            logger.error(f"❌ SQL generation timeout after 180s: {e}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Cannot connect to Ollama: {e}")
            self.available = False
            return None
        except Exception as e:
            logger.error(f"❌ SQL generation failed: {e}", exc_info=True)
            return None
    
    def analyze_business_data(self, data: str, question: str = "") -> Optional[str]:
        """
        Generate business insights from data
        
        Args:
            data: Data to analyze (JSON or CSV format)
            question: Specific question about the data
            
        Returns:
            Business analysis and insights
        """
        if not self.available:
            logger.warning("AI service not available for business analysis")
            return None
        
        try:
            # Truncate data if too large to prevent token overflow
            data_preview = data[:3000] if len(data) > 3000 else data
            if len(data) > 3000:
                data_preview += "\n... (data truncated for analysis)"
            
            prompt = f"""You are a senior business analyst for an e-commerce company. Analyze this data and provide actionable insights.

                        Data:
                        {data_preview}

                        Question: {question if question else "Provide general business insights"}

                        Provide a structured analysis with:
                        1. **Key Findings**: 2-3 most important insights from the data
                        2. **Business Impact**: What these findings mean for the business
                        3. **Recommendations**: 3-4 specific actionable recommendations
                        4. **Metrics**: Highlight the most important numbers

                        Keep your response concise, professional, and focused on actionable insights.

                        Analysis:"""
            
            logger.info(f"Sending business analysis request to Ollama for: {question[:100]}...")
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,  # Slightly higher for creative insights
                        "top_p": 0.9,
                        "num_predict": 1000
                    }
                },
                timeout=180  # Generous timeout for analysis
            )
            
            if response.status_code == 200:
                result = response.json()
                analysis = result.get("response", "").strip()
                logger.info(f"✅ Generated business analysis successfully")
                return analysis
            else:
                logger.error(f"❌ Ollama API error: {response.status_code} - {response.text[:200]}")
                return None
                
        except requests.exceptions.Timeout as e:
            logger.error(f"❌ Business analysis timeout after 180s: {e}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Cannot connect to Ollama: {e}")
            self.available = False
            return None
        except Exception as e:
            logger.error(f"❌ Business analysis failed: {e}", exc_info=True)
            return None
    
    def generate_insights(self, metrics: Dict[str, Any], focus_area: str = "general") -> Optional[Dict[str, Any]]:
        """
        Generate business insights from key metrics
        
        Args:
            metrics: Dictionary of business metrics
            focus_area: Area to focus analysis on
            
        Returns:
            Structured insights with recommendations
        """
        if not self.available:
            return {
                "insights": [
                    {
                        "type": "info",
                        "title": "AI Service Unavailable",
                        "description": "AI-powered insights require Ollama to be running",
                        "confidence": 0.0
                    }
                ],
                "recommendations": [
                    "Ensure Ollama service is running and accessible",
                    "Check MCP server logs for AI service connectivity"
                ],
                "focus_area": focus_area,
                "generated_at": datetime.now().isoformat()
            }
        
        try:
            metrics_str = "\n".join([f"- {k}: {v}" for k, v in metrics.items()])
            
            prompt = f"""
                        You are a business intelligence expert. Analyze these metrics and generate insights.

                        Business Metrics:
                        {metrics_str}

                        Focus Area: {focus_area}

                        Provide insights in this JSON format:
                        {{
                            "insights": [
                                {{
                                    "type": "trend|opportunity|risk|achievement",
                                    "title": "Brief insight title",
                                    "description": "Detailed explanation",
                                    "confidence": 0.85
                                }}
                            ],
                            "recommendations": [
                                "Actionable recommendation 1",
                                "Actionable recommendation 2"
                            ]
                        }}

                        Analysis:
                        """
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "top_p": 0.9,
                        "max_tokens": 800
                    }
                },
                timeout=120  # Increased timeout for model loading
            )
            
            if response.status_code == 200:
                result = response.json()
                analysis_text = result.get("response", "").strip()
                
                # Try to parse JSON response
                try:
                    import json
                    # Extract JSON from response if wrapped in markdown
                    if "```json" in analysis_text:
                        json_start = analysis_text.find("```json") + 7
                        json_end = analysis_text.find("```", json_start)
                        analysis_text = analysis_text[json_start:json_end].strip()
                    
                    insights_data = json.loads(analysis_text)
                    insights_data["focus_area"] = focus_area
                    insights_data["generated_at"] = datetime.now().isoformat()
                    
                    return insights_data
                    
                except json.JSONDecodeError:
                    # Fallback to text-based insights
                    return {
                        "insights": [
                            {
                                "type": "analysis",
                                "title": "AI-Generated Business Analysis",
                                "description": analysis_text,
                                "confidence": 0.75
                            }
                        ],
                        "recommendations": ["Review the detailed analysis above"],
                        "focus_area": focus_area,
                        "generated_at": datetime.now().isoformat()
                    }
            else:
                logger.error(f"Ollama API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Insights generation failed: {e}")
            return None

# Global AI service instance
ai_service = AIService()