# =============================================================================
# J.A.R.V.I.S. — Production Dockerfile (backend + frontend)
# =============================================================================
# Serves both the FastAPI backend and built React frontend from one container.
# =============================================================================

# ── Stage 1: Build the frontend ──────────────────────────────────────────────
FROM node:20-slim AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --ignore-scripts 2>/dev/null || npm install
COPY frontend/ .
ENV VITE_API_URL=/api/v1
RUN npm run build

# ── Stage 2: Python backend + serve frontend ─────────────────────────────────
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
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Application code
COPY backend/ .
RUN chmod +x /app/entrypoint.sh

# Copy built frontend into /app/static
COPY --from=frontend-build /frontend/dist /app/static

# Non-root user
RUN addgroup --system jarvis && \
    adduser --system --ingroup jarvis jarvis && \
    chown -R jarvis:jarvis /app
USER jarvis

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
