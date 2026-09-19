#!/usr/bin/env bash
set -euo pipefail

HERE="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
REPO="$(CDPATH= cd -- "$HERE/../.." && pwd)"
PROFILE="${DSH_WEBSITE_AUDITOR_PROFILE:-website-auditor}"

command -v dsh >/dev/null 2>&1 || {
  echo "BLOCKED: dsh is not installed. Install the pinned package first:" >&2
  echo "  npm install -g @deepseek-ai/dsh@0.1.6-alpha.2" >&2
  exit 2
}
command -v pnpm >/dev/null 2>&1 || {
  echo "BLOCKED: pnpm is required by 'dsh plugin'. Enable/install pnpm, then rerun." >&2
  exit 2
}

export WEBSITE_AUDITOR_ROOT="$REPO"
export DSH_TELEMETRY_MODE="${DSH_TELEMETRY_MODE:-DISABLED}"

if ! dsh --profile "$PROFILE" --dump-config >/dev/null 2>&1; then
  dsh --profile "$PROFILE" --from-default-profile headless --dump-config >/dev/null
fi

dsh plugin --profile "$PROFILE" add "file:$HERE/plugin"
dsh --profile "$PROFILE" --dump-config | grep -q "dsh-website-auditor-tools"

echo "PASS: DeepSeek Harness profile '$PROFILE' includes dsh-website-auditor-tools"
echo "Repo: $REPO"
echo "Writes: bounded mutation tools remain disabled unless DSH_MM_ALLOW_BOUNDED_WRITES=1"
