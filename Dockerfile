FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (curl for healthcheck, libpq for PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code (secrets and db are excluded via .dockerignore)
COPY . .

# Expose default port (Render overrides via $PORT)
EXPOSE 8000

# Healthcheck against zero-dependency /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start uvicorn dynamically binding to $PORT (Render/Cloud container standard) or defaulting to 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
