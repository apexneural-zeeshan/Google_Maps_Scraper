#!/usr/bin/env sh
set -eu

MAX_RETRIES="${DB_MIGRATION_MAX_RETRIES:-30}"
SLEEP_SECONDS="${DB_MIGRATION_RETRY_SLEEP_SECONDS:-2}"
ATTEMPT=1

echo "Running database migrations..."
until alembic upgrade head; do
  if [ "$ATTEMPT" -ge "$MAX_RETRIES" ]; then
    echo "Migration failed after ${ATTEMPT} attempts."
    exit 1
  fi
  echo "Migration attempt ${ATTEMPT} failed. Retrying in ${SLEEP_SECONDS}s..."
  ATTEMPT=$((ATTEMPT + 1))
  sleep "$SLEEP_SECONDS"
done

echo "Starting API server..."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${UVICORN_WORKERS:-2}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
