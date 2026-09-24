#!/bin/zsh
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
KEYCHAIN_SERVICE="com.website-auditor.a2a-gateway"
KEYCHAIN_ACCOUNT="WEBSITE-AUDITOR"

# Keep credentials out of the LaunchAgent plist and load them only into this
# dedicated process. A missing or malformed key fails closed.
MM_A2A_GATEWAY_TOKEN="$(/usr/bin/security find-generic-password \
  -a "$KEYCHAIN_ACCOUNT" -s "$KEYCHAIN_SERVICE" -w 2>/dev/null)"
if [[ ! "$MM_A2A_GATEWAY_TOKEN" =~ '^[[:xdigit:]]{64}$' ]]; then
  print -u2 -- "A2A gateway Keychain token is missing or invalid."
  exit 1
fi

export MM_A2A_GATEWAY_TOKEN
export MM_A2A_GATEWAY_ENABLED=1
export MM_A2A_FREE_ROUTING=1
export MM_ALLOW_EXTERNAL_FREE_MODELS=1
export MM_A2A_GATEWAY_HOST=127.0.0.1
export MM_A2A_GATEWAY_PORT=8094

cd "$REPO_ROOT"
exec "$REPO_ROOT/.venv-email/bin/python" \
  "$REPO_ROOT/money-machine/mm_operator.py" a2a-gateway \
  --host 127.0.0.1 --port 8094
