#!/usr/bin/env bash
set -euo pipefail
curl -sf http://127.0.0.1:5678/healthz >/dev/null
echo "n8n healthy"
