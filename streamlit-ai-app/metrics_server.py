#!/usr/bin/env python3
"""
Simple metrics server for Streamlit application
Runs alongside Streamlit to provide Prometheus metrics
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time
import os
import requests
import json
from datetime import datetime

class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            
            # Get basic metrics
            metrics = self.get_metrics()
            self.wfile.write(metrics.encode('utf-8'))
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            health = {
                "status": "healthy",
                "service": "streamlit-metrics",
                "timestamp": datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(health).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def get_metrics(self):
        """Generate Prometheus metrics"""
        # Check if Streamlit is running
        try:
            response = requests.get('http://localhost:8501/_stcore/health', timeout=2)
            streamlit_up = 1 if response.status_code == 200 else 0
        except:
            streamlit_up = 0
        
        # Check MCP server connectivity
        try:
            mcp_url = os.getenv('MCP_SERVER_URL', 'http://mcp-server:5000')
            response = requests.get(f'{mcp_url}/health', timeout=2)
            mcp_connected = 1 if response.status_code == 200 else 0
        except:
            mcp_connected = 0
        
        metrics = f"""# HELP streamlit_up Streamlit application status
                    # TYPE streamlit_up gauge
                    streamlit_up {streamlit_up}

                    # HELP streamlit_mcp_connected MCP server connection status
                    # TYPE streamlit_mcp_connected gauge
                    streamlit_mcp_connected {mcp_connected}

                    # HELP streamlit_uptime_seconds Service uptime
                    # TYPE streamlit_uptime_seconds counter
                    streamlit_uptime_seconds {time.time()}
                    """
        return metrics
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass

def start_metrics_server():
    """Start the metrics server in a separate thread"""
    server = HTTPServer(('0.0.0.0', 9501), MetricsHandler)
    print("🔧 Starting Streamlit metrics server on port 9501")
    server.serve_forever()

if __name__ == '__main__':
    # Start metrics server in background thread
    metrics_thread = threading.Thread(target=start_metrics_server, daemon=True)
    metrics_thread.start()
    
    print("✅ Streamlit metrics server started")
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🛑 Shutting down metrics server")