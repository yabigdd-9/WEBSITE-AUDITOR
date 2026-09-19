#!/usr/bin/env bash
set -euo pipefail
# Healthcheck for n8n — exits 0 if healthy, 1 otherwise.
RESPONSE=$(curl -sf http://127.0.0.1:5678/healthz 2>/dev/null) || { echo "unhealthy"; exit 1; }
echo "$RESPONSE"
exit 0