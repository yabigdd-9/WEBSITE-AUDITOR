#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -n "${MM_PYTHON:-}" ]; then
  PY="$MM_PYTHON"
elif [ -x "$ROOT/.venv-email/bin/python" ]; then
  PY="$ROOT/.venv-email/bin/python"
else
  PY="$ROOT/.venv/bin/python"
fi
MM_LAUNCHD="$ROOT/money-machine/supervisor/launchd.py"
FCC_LAUNCHD="$ROOT/money-machine/supervisor/fcc_launchd.py"

die() {
  echo "ERROR: $*" >&2
  exit 2
}

[ -x "$PY" ] || die "Python runtime missing: $PY"
[ -f "$MM_LAUNCHD" ] || die "Money Machine launchd wrapper missing: $MM_LAUNCHD"
[ -f "$FCC_LAUNCHD" ] || die "FCC launchd wrapper missing: $FCC_LAUNCHD"
[ -x "$ROOT/mm" ] || die "operator CLI missing or not executable: $ROOT/mm"

action="${1:-status}"

case "$action" in
  install)
    echo "== WEBSITE-AUDITOR local machine: preflight =="
    cd "$ROOT"
    ./mm doctor
    echo "== installing FCC launchd service =="
    if "$PY" "$FCC_LAUNCHD" install; then
      echo "FCC launchd loaded."
    else
      echo "WARNING: FCC did not load; Hermes free fallback remains available." >&2
    fi
    echo "== installing Money Machine launchd service =="
    "$PY" "$MM_LAUNCHD" install
    sleep 2
    echo "== launchd status =="
    "$PY" "$FCC_LAUNCHD" status
    "$PY" "$MM_LAUNCHD" status
    echo "== money machine health =="
    ./mm health
    echo "== model routes =="
    ./mm model-routes
    echo "LOCAL_MACHINE_READY"
    ;;
  start)
    cd "$ROOT"
    "$PY" "$FCC_LAUNCHD" install || true
    ./mm supervisor ensure-running
    ./mm health
    ;;
  status)
    cd "$ROOT"
    "$PY" "$FCC_LAUNCHD" status
    "$PY" "$MM_LAUNCHD" status
    ./mm health
    ./mm model-routes
    ;;
  restart)
    cd "$ROOT"
    "$PY" "$MM_LAUNCHD" uninstall --keep-plist || true
    "$PY" "$FCC_LAUNCHD" uninstall || true
    "$PY" "$FCC_LAUNCHD" install || true
    "$PY" "$MM_LAUNCHD" install
    sleep 2
    ./mm health
    ;;
  logs)
    cd "$ROOT"
    ./mm supervisor logs
    echo "FCC stdout: $ROOT/state/launchd-fcc.stdout.log"
    echo "FCC stderr: $ROOT/state/launchd-fcc.stderr.log"
    ;;
  uninstall)
    cd "$ROOT"
    "$PY" "$MM_LAUNCHD" uninstall
    "$PY" "$FCC_LAUNCHD" uninstall || true
    ./mm supervisor stop || true
    ;;
  *)
    echo "usage: sh scripts/local-machine.sh {install|start|status|restart|logs|uninstall}" >&2
    exit 2
    ;;
esac
