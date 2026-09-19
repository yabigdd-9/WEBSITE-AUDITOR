#!/usr/bin/env bash
set -euo pipefail

HERE="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
REPO="$(CDPATH= cd -- "$HERE/../.." && pwd)"
PROFILE="${DSH_WEBSITE_AUDITOR_PROFILE:-website-auditor}"

command -v dsh >/dev/null 2>&1 || {
  echo "BLOCKED: dsh is not installed." >&2
  exit 2
}

export WEBSITE_AUDITOR_ROOT="$REPO"
export DSH_TELEMETRY_MODE="${DSH_TELEMETRY_MODE:-DISABLED}"
export OLLAMA_API_KEY="${OLLAMA_API_KEY:-ollama}"

if [ "$#" -gt 0 ]; then
  TASK="$*"
else
  TASK="$(cat)"
fi

[ -n "${TASK//[[:space:]]/}" ] || {
  echo "BLOCKED: provide a task argument or pipe a task on stdin." >&2
  exit 2
}

cd "$REPO"
exec dsh --profile "$PROFILE" --json "$TASK"
