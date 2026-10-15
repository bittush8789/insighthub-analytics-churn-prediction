# Multi-stage Dockerfile for E-commerce Analytics & Churn Prediction Platform
FROM python:3.12-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8501

# Copy dependency definition
COPY requirements.txt .

# Install Python packages
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application source code
COPY src/ ./src/
COPY app/ ./app/
COPY sql/ ./sql/
COPY scripts/ ./scripts/
COPY .env.example ./

# Create data, artifacts, and log directories with default placeholders
RUN mkdir -p data/raw data/processed artifacts/models logs

# Expose Streamlit port
EXPOSE 8501

# Healthcheck for Streamlit service
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Default execution command
CMD ["streamlit", "run", "app/Home.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
