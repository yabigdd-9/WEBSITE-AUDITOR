#!/usr/bin/env bash
set -u

MM="$HOME/MoneyMachine"
OUT="${1:-$MM/reports/machine-audit-$(date +%Y%m%d-%H%M%S).txt}"

count_files() {
    find "$1" -type f 2>/dev/null | wc -l | tr -d ' '
}

{
    echo "MONEY_MACHINE_AUDITOR"
    echo "DATE=$(date)"

    echo "database=$(count_files "$MM/database")"
    echo "scripts=$(count_files "$MM/scripts")"
    echo "logs=$(count_files "$MM/logs")"
    echo "reports=$(count_files "$MM/reports")"
    echo "backups=$(count_files "$MM/backups")"
    echo "demos=$(count_files "$MM/demos")"
    echo "control_plane=$(count_files "$MM/control-plane")"

    echo
    echo "-- DUPLICATE CONTENT --"

    find \
      "$MM/config" \
      "$MM/control-plane" \
      "$MM/scripts" \
      "$MM/demos" \
      "$MM/reports" \
      -type f -size -5M 2>/dev/null |
    while read -r f
    do
        shasum -a 256 "$f" 2>/dev/null || true
    done |
    sort |
    awk '
      previous_hash == $1 {
          print previous
          print
      }
      {
          previous_hash=$1
          previous=$0
      }
    ' |
    head -100

    echo
    echo "-- STALE WORK >14 DAYS --"

    find \
      "$MM" \
      -type f -mtime +14 \
      -not -path '*/.git/*' \
      -not -path '*/backups/*' \
      -not -path '*/data/*' \
      -not -path '*/logs/*' \
      -print 2>/dev/null |
    head -100

} > "$OUT"

echo "$OUT"
