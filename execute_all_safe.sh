#!/usr/bin/env bash
set -euo pipefail
TARGET="${1:-https://example.co.nz}"
exec python3 run_all.py "$TARGET"
