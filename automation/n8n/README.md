# n8n orchestration — WEBSITE-AUDITOR

n8n orchestrates schedules, branching, retries, dashboards, webhooks and transport integrations.
It does NOT replace MoneyMachine's database, verification rules, suppression tables, brain approval logic or send receipts.

## Quick start

```bash
cd automation/n8n
cp .env.example .env        # fill MM_BRIDGE_TOKEN and N8N_VERSION
./start-n8n.sh
```

## Security

- n8n binds to `127.0.0.1:5678` only (localhost).
- USB fail-closed: n8n refuses to start if `/Volumes/LLM-USB` is not mounted.
- Docker socket is NOT exposed to n8n.
- Secrets (`.env`) are never committed to Git.
- MM bridge binds `127.0.0.1:8787` with bearer-token auth and action allowlist.
- n8n cannot run arbitrary shell, SQL, or delete suppression/holds via the bridge.

## Files

| File | Purpose |
|------|---------|
| `compose.yml` | Docker Compose — n8n service |
| `.env.example` | Environment template |
| `.gitignore` | Excludes secrets and runtime data |
| `start-n8n.sh` | Start with USB fail-closed preflight |
| `stop-n8n.sh` | Stop container |
| `healthcheck.sh` | Health check script |
| `backup-n8n.sh` | Backup n8n data and compose |
| `README.md` | This file |