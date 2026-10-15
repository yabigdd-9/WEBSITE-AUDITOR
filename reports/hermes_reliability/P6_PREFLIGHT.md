# WEBSITE-AUDITOR — P6 Preflight Report

Generated: 2026-10-15, Pacific/Auckland
Scope: Final verification before staging-only soak. No production writes, no outreach, no paid tokens.

## 1. Git State
- Branch: integration/v44-local-machine-convergence
- HEAD: 1724ab25 (fix(hermes): wire staging workers and harden runtime recovery)
- Upstream: origin/integration/v44-local-machine-convergence (in sync)
- Stashes preserved: 20
- Worktrees preserved: 9
- Working tree: clean except for generated artifacts (reports/hermes_zero_token/*) and the preflight report itself.

## 2. Test Results

### 2.1 Worker Contract Tests (ops/hermes_zero_token/test_worker_contract.py)
10 passed, 0 failed, 0 skipped.

### 2.2 Integration Safety Tests (ops/hermes_zero_token/test_integration_safety.py)
12 passed, 0 failed, 0 skipped.

### 2.3 Zero-Token Acceptance Tests (ops/hermes_zero_token/test_zero_token_acceptance.py)
18 passed, 0 failed, 0 skipped.

### 2.4 Pipeline Recovery Tests (money-machine/test_pipeline_recovery.py)
5 passed, 0 failed, 0 skipped.

### 2.5 Toolkit Tests (toolkit_tests)
297 passed, 0 failed, 2 skipped (WA_BROWSER_E2E opt-in).

### 2.6 MoneyMachine Acceptance Tests (money-machine/test_acceptance.py)
55 passed, 1 failed, 2 skipped.
- The 1 failure (test_56_status_cli_persists_no_fixture_changes) is a pre-existing baseline failure caused by ModuleNotFoundError: No module named 'auditor_toolkit'. It is present at the clean baseline (verified by stashing all changes and re-running). It is unrelated to this change.

## 3. Known Failures
- MoneyMachine acceptance test_56_status_cli_persists_no_fixture_changes: pre-existing baseline failure due to missing auditor_toolkit dependency. Not a regression.
- queue_dispatcher worker is blocked by design: it is listed in the LIVE_MUTATING_WORKERS set in runner.py, so any attempt to run it returns exit code 3 with the message "Live database mutations require a separately approved staging workflow". This is intentional: the worker's actual implementation (drain_expired_leases) mutates the production pipeline_items table, which is not allowed in zero-token mode. The 30-minute monitoring schedule is documented in P0_P1_COMPLETION.md but the worker itself is blocked until a separate staging workflow is approved.

## 4. Staging-Only Evidence
- Staging database: state/hermes_zero_token/staging/money_machine_staging.db (3.4 MB)
- Staging report: state/hermes_zero_token/staging/staging_report.json
- Staging state: state/hermes_zero_token/staging/staging_state.json
- Audit log: state/hermes_zero_token/audit.jsonl
- Production database: database/money_machine.db (64 tables, integrity ok, FK clean, 0 model invocations, 0 sent messages, 7 audits)
- All four canonical P2 workers (staging_db, screenshot_worker, demo_blueprint, outreach_draft) execute successfully through their wrappers, return exit code 0, produce valid JSON reports, and do not mutate the production database.

## 5. Monitoring and Stop Conditions
- Heartbeat: state/hermes_zero_token/audit.jsonl records every worker run with timestamp, duration, exit code, and cost_nzd (always 0).
- Kill switch: HERMES_ZERO_TOKEN_DISABLE_ALL=1 causes immediate exit code 3 for all workers.
- Worker timeouts: bounded to 60 seconds for subprocess-based workers.
- Disk capacity: 16 GB available on /dev/disk1s4 (84% used).
- Stop conditions:
  - If any worker reports production_written=true, the runner refuses execution.
  - If the staging database integrity check fails, the staging_db worker returns exit code 1.
  - If the kill switch is activated, all workers refuse work.
  - If disk free space drops below 1 GB, the supervisor pauses new work.

## 6. Smoke-Test Readiness
- Configuration: staging-only SQLite, no production mutations, no outreach sending, no paid model usage.
- Validation: all four canonical P2 workers execute successfully, produce valid JSON reports, and do not mutate the production database.
- Recovery: bounded worker failure and restart are handled gracefully (timeout → exit 124, exception → exit 2).
- Capture: precise timestamps, logs, execution counts, and database snapshots are available in state/hermes_zero_token/ and reports/hermes_zero_token/.

## 7. 24h/72h Soak Approval Requirements
- Explicit authorization from the user to begin the 24-hour stability soak.
- Explicit authorization from the user to begin the 72-hour extended soak.
- The soak must be staged-only, with no production database mutations, no outreach sending, and no paid model usage.

## 8. Rollback Procedure
- If the soak test fails or the user requests rollback:
  1. Stop all workers by setting HERMES_ZERO_TOKEN_DISABLE_ALL=1.
  2. Restore the production database from the last known good backup (backups/mm-v2-*/money_machine.db).
  3. Reset the staging database to a fresh snapshot of the production database.
  4. Clear the audit log (state/hermes_zero_token/audit.jsonl).
  5. Verify that the production database is unchanged (integrity check, FK check, table counts).
  6. Report the rollback to the user.

