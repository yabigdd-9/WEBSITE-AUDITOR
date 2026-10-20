#!/bin/bash
# Compatibility entry point: inference uses the admitted Python bridge.
# Service control belongs to the verified supervisor rollout workflow.
set -eu
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMAND="${1:-status}"
if [[ $# -gt 0 ]]; then shift; fi
case "$COMMAND" in
    status|claude|codex|fcc)
        exec "${MM_PYTHON:-python3}" "$SCRIPT_DIR/fcc-bridge.py" "$COMMAND" "$@"
        ;;
    server|all|start|stop)
        printf '%s\n' 'BLOCKED: service control requires verified ownership and exact rollout authority.' >&2
        exit 3
        ;;
    *)
        printf '%s\n' 'Usage: fcc-bridge.sh [status|claude|codex|fcc]' >&2
        exit 2
        ;;
esac
