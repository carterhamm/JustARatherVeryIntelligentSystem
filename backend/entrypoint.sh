#!/bin/sh
set -e

echo "Running database migrations..."
python -m alembic upgrade head

echo "Starting JARVIS backend..."
exec uvicorn app.main:app \
  --host :: \
  --port "${PORT:-8000}" \
  --workers "${WORKERS:-4}" \
  --log-level info