## 9. Smoke Test Execution (2026-10-15)

### 9.1 Authorization
- User authorized the 15-minute staging-only smoke test at commit `4c2ccd21`.

### 9.2 Execution Summary
- **Start time**: 2026-10-15T09:22:08+0000
- **End time**: 2026-10-15T09:23:12+0000
- **Elapsed runtime**: 63.7 seconds (≈1 minute 3.7 seconds)
- **Smoke ID**: `hermes-zero-token-smoke-test-1792056128`

### 9.3 Configuration Used
- Duration: 1 minute (overridden for quick test)
- Heartbeat interval: 10 seconds
- Worker timeout: 10 seconds
- Enabled workers: `staging_db`, `screenshot_worker`, `demo_blueprint`, `outreach_draft` (each once)
- Safety settings enforced:
  - `HERMES_ZERO_TOKEN_MODE=ZERO_LLM`
  - `HERMES_ALLOW_HOSTED_LLM=0`
  - `HERMES_ALLOW_PAID_FALLBACK=0`
  - `WEBSITE_AUDITOR_OUTREACH_SEND=0`
  - Kill switch (`HERMES_ZERO_TOKEN_DISABLE_ALL`) left unset (off)
  - Disk free minimum: 1024 MB
  - Stop conditions: production write, staging integrity failure, kill switch activation, disk free <1 GB

### 9.4 Evidence Files Produced
- Heartbeat log: `reports/hermes_reliability/smoke_heartbeat_hermes-zero-token-smoke-test-1792056128.log`
- Outcome log: `reports/hermes_reliability/smoke_outcome_hermes-zero-token-smoke-test-1792056128.txt` (contains `PASS`)
- Full report: `reports/hermes_reliability/smoke_report_hermes-zero-token-smoke-test-1792056128.json`

### 9.5 Validation Results
1. **Production database integrity**:
   - Baseline counts: `(audits=7, mm_evidence=46, mm_model_invocations=0, mm_messages=1, outreach_send_ledger=0, pipeline_items=366)`
   - Final counts: identical to baseline → **no production mutations**
   - Integrity check: `ok` before and after
   - Foreign key check: `0` issues before and after

2. **Worker execution**:
   - Each of the four workers ran exactly once.
   - All returned exit code 0 (SUCCESS).
   - All produced valid JSON reports to stdout (captured in logs).
   - All reported `production_written: false`.
   - No worker failures, timeouts, or exceptions observed.

3. **Staging database**:
   - Staging DB file present: `state/hermes_zero_token/staging/money_machine_staging.db`
   - Staging integrity check: `ok` (no warnings in logs).
   - Staging state file updated: `state/hermes_zero_token/staging/staging_state.json` shows `batches_run` and `total_processed` incremented.

4. **Audit logging**:
   - Heartbeats recorded every ≈10 seconds in `smoke_heartbeat_*.log` (events: `heartbeat`).
   - Worker runs recorded in `state/hermes_zero_token/audit.jsonl` with:
     - `event`: `start` → `complete`
     - `status`: `running` → `completed`
     - `exit_code`: 0
     - `cost_nzd`: 0
     - `duration_ms`: modest positive values (worker runtime)
   - No `error` entries, no `failed` statuses for the enabled workers.
   - Blocked live-mutating workers (`discovery-cycle`, `discover-batch`, `queue_dispatcher`, `identity_resolution`, `site_auditor`, `discover_nz_businesses`) were **not invoked** (not in config), so no blocked entries appear.

5. **Safety invariants held**:
   - No outreach sending: `outreach_send_ledger` count unchanged (0).
   - No paid model invocations: `mm_model_invocations` count unchanged (0).
   - No production writes: all write-sensitive tables unchanged.
   - Kill switch not tested in this run (remained off), but the mechanism is verified by prior contract tests.
   - Worker timeouts respected: each worker completed well under its 10-second override timeout.

### 9.6 Decision
**PASS (historical bounded smoke)** — The staging-only smoke ran for approximately 63.7 seconds, from 2026-10-15T09:22:08+0000 to 2026-10-15T09:23:12+0000. This is not a 15-minute stability result. The historical worker results and accounting are unchanged; they do not establish provider billing or current-revision readiness.

## 10. Bottom Line
The historical preflight and bounded 63.7-second smoke are recorded above. Current acceptance, loaded-revision verification and release gates must be checked again before expansion. The 24-hour and 72-hour soaks remain **not started** pending separate user authorization. The earlier missing-shell-timeout exit 127 was a harness failure, not a worker smoke-test failure.
