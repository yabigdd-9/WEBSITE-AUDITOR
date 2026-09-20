#!/bin/zsh
set -eu
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/wa ]]; then
  print 'Install first: python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev,browser,portal]"'
  exit 1
fi
if [[ ! -f outputs/toolkit/portal-auth.json ]]; then
  .venv/bin/wa dashboard --set-password
fi
print 'Open http://127.0.0.1:8080 in your browser. Stop with Ctrl+C.'
exec .venv/bin/wa dashboard
