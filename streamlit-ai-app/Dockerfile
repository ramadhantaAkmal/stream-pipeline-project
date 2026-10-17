FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .
COPY startup.sh .
# COPY test_mcp.py .

# Fix Windows line endings (CRLF -> LF) and make executable
# This prevents "exec ./startup.sh: no such file or directory" on Linux
RUN dos2unix startup.sh && chmod +x startup.sh

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Use startup script
CMD ["./startup.sh"]