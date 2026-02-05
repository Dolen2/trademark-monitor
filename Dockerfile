# Trademark Monitor Docker Image
# ==============================

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data/uspto_xml logs

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Default command - run scheduled monitoring
CMD ["python", "run_monitor.py", "--schedule"]

# Alternative commands:
# Run single scan: docker run trademark-monitor python run_monitor.py --days 7
# Dashboard: docker run -p 8501:8501 trademark-monitor python run_monitor.py --dashboard
