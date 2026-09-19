#!/usr/bin/env bash
set -euo pipefail
# Start n8n with USB fail-closed: refuse to start if /Volumes/LLM-USB is not mounted.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== n8n preflight ==="
test -d "/Volumes/LLM-USB" || { echo "LLM-USB NOT MOUNTED"; exit 1; }
mkdir -p "/Volumes/LLM-USB/WEBSITE-AUDITOR/n8n/data"
mkdir -p "/Volumes/LLM-USB/WEBSITE-AUDITOR/n8n/files"
mkdir -p "/Volumes/LLM-USB/WEBSITE-AUDITOR/n8n/logs"
docker version >/dev/null 2>&1 || { echo "Docker daemon not reachable"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose not available"; exit 1; }

echo "=== starting n8n ==="
cd "$SCRIPT_DIR"
docker compose up -d
echo "=== n8n started ==="
docker compose ps
echo "=== health check ==="
for i in 1 2 3 4 5; do
  if curl -sf http://127.0.0.1:5678/healthz >/dev/null 2>&1; then
    echo "n8n healthy"
    exit 0
  fi
  sleep 3
done
echo "n8n health check failed"
exit 1