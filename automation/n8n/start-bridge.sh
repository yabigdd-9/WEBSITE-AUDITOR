#!/usr/bin/env bash
# Start the MM bridge API (n8n calls http://host.docker.internal:8787/<action>)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found — copy .env.example and set MM_BRIDGE_TOKEN" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"

if [ -z "${MM_BRIDGE_TOKEN:-}" ]; then
    echo "ERROR: MM_BRIDGE_TOKEN not set in .env" >&2
    exit 1
fi

export MM_BRIDGE_TOKEN
cd "$PROJECT_ROOT"
source .venv-email/bin/activate
exec python money-machine/mm_bridge.py --host 127.0.0.1 --port 8787