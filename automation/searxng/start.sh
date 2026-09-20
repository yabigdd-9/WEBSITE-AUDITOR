#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
EXAMPLE="$SCRIPT_DIR/.env.example"

test -d "/Volumes/LLM-USB" || { echo "LLM-USB NOT MOUNTED"; exit 1; }
docker version >/dev/null 2>&1 || { echo "Docker daemon not reachable"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose not available"; exit 1; }

if [ ! -f "$ENV_FILE" ]; then
  cp "$EXAMPLE" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

if ! grep -Eq '^SEARXNG_SECRET=.+$' "$ENV_FILE"; then
  SECRET="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
  python3 - "$ENV_FILE" "$SECRET" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1])
secret = sys.argv[2]
lines = p.read_text().splitlines()
out = []
seen = False
for line in lines:
    if line.startswith("SEARXNG_SECRET="):
        out.append("SEARXNG_SECRET=" + secret)
        seen = True
    else:
        out.append(line)
if not seen:
    out.append("SEARXNG_SECRET=" + secret)
p.write_text("\n".join(out) + "\n")
PY
fi

set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

: "${SEARXNG_DATA_DIR:?SEARXNG_DATA_DIR is required}"
mkdir -p "$SEARXNG_DATA_DIR"

cd "$SCRIPT_DIR"
docker compose up -d
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "http://127.0.0.1:${SEARXNG_PORT:-8888}/search?q=health&format=json" >/dev/null; then
    echo "SearXNG healthy on 127.0.0.1:${SEARXNG_PORT:-8888}"
    exit 0
  fi
  sleep 3
done
echo "SearXNG health check failed"
exit 1
