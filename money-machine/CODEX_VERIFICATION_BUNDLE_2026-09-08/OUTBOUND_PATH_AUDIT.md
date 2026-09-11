# Outbound Path Audit
**Generated:** 2026-09-07T19:05:23.124504+00:00

## Summary
All external communication pathways are either BLOCKED, PAUSED, or require explicit human approval. No automated sending is active.

## Discovered Pathways

### 1. Email via himalaya CLI
- **File:** ~/.hermes/cron/jobs.json (paused jobs)
- **Function:** himalaya CLI with --account catalyx and --account yabigdd
- **Active:** NO — both cron jobs are PAUSED
- **Reachable:** YES (himalaya CLI installed and configured)
- **Approval requirement:** Per-message human approval required
- **Risk level:** LOW (paused, no auto-send)

### 2. Email via SMTP (direct)
- **File:** Not found in MoneyMachine scripts
- **Function:** N/A
- **Active:** NO
- **Reachable:** N/A
- **Approval requirement:** N/A
- **Risk level:** N/A

### 3. HTTP POST / Webhook
- **File:** Not found in MoneyMachine scripts
- **Function:** N/A
- **Active:** NO
- **Reachable:** N/A
- **Approval requirement:** N/A
- **Risk level:** N/A

### 4. Slack
- **File:** Not found in MoneyMachine scripts
- **Function:** N/A
- **Active:** NO
- **Reachable:** N/A
- **Approval requirement:** N/A
- **Risk level:** N/A

### 5. SMS
- **File:** Not found in MoneyMachine scripts
- **Function:** N/A
- **Active:** NO
- **Reachable:** N/A
- **Approval requirement:** N/A
- **Risk level:** N/A

### 6. Browser Automation
- **File:** ~/MoneyMachine/data/playwright/ (chromium installed)
- **Function:** Browser automation for evidence capture only
- **Active:** NO (not used for sending)
- **Reachable:** YES (playwright/chromium installed)
- **Approval requirement:** N/A (used for reading, not sending)
- **Risk level:** LOW (read-only usage)

### 7. n8n Workflows
- **File:** ~/MoneyMachine/data/n8n/
- **Function:** Workflow automation
- **Active:** NO — no production workflows, crash journal empty
- **Reachable:** YES (n8n installed)
- **Approval requirement:** N/A
- **Risk level:** LOW (no workflows configured)

### 8. Hermes Agent (autonomous)
- **File:** ~/.hermes/cron/jobs.json
- **Function:** Autonomous agent execution
- **Active:** NO — model_execution_enabled: false, adapters blocked
- **Reachable:** YES (gateway running)
- **Approval requirement:** Human approval required for external actions
- **Risk level:** LOW (disabled by design)

### 9. MoneyMachine mm_operator.py
- **File:** ~/MoneyMachine/scripts/mm_operator.py
- **Function:** Local-only CLI operator
- **Active:** YES (for local operations only)
- **Reachable:** YES
- **Approval requirement:** Per-message human approval required for sends
- **Risk level:** LOW (no network/mail clients, local-only)

### 10. Retired/BLOCKED Scripts
- **File:** scripts/seed_data.py, scripts/fix_contacts.py, scripts/mark_sent.py
- **Function:** All raise SystemExit("BLOCKED: retired one-off migration...")
- **Active:** NO
- **Reachable:** YES (but immediately exits)
- **Approval requirement:** N/A
- **Risk level:** NONE (hard-blocked)

## Conclusion
- **Active outbound pathways:** 0
- **Blocked pathways:** 3 (retired scripts)
- **Paused pathways:** 2 (cron jobs)
- **Read-only pathways:** 1 (browser automation for evidence)
- **Total risk level:** LOW — no automated sending possible without human approval
