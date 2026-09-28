#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PY="${MM_PYTHON:-$ROOT/.venv-email/bin/python}"
LAUNCHD="$ROOT/money-machine/supervisor/launchd.py"

die() {
  echo "ERROR: $*" >&2
  exit 2
}

[ -x "$PY" ] || die "Python runtime missing: $PY"
[ -f "$LAUNCHD" ] || die "launchd wrapper missing: $LAUNCHD"
[ -x "$ROOT/mm" ] || die "operator CLI missing or not executable: $ROOT/mm"

action="${1:-status}"

case "$action" in
  install)
    echo "== WEBSITE-AUDITOR local machine: preflight =="
    cd "$ROOT"
    ./mm doctor
    echo "== installing user launchd service =="
    "$PY" "$LAUNCHD" install
    sleep 2
    echo "== launchd status =="
    "$PY" "$LAUNCHD" status
    echo "== money machine health =="
    ./mm health
    echo "LOCAL_MACHINE_READY"
    ;;
  start)
    cd "$ROOT"
    ./mm supervisor ensure-running
    ./mm health
    ;;
  status)
    cd "$ROOT"
    "$PY" "$LAUNCHD" status
    ./mm health
    ;;
  restart)
    cd "$ROOT"
    "$PY" "$LAUNCHD" uninstall --keep-plist || true
    "$PY" "$LAUNCHD" install
    sleep 2
    ./mm health
    ;;
  logs)
    cd "$ROOT"
    ./mm supervisor logs
    ;;
  uninstall)
    cd "$ROOT"
    "$PY" "$LAUNCHD" uninstall
    ./mm supervisor stop || true
    ;;
  *)
    echo "usage: sh scripts/local-machine.sh {install|start|status|restart|logs|uninstall}" >&2
    exit 2
    ;;
esac
