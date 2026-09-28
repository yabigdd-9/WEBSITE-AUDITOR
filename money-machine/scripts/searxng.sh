#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
SRC="$HOME/searxng-src"
VENV="$HOME/.local/share/searxng/.venv"
SETTINGS_DIR="$HOME/.searxng"
SETTINGS="$SETTINGS_DIR/settings.yml"
LAUNCHD="$ROOT/money-machine/supervisor/searxng_launchd.py"
ENDPOINT="${MM_SEARXNG_ENDPOINT:-http://127.0.0.1:8888}"

die() {
  echo "ERROR: $*" >&2
  exit 2
}

project_python() {
  if [ -x "$ROOT/.venv-email/bin/python" ]; then
    printf '%s\n' "$ROOT/.venv-email/bin/python"
  elif [ -x "$ROOT/.venv/bin/python" ]; then
    printf '%s\n' "$ROOT/.venv/bin/python"
  else
    command -v python3
  fi
}

ensure_settings() {
  mkdir -p "$SETTINGS_DIR"
  chmod 700 "$SETTINGS_DIR"
  if [ ! -f "$SETTINGS" ]; then
    SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
    umask 077
    cat > "$SETTINGS" <<EOF
use_default_settings: true
server:
  secret_key: "$SECRET"
  limiter: false
  public_instance: false
  bind_address: "127.0.0.1"
  port: 8888
search:
  formats:
    - html
    - json
  safe_search: 1
general:
  debug: false
  enable_metrics: false
EOF
    chmod 600 "$SETTINGS"
    echo "Created private SearXNG settings: $SETTINGS"
  else
    chmod 600 "$SETTINGS"
    echo "Preserving existing SearXNG settings: $SETTINGS"
  fi
}

verify_listener() {
  if ! command -v lsof >/dev/null 2>&1; then
    echo "WARNING: lsof unavailable; HTTP probe will still run." >&2
    return 0
  fi
  LISTENERS="$(lsof -nP -iTCP:8888 -sTCP:LISTEN 2>/dev/null || true)"
  [ -n "$LISTENERS" ] || die "nothing is listening on TCP 8888"
  echo "$LISTENERS"
  echo "$LISTENERS" | grep -Eq '127\.0\.0\.1:8888|\[::1\]:8888|localhost:8888' \
    || die "SearXNG listener is not loopback-only"
  if echo "$LISTENERS" | grep -Eq '(\*:8888|0\.0\.0\.0:8888|\[::\]:8888)'; then
    die "unsafe SearXNG public bind detected"
  fi
}

action="${1:-status}"
PY="$(project_python)"

case "$action" in
  install)
    command -v git >/dev/null 2>&1 || die "git is required"
    command -v uv >/dev/null 2>&1 || die "uv is required"

    if [ ! -d "$SRC/.git" ]; then
      [ ! -e "$SRC" ] || die "$SRC exists but is not a git checkout"
      git clone --depth 1 https://github.com/searxng/searxng.git "$SRC"
    else
      echo "Preserving existing SearXNG checkout: $SRC"
    fi

    if [ ! -x "$VENV/bin/python" ]; then
      mkdir -p "$(dirname "$VENV")"
      uv venv --python 3.11 "$VENV"
    fi

    # Match current upstream source-install requirements: seed the build
    # dependencies, then install the SearXNG checkout itself into this isolated
    # venv. Installing requirements.txt alone is insufficient for
    # python -m searx.webapp from a launchd working directory outside the repo.
    uv pip install --python "$VENV/bin/python" \
      --upgrade setuptools wheel pyyaml msgspec typing-extensions pybind11
    uv pip install --python "$VENV/bin/python" \
      --no-build-isolation --editable "$SRC"
    ensure_settings
    "$PY" "$LAUNCHD" install
    sleep 5
    "$0" verify
    ;;

  status)
    "$PY" "$LAUNCHD" status
    "$ROOT/mm" searxng status --endpoint "$ENDPOINT"
    ;;

  verify)
    verify_listener
    "$ROOT/mm" searxng verify --endpoint "$ENDPOINT"
    ;;

  start|restart)
    "$PY" "$LAUNCHD" install
    sleep 5
    "$0" verify
    ;;

  stop)
    "$PY" "$LAUNCHD" uninstall
    ;;

  logs)
    echo "stdout: $ROOT/state/launchd-searxng.stdout.log"
    echo "stderr: $ROOT/state/launchd-searxng.stderr.log"
    tail -80 "$ROOT/state/launchd-searxng.stderr.log" 2>/dev/null || true
    ;;

  uninstall)
    "$PY" "$LAUNCHD" uninstall || true
    echo "LaunchAgent removed."
    echo "Source, virtualenv, and settings were intentionally preserved."
    ;;

  *)
    echo "usage: $0 {install|status|verify|start|restart|stop|logs|uninstall}" >&2
    exit 2
    ;;
esac
