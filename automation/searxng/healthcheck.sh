#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
PORT=8888
if [ -f "$ENV_FILE" ]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  PORT="${SEARXNG_PORT:-8888}"
fi
curl -fsS "http://127.0.0.1:$PORT/search?q=health&format=json" >/dev/null
echo "SearXNG healthy"
