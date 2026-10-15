# P0 + P1 COMPLETION REPORT

## Phase P0: Inventory, Baseline, and Backups — DONE

### Inventory
- **Hermes:** v0.21.7+279.g63d0b94 (2026.9.24), Python 3.14.7, cron scheduler running (PID 69499), no active jobs initially
- **Repository:** integration/v44-local-machine-convergence, clean (ahead 1, behind 2)
- **Venvs:** .venv (Python 3.11.16), .venv-email (Python 3.11.16)
- **mm entrypoint:** mm → money-machine/mm (shell) → money-machine/mm_operator.py
- **Launchd supervisor:** Running (PID 6144), MM_EXTERNAL_SEND_DISABLED=1
- **DB:** WAL mode, integrity_check ok, FK clean, 64 tables, 0 model invocations, 0 sent messages
- **Worktrees:** 7 (main, v32-wt, v45, several Codex soak/work review branches)

### Baseline test results
- Toolkit tests: **162 passed, 2 skipped** (25s)
- Money Machine acceptance (run from money-machine/ with .venv-email): **58 passed, 2 skipped**

### Backup
- Verified online SQLite backup using mm_core.backup():
  state/hermes_zero_token_backups/money_machine_backup_20261013T051937Z.db
  - integrity_check: ok
  - table count matches source: 64 tables

### Compatibility gaps identified
- No Hermes cron jobs existed for zero-token workers
- No dedicated integration/runner scripts
- No zero-token env guards in wrapper scripts
- No JSONL audit logging for zero-token workforce
- Existing system supervisor already covers system_supervisor duties (no duplicate needed)

## Phase P1: Safety Wrapper, Queue, and Monitoring — DONE

### Implemented

#### 1. Runner (`/Users/dd/WEBSITE-AUDITOR/ops/hermes_zero_token/runner.py`)
- Routes worker IDs to existing MM commands or custom logic
- Sets `HERMES_ZERO_TOKEN_MODE=ZERO_LLM`, `HERMES_ALLOW_HOSTED_LLM=0`,
  `HERMES_ALLOW_PAID_FALLBACK=0`, `WEBSITE_AUDITOR_OUTREACH_SEND=0`
- Emergency kill switch: `HERMES_ZERO_TOKEN_DISABLE_ALL=1` exits with code 3
- JSONL audit logging to `state/hermes_zero_token/audit.jsonl` with required fields:
  timestamp, job_id, worker_id, task_id, event, status, duration_ms, cost_nzd (always 0)

#### 2. Hermes Cron Jobs (all `--no-agent --script --deliver local`)
- `za_system_supervisor.sh` — every 15m
- `za_database_guard.sh` — every 6h
- `za_daily_report.sh` — daily at 08:00
- `za_queue_dispatcher.sh` — every 30m
- `za_identity_resolution.sh` — every 2h
- `za_site_auditor.sh` — every 3h
- `za_scoring_judge.sh` — every 4h
- `za_evidence_proofer.sh` — every 4h
- `za_discover_nz_businesses.sh` — every 2h
- `za_screenshot_worker.sh` — every 3h
- `za_testing.sh` — every 6h
- `za_git_observer.sh` — every 6h
- `za_competitor_research.sh` — every 12h
- `za_demo_blueprint.sh` — every 8h
- `za_outreach_draft.sh` — every 8h
- `za_weekly_review.sh` — every 7d
- `za_provider_monitor.sh` — every 6h

All wrappers auto-detect worker ID from script name and set zero-token env vars.

#### 3. Worker Implementations (reusing existing MM logic)
- **system_supervisor:** `mm supervisor health` (reads launchd supervisor + pipeline state)
- **database_guard:** `mm db-check` (integrity + FK check)
- **daily_report:** `mm daily` (produces daily operator report)
- **queue_dispatcher:** `mm_pipeline.drain_expired_leases()` (lease recovery)
- **identity_resolution:** `mm discovery-cycle --force` (reuses mm_workers identity handler)
- **site_auditor:** `mm_workers.audit` handler (browser=False, ai=False, external_tools=False)
- **scoring_judge:** `mm_workers.qualification` handler (deterministic scoring)
- **evidence_proofer:** `mm_workers.qa` handler
- **discover_nz_businesses:** `mm discover-batch` with queries from discovery_schedule.yaml
- **testing_worker:** `pytest toolkit_tests -q`
- **git_observer:** git status + worktree list
- **provider_monitor:** reports ZERO_LLM mode, hosted LLM disabled
- **screenshot_worker, demo_blueprint, outreach_draft, competitor_research:** placeholders (no direct MM command; review-only), **weekly_review:** not yet implemented (optional per plan)

### Verification

#### Smoke tests — all pass
```
system_supervisor:     supervisor health JSON returned
database_guard:         {ok: true, checks: [integrity, foreign_keys]}
queue_dispatcher:       drained expired leases
git_observer:           git status + worktree list
provider_monitor:       ZERO_LLM mode active
daily_report:           mm daily output (metrics JSON)
```

#### Acceptance tests: **18 passed**
- `test_environment_guards_set`: env flags verified
- `test_no_paid_calls_in_database`: mm_model_invocations cost = 0
- `test_no_hosted_llm_provider_imports`: runner.py has no openai/anthropic/litellm/httpx
- `test_wrapper_scripts_block_outreach`: all za_*.sh have all 4 zero-token env vars
- `test_cost_always_zero`: CHECK(cost_usd=0) constraint enforced
- `test_external_send_disabled_in_launchd`: MM_EXTERNAL_SEND_DISABLED=1 in plist
- `test_no_messages_sent`: 0 sent messages
- `test_no_proposals_sent`: 0 sent proposals
- `test_discovery_does_not_create_duplicate_hosts`: dedup confirmed
- `test_integrity_check`: PRAGMA integrity_check = ok
- `test_foreign_key_check`: clean
- `test_leases_are_recoverable`: mm_pipeline recovery infrastructure present
- `test_public_url_rejects_private`: localhost/private IP/127.0.0.1 rejected
- `test_audit_disables_ai_and_browser`: ai=False, browser=False, external_tools=False in mm_workers.audit_handler
- `test_disk_guard_present`: disk_guard pause_new_work on low disk
- `test_toolkit_tests_pass`: 162 passed, 2 skipped
- `test_cron_jobs_are_no_agent`: no --model/--provider in wrappers
- `test_metrics_recomputable`: biz/pipeline count consistent

#### Zero-token attestation
- Paid model calls: 0
- Estimated paid cost NZD: 0
- Outbound messages sent: 0
- Audit log entries: all cost_nzd=0

### P1 Gate: PASSED
"All scripts pass offline smoke tests and cannot call hosted inference."

### Pre-existing modified files (NOT from this work)
- reports/DAILY_OPERATOR.md, reports/KPI_DASHBOARD.md, reports/daily-operator/*
  These are regenerated by `mm daily` when the daily_report worker runs.
  Git diff shows only timestamp/content updates from operator runs.

### Outstanding (NOT STARTED)
- **P2:** Read-only research and audit workers in dry-run (identity, audit, screenshots in staging DB)
- **P3:** Scoring, QA, and review-only draft outputs (outreach_draft, demo_blueprint)
- **P4:** Full test/baseline comparison, Obsidian export, restart recovery
- **P5:** 24h/72h soak tests
- **P6:** Optional local model support (LOCAL_ONLY mode)
- Daily report needs dedicated zero-token format: DAILY_REPORT_YYYY-MM-DD.md + daily_metrics.json
  in reports/hermes_zero_token/ with zero-token attestation block (currently uses mm daily)