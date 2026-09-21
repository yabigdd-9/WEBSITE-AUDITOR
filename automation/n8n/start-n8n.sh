#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

echo "=== n8n preflight ==="
test -d "/Volumes/LLM-USB" || { echo "LLM-USB NOT MOUNTED"; exit 1; }
test -f "$ENV_FILE" || { echo "Missing $ENV_FILE — copy .env.example to .env first"; exit 1; }

set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

: "${N8N_DATA_DIR:?N8N_DATA_DIR is required}"
: "${N8N_FILES_DIR:?N8N_FILES_DIR is required}"
mkdir -p "$N8N_DATA_DIR" "$N8N_FILES_DIR"

docker version >/dev/null 2>&1 || { echo "Docker daemon not reachable"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose not available"; exit 1; }

cd "$SCRIPT_DIR"
docker compose up -d
docker compose ps

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf http://127.0.0.1:5678/healthz >/dev/null 2>&1; then
    echo "n8n healthy"
    exit 0
  fi
  sleep 3
done

echo "n8n health check failed"
exit 1
