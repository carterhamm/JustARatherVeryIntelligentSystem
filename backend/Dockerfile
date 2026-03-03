# =============================================================================
# J.A.R.V.I.S. — Production Dockerfile (backend + frontend)
# =============================================================================
# Serves both the API and the pre-built React frontend from a single container.
# Frontend is pre-built and included in backend/static/.
# =============================================================================

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        postgresql-client \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Application code (includes static/ with pre-built frontend)
COPY . .
RUN chmod +x /app/entrypoint.sh

# Non-root user
RUN addgroup --system jarvis && \
    adduser --system --ingroup jarvis jarvis && \
    chown -R jarvis:jarvis /app
USER jarvis

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
