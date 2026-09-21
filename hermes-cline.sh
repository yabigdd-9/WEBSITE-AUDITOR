#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export HERMES_ENABLE_PROJECT_PLUGINS=true

if ! command -v hermes >/dev/null 2>&1; then
  echo "ERROR: hermes is not in PATH" >&2
  exit 1
fi

if ! command -v cline >/dev/null 2>&1; then
  echo "ERROR: cline is not in PATH" >&2
  echo "Install/update it with: npm install -g cline@latest" >&2
  exit 1
fi

CLINE_HELP="$(cline --help 2>&1 || true)"
for flag in --json --cwd --provider --model --auto-approve; do
  if ! printf '%s\n' "$CLINE_HELP" | grep -q -- "$flag"; then
    echo "ERROR: installed Cline CLI is too old for the Hermes bridge (missing $flag)." >&2
    echo "Update with: npm install -g cline@latest && hash -r" >&2
    exit 1
  fi
done

exec hermes "$@"
