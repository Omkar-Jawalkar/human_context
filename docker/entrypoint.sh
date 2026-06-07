#!/usr/bin/env bash
set -euo pipefail

case "${1:-api}" in
  api)
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  worker)
    exec celery -A app.workers.celery_app worker --loglevel="${CELERY_LOG_LEVEL:-info}"
    ;;
  flower)
    args=(
      celery -A app.workers.celery_app flower
      --port="${FLOWER_PORT:-5555}"
      --address=0.0.0.0
    )
    if [ -n "${FLOWER_BASIC_AUTH:-}" ]; then
      args+=(--basic-auth="${FLOWER_BASIC_AUTH}")
    fi
    exec "${args[@]}"
    ;;
  *)
    exec "$@"
    ;;
esac
