#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

project_python() {
  if [ -x "$ROOT/.venv-email/bin/python" ]; then
    printf '%s\n' "$ROOT/.venv-email/bin/python"
  elif [ -x "$ROOT/.venv/bin/python" ]; then
    printf '%s\n' "$ROOT/.venv/bin/python"
  else
    echo "ERROR: project Python environment is missing" >&2
    exit 2
  fi
}

PY="$(project_python)"

echo "=== INSTALL / VERIFY LOCAL SEARXNG ==="
sh "$ROOT/money-machine/scripts/searxng.sh" install

echo
echo "=== VERIFY SEARCH SERVICE ==="
./mm searxng verify

echo
echo "=== RELOAD MONEY MACHINE SUPERVISOR ONLY ==="
"$PY" "$ROOT/money-machine/supervisor/launchd.py" install

sleep 5

echo
echo "=== RUN ONE BOUNDED DISCOVERY CYCLE NOW ==="
./mm discovery-cycle --force

echo
echo "=== SUPERVISOR STATUS ==="
./mm supervisor status

echo
echo "=== MONEY MACHINE HEALTH ==="
./mm health

echo
echo "=== RECURRING DISCOVERY STATE ==="
cat "$ROOT/state/recurring-discovery.json" 2>/dev/null || true

echo
echo "Scanning activation complete."
echo "No outreach send action is performed by this script."
