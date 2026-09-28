#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export HOST=127.0.0.1
export PORT="${PORT:-8082}"
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"

load_env_file() {
  file="$1"
  [ -f "$file" ] || return 0
  set -a
  . "$file"
  set +a
}

load_env_file "$ROOT/.env"
load_env_file "$ROOT/.env.fcc"

command -v fcc-server >/dev/null 2>&1 || {
  echo "fcc-server not found in PATH" >&2
  exit 127
}

exec fcc-server
