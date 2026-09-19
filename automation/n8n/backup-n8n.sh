#!/usr/bin/env bash
set -euo pipefail
# Backup n8n data directory and compose.yml to a timestamped archive.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="${1:-/Volumes/LLM-USB/WEBSITE-AUDITOR/n8n/data}"
BACKUP_DIR="${2:-/Volumes/LLM-USB/WEBSITE-AUDITOR/backups}"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
TARGET="$BACKUP_DIR/n8n-backup-$TIMESTAMP.tar.gz"

mkdir -p "$BACKUP_DIR"
tar -czf "$TARGET" -C "$(dirname "$SOURCE")" "$(basename "$SOURCE")" "$SCRIPT_DIR/compose.yml" 2>/dev/null
echo "$TARGET"
echo "Backup created: $TARGET"