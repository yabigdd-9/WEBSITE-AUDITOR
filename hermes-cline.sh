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

exec hermes "$@"
