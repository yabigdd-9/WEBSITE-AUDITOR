#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
test -f "$ENV_FILE" || { echo "Missing $ENV_FILE"; exit 1; }
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a
SOURCE="${N8N_DATA_DIR:?N8N_DATA_DIR is required}"
BACKUP_DIR="${1:-/Volumes/LLM-USB/WEBSITE-AUDITOR/backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$BACKUP_DIR/n8n-backup-$TIMESTAMP.tar.gz"
mkdir -p "$BACKUP_DIR"
tar -czf "$TARGET" -C "$(dirname "$SOURCE")" "$(basename "$SOURCE")"
echo "Backup created: $TARGET"
