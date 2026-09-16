#!/bin/bash
set -eu
MM_LAUNCH_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
"$MM_LAUNCH_DIR/mm" --runtime
if [ "${1:-}" = '--runtime' ]; then exit 0; fi
"$MM_LAUNCH_DIR/mm" daily
open "${MM_ROOT:-$MM_LAUNCH_DIR/..}/reports/daily-operator/index.html"
