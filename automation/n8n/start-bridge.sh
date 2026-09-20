#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOCAL_ENV="$SCRIPT_DIR/.env"

if [ -z "${MM_BRIDGE_TOKEN:-}" ] && [ -f "$LOCAL_ENV" ]; then
  MM_BRIDGE_TOKEN="$(python3 - "$LOCAL_ENV" <<'PY'
import sys
from pathlib import Path
for raw in Path(sys.argv[1]).read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() == "MM_BRIDGE_TOKEN":
        print(value.strip().strip('"').strip("'"))
        break
PY
)"
fi

if [ -z "${MM_BRIDGE_TOKEN:-}" ]; then
  echo "ERROR: MM_BRIDGE_TOKEN is not configured in automation/n8n/.env or the environment" >&2
  exit 1
fi

export MM_BRIDGE_TOKEN
export MM_EXTERNAL_SEND_DISABLED=1
unset LIVE_SEND_ENABLED || true

PYTHON="$PROJECT_ROOT/.venv-email/bin/python"
test -x "$PYTHON" || { echo "Missing $PYTHON"; exit 1; }

cd "$PROJECT_ROOT"
exec "$PYTHON" money-machine/mm_bridge.py --host 127.0.0.1 --port 8787
