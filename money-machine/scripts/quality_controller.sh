#!/usr/bin/env bash
set -u

TARGET="${1:-}"

if [ -z "$TARGET" ]; then
    echo "BLOCKED: target required"
    exit 2
fi

if [ ! -e "$TARGET" ]; then
    echo "BLOCKED: target does not exist"
    exit 2
fi

BAD=0

if [ -f "$TARGET" ] && [ ! -s "$TARGET" ]; then
    echo "REWORK: empty artifact"
    BAD=1
fi

# Look for likely exposed secrets, but never print their contents.
if grep -RIlE \
 '(sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY[[:space:]]*=|API_KEY[[:space:]]*=[[:space:]]*[^$<{[:space:]])' \
 "$TARGET" \
 --exclude-dir=.git \
 --exclude-dir=node_modules \
 --exclude='*.log' \
 2>/dev/null |
  head -1 |
  grep -q .
then
    echo "REWORK: possible secret material detected"
    BAD=1
fi

if [ "$BAD" -eq 0 ]; then
    echo "PASS: quality/security gate"
    exit 0
fi

exit 1
