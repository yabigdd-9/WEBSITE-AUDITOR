# HERMES ZERO-TOKEN P0 INVENTORY

## Machine and Hermes
- Hermes Agent: v0.21.7+279.g63d0b94 (2026.9.24) stable local 63d0b9412002
- Install directory: /Users/dd/.hermes/hermes-agent
- Python: 3.14.7
- Cron scheduler: running (PID 69499), no active jobs
- Launchd plists present: ai.hermes.gateway.plist, ai.website-auditor.* (supervisor, searxng, fcc, integrations, a2a-gateway, soak-controller)

## Repository
- Root: /Users/dd/WEBSITE-AUDITOR
- Branch: integration/v44-local-machine-convergence (ahead 1, behind 2)
- Worktrees: multiple (v32-wt, recovery/soak-discovery-review, etc.)
- MM executable: /Users/dd/WEBSITE-AUDITOR/mm (shell -> money-machine/mm_operator.py)
- Venv: .venv/bin/python (3.11.16)
- Venv-email: .venv-email/bin/python (3.11.16)

## Database
- Path: /Users/dd/WEBSITE-AUDITOR/database/money_machine.db
- Size: 3,354,624 bytes
- WAL mode: enabled
- Integrity check: ok
- Foreign key check: no errors
- Tables: 64 (including businesses, audits, mm_jobs, pipeline_items, mm_scores, mm_evidence, mm_holds, mm_suppression, mm_model_invocations)
- mm_model_invocations: 0 rows, cost_usd always 0 (column constraint)
- mm_messages: 1 row, 0 sent
- Businesses status: audited (3), discovered (381), human_review (1)
- Pipeline_items state: NEEDS_REVIEW (22), REJECTED (321), SUPPRESSED (12)

## Tests
- Toolkit tests: 162 passed, 2 skipped (WA_BROWSER_E2E opt-in)
- Money Machine acceptance: 58 passed, 2 skipped (when run from money-machine/ with .venv-email)
- No existing zero-token or hosted-LLM disabling flags found in codebase

## Existing Workers and Guards
- Supervisor: launchd-loaded, running (PID 6144), MM_EXTERNAL_SEND_DISABLED=1
- Supervisor CLI: money-machine/supervisor/cli.py (single-instance, PID lock, heartbeats, disk/network guards)
- mm_runtime_guards: disk_guard (pause_new_work on low disk), network_guard (DNS/TTP probe, caching), accounting_snapshot (reads mm_model_invocations for paid calls)
- mm_pipeline: migration, Worker class, drain_expired_leases
- mm_workers: handlers for identity, audit, understanding, qualification, contact, preparation, outreach_gate, management (all deterministic, no paid inference)
- mm_core: backup() uses SQLite online-backup API, migrate() runs DDL, connect() with readonly/readwrite
- Existing schedules: discovery_schedule.yaml (interval 360m, region NZ, local SearXNG endpoint)

## Directories (created for integration)
- Ops: /Users/dd/WEBSITE-AUDITOR/ops/hermes_zero_token
- State: /Users/dd/WEBSITE-AUDITOR/state/hermes_zero_token
- Reports: /Users/dd/WEBSITE-AUDITOR/reports/hermes_zero_token
- Backups: /Users/dd/WEBSITE-AUDITOR/state/hermes_zero_token_backups (one verified backup)

## Commands Verified
- hermes cron create --no-agent --script --deliver local (supported)
- ./mm doctor --profile research-only (db_integrity ok, models_enabled false, model_calls 0)
- ./mm report daily (no output, presumably dry-run)
- ./mm discovery-cycle --help, discover-batch --help, audit --help, score --help, report --help, outreach-plan --help, daily --help, health --help, supervisor --help

## Missing for Zero-Token Workforce
- No hermes cron jobs yet for zero-token workers
- No dedicated integration/runner scripts
- No explicit zero-hosted-LLM guards in wrapper scripts
- No idempotent queue dispatcher/checkpoint beyond existing mm_pipeline/mm_jobs
- No JSONL audit logs for zero-token workers
- No resource guards beyond existing disk/network guards in supervisor
- No daily report in reports/hermes_zero_token/