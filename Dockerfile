FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Persistent storage for the SQLite database.
# In Railway: add a Volume mounted at /data in your service settings.
RUN mkdir -p /data

# Railway injects $PORT at runtime (default 8080).
# Gunicorn reads it via the CMD below.
ENV PORT=8080

EXPOSE 8080

# 2 workers is sufficient for a small crew app; adjust via GUNICORN_WORKERS env var.
CMD gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout 120 \
    --access-logfile - \
    run:app
