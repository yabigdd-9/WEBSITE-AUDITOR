#!/bin/sh
# searxng.sh — local SearXNG discovery service management helper
# Mirrors supervisor.sh pattern: delegates to the launchd wrapper module.
# SearXNG is read-only discovery only on 127.0.0.1:8888.
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PY="${REPO_ROOT}/.venv-email/bin/python"

if [ "$#" -eq 0 ]; then
    ACTION="status"
else
    ACTION="$1"
    shift
fi

case "$ACTION" in
    status|start|stop|restart|ensure-running|install|uninstall)
        exec "$VENV_PY" -m supervisor.searxng_launchd "$ACTION" "$@"
        ;;
    *)
        echo "Usage: searxng.sh {status|start|stop|restart|ensure-running|install|uninstall}" >&2
        exit 2
        ;;
esac
