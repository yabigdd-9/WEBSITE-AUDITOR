#!/bin/sh
set -eu
MM_ADAPTER_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${MM_ADAPTER_PYTHON:-python3}" "$MM_ADAPTER_DIR/hermes_adapter.py" "$@"
