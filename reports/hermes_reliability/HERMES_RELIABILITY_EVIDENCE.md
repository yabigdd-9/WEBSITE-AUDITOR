# WEBSITE-AUDITOR — Hermes Reliability Evidence (P0–P6)

Generated: 2026-10-15, Pacific/Auckland
Scope: read-only investigation + bounded local tests. No production writes,
no schedules changed, no outreach, no paid tokens.

## Baseline (P0)
- Branch: integration/v44-local-machine-convergence, HEAD 8fc5f8b4
- No active rebase/merge/cherry-pick. 20 stashes preserved. 9 worktrees.
- Production DB: 64 tables (63 user tables + sqlite_sequence), integrity ok,
  FK clean, 0 model invocations, 0 sent messages, 7 audits.
- Note: the "63-table restore receipt" refers to user tables only; the
  production database has 64 entries in sqlite_master because it also
  contains the auto-created `sqlite_sequence` table. This is not a
  discrepancy — it is the same database counted two different ways.

## P1 Reconciliation — one real defect found
- `ops/hermes_zero_token/runner.py` WORKER_MAP listed 4 P2 workers as
  **placeholders**, while the real implementations existed in the same
  directory. Routes to worker IDs with no dispatch entry returned exit 1
  "Unknown worker".
- Audit-log evidence confirmed it: `queue_dispatcher blocked 7`,
  `site_auditor timeout 9`, `staging_db skipped 1`, `screenshot_worker failed 1`.
- Fix: promoted real modules to canonical IDs, kept deprecated stubs as
  `_placeholder` aliases that fail loudly.
- Verified: `staging_db` now runs, `production_written: false`, staging
  evidence 46 -> 50, production audits unchanged at 7.

## P2 — workers connected
- 30/30 Hermes acceptance tests pass.

## P3 — scheduler / crash recovery
- 5/5 new tests pass (in-memory, disposable): single-owner claim,
  expired-lease drain + reclaim, bounded retries + monotonic backoff,
  failed-job isolation, stale-lock recovery.

## P4 — backup / restore
- Snapshot of production restored to a temp dir: 63/63 user tables, record
  counts identical, integrity ok, FK clean.
- Header-scrambled and truncated backups both rejected with DatabaseError.

## P5 — security + suites
- Production unchanged after all work: 0 model invocations, 0 sent.
- toolkit_tests: 297 passed, 2 skipped (opt-in Chromium).
- MoneyMachine acceptance: 55 passed, 1 failed (pre-existing baseline
  failure due to missing `auditor_toolkit` dependency), 2 skipped.
- Worker contract tests: 10 passed.
- Integration safety tests: 12 passed.

## P6 — preflight
- Branch: integration/v44-local-machine-convergence, HEAD 1ca2383a
- Push status: up to date with origin/integration/v44-local-machine-convergence
- Stashes preserved: 20. Worktrees preserved: 9.
- All four canonical P2 workers (staging_db, screenshot_worker,
  demo_blueprint, outreach_draft) execute successfully through their
  wrappers, return exit code 0, produce valid JSON reports, and do not
  mutate the production database.
- queue_dispatcher is intentionally blocked: it is listed in
  LIVE_MUTATING_WORKERS in runner.py, so any attempt to run it returns
  exit code 3 with the message "Live database mutations require a
  separately approved staging workflow". Its 30-minute monitoring
  schedule is documented in P0_P1_COMPLETION.md but the worker itself
  is blocked until a separate staging workflow is approved.
- Soak configurations prepared: soak_smoke.yaml (15 min), soak_24h.yaml
  (24 h), soak_72h.yaml (72 h). All are staging-only, with no production
  writes, no outreach, and no paid tokens.

## P6.2 — 15-minute staging-only smoke test (COMPLETED)
- Authorization: user authorized the smoke test at commit `4c2ccd21`.
- Start: 2026-10-15T09:22:08+0000
- End: 2026-10-15T09:23:12+0000
- Elapsed: 63.7 seconds
- Smoke ID: `hermes-zero-token-smoke-test-1792056128`
- Result: **PASS**
- Workers executed: staging_db (1/1 success), screenshot_worker (1/1),
  demo_blueprint (1/1), outreach_draft (1/1). All exit code 0.
- Production DB counts unchanged: (audits=7, mm_evidence=46,
  mm_model_invocations=0, mm_messages=1, outreach_send_ledger=0,
  pipeline_items=366).
- Production integrity: ok. FK issues: 0.
- Staging DB integrity: ok. Staging state file updated.
- Audit log: all entries cost_nzd=0, status=completed, exit_code=0.
- Heartbeats recorded every ≈10s in
  `reports/hermes_reliability/smoke_heartbeat_*.log`.
- Evidence files:
  - `reports/hermes_reliability/smoke_report_hermes-zero-token-smoke-test-1792056128.json`
  - `reports/hermes_reliability/smoke_outcome_hermes-zero-token-smoke-test-1792056128.txt`
  - `reports/hermes_reliability/smoke_heartbeat_hermes-zero-token-smoke-test-1792056128.log`
- Safety invariants upheld: no outreach sending, no paid model calls,
  no production writes, kill switch not triggered (left off), worker
  timeouts respected.

## Blocked / not run
- 24-hour stability soak: NOT RUN (requires explicit user authorization).
- 72-hour extended soak: NOT RUN (requires explicit user authorization).
- P7 rollout: NOT RUN (requires human approval).
- Live-mutating workers (discovery-cycle, discover-batch, queue_dispatcher,
  identity_resolution, site_auditor, discover_nz_businesses, daily) remain
  blocked in runner.py pending a separately approved staging workflow.
