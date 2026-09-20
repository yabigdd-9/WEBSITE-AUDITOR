#!/bin/sh
set -eu
MM_ENTRY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
exec "$MM_ENTRY_ROOT/mm" supervisor-start "$@"
