# =============================================================================
# J.A.R.V.I.S. Backend — Production Dockerfile
# =============================================================================
# Build:  docker build -t jarvis-backend .
# Run:    docker run -p 8000:8000 --env-file ../.env jarvis-backend
# =============================================================================

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# -- System dependencies ------------------------------------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        postgresql-client \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

# -- Python dependencies ------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# -- Application code ---------------------------------------------------------
COPY . .

# -- Non-root user -------------------------------------------------------------
RUN addgroup --system jarvis && \
    adduser --system --ingroup jarvis jarvis && \
    chown -R jarvis:jarvis /app
USER jarvis

EXPOSE 8000

# -- Health check --------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# -- Entrypoint ----------------------------------------------------------------
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--log-level", "info"]
