#!/bin/sh
set -eu
MM_REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$MM_REPO_DIR/money-machine/mm" "$@"
