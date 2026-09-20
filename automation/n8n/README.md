# n8n orchestration — WEBSITE-AUDITOR

This folder provides a **local-only, fail-closed** n8n control plane for MoneyMachine.

MoneyMachine remains the source of truth for the database, evidence, email selection,
suppression, approvals and receipts. n8n only orchestrates bounded actions exposed by
the localhost bridge.

## Safety boundary

- n8n binds to `127.0.0.1:5678` only.
- The MoneyMachine bridge binds to `127.0.0.1:8787` only.
- The bridge requires a bearer token.
- Docker socket access is not exposed.
- Runtime storage is kept on `/Volumes/LLM-USB` by default.
- **External sending is not exposed by the bridge.**
- There is no `send`, `record-sent`, raw SQL, arbitrary shell or arbitrary Python action.
- The old branch version that enabled `LIVE_SEND_ENABLED=1` is intentionally not carried forward.

## Setup

```bash
cd ~/WEBSITE-AUDITOR/automation/n8n
cp .env.example .env
python3 - <<'PY'
import secrets
from pathlib import Path
p = Path(".env")
text = p.read_text()
text = text.replace("MM_BRIDGE_TOKEN=", "MM_BRIDGE_TOKEN=" + secrets.token_urlsafe(32), 1)
p.write_text(text)
PY

./start-n8n.sh
./start-bridge.sh
```

Create an n8n HTTP Header Auth credential named `mmBridgeToken` with:

```text
Authorization: Bearer <the MM_BRIDGE_TOKEN from automation/n8n/.env>
```

## Included workflows

The imported workflows are restricted to status, qualification, email-status,
internal intake/audit, outcomes and daily operations. Brain auto-approval and all
send-related workflows are deliberately excluded until separately reviewed.
