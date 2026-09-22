# FABLE MASTER EXECUTION PLAN — v4 (CONSOLIDATED, SINGLE SOURCE OF TRUTH)
## Supersedes: FABLE_EXECUTION_PLAN.md (v2), FABLE_IMPRESSIVE_UPGRADE_PLAN.md (v3), FABLE_EXECUTION_PLAN_V3_ADDENDUM.md
**Repo:** `/Users/dd/WEBSITE-AUDITOR` · **Branch:** `upgrade/v32-canonical-execution` (NEVER master; PR #36 stays draft)
**Executor:** FABLE · **Date:** 2026-09-22 · **Cost:** $0 · **New software:** ZERO

---

## 0. IRON CONSTRAINTS (any violation = STOP and report)

1. **$0 spend:** `paid_allowed=false`, `max_cost_usd=0`. Never set `MM_ALLOW_EXTERNAL_FREE_MODELS=1`.
2. **Zero new software / zero new deps:** no pip/npm/brew installs, no docker pulls, no requirements/pyproject/package.json edits. New code = Python stdlib only, run under `.venv-email` (Python 3.11 — do NOT "fix" with global 3.14).
3. **Fail-closed safety:** `external_send_allowed=false`, `daily_cap=0`, transport `none`. Never touch send/approve/email paths except to add guards/tests. Never send, publish, price-to-customer, or auto-promote.
4. **Frozen surfaces (wrap, never rewrite):** `test_discovery.py` (12 tests), `searxng_candidates()` signature, `mm_pipeline` state transitions, `public_url()` validator strictness.
5. **Loopback-only probes:** 127.0.0.1 only; non-loopback = REJECTED_ENDPOINT before any socket.
6. **Hygiene:** `git status` before every commit; never add `state/*`, `*.db`, `.env`, `reports/` outputs, caches, secrets. One writer per file. One commit per workpath, with test evidence.
7. **Gates:** every phase ends at a GATE with raw command output pasted into the phase report. `BLOCKED`/`DEFERRED`/`SKIPPED` with a recorded reason = PASS. Fake green = FAIL.
8. **DB safety:** `cp database/money_machine.db database/backups/mm_$(date +%Y%m%d_%H%M%S).db` before ANY migration or bulk data change.

## 1. VERIFIED BASELINE (2026-09-22, re-verified this session)

- Supervisor RUNNING, PID 26743 · health OK · `external_sends: 0` · `paid_calls: 0` · `models_enabled: false` · `model_calls: 0`
- Pipeline: `RETRYABLE_FAILURE: 12` · metrics: 48 retry_scheduled / 12 dead_lettered
- **DLQ root cause PROVEN:** all 12 items are `source='test_import'` fixtures (`Acme Corporation` … `not-a-url`); ids 35–40 are byte-identical duplicates of 29–34. Failures: `mm_core.py:42 public_url()` rejects bare domains (no scheme) and non-URLs → 5 retries → dead-letter.
- Funnel: 39 real prospects · **25 with zero evidence** · 0 verified emails · 0 sends (correct — safety holding).
- Environment: no DNS/sockets in sandbox (network_guard errors expected) · launchd install blocked · SearXNG absent (12 discovery tests pass, FROZEN).
- Schema truth: `businesses` columns are `id, name, industry_id, region, public_website, source, discovered_at, current_status, is_dummy` (NO `business_id`/`website`/`state`).

---

## 2. PHASE 0 — LOCK THE BASELINE (30 min, no code)

1. `git status --short && git log --oneline -3`
2. `./mm health; ./mm metrics; ./mm errors; ./mm queue; ./mm dead-letter; ./mm doctor --profile research-only; ./mm pipeline-status`
3. Save raw outputs to `reports/fable/p0_baseline_<date>.md` (do NOT git-add runtime outputs).
4. GATE: supervisor running, $0, 0 sends. If dead: `./mm supervisor start`, re-check, log the recovery.

## 3. PHASE 1 — TEST-DATA QUARANTINE (highest visible win)

**Why first:** the only red in the system (12 DLQ) is 100% test fixtures. Quarantine, don't repair.

1. New `mm data-quarantine --source test_import`: sets `is_dummy=1` + suppression reason `test_fixture` for matching rows; excluded from leased queue, funnel metrics, and reports. Transactional, idempotent, backup first.
2. Transition the 12 DLQ items out of `RETRYABLE_FAILURE` via a new `mm dead-letter resolve --all --reason test_fixture` (never raw SQL; every transition records reason + timestamp).
3. Files: `money-machine/mm_operator.py`, `money-machine/mm_core.py`.
4. Tests: `test_quarantine_excludes_from_queue_and_metrics`, `test_quarantine_idempotent`, `test_quarantine_never_deletes_rows`, `test_dead_letter_resolve_records_reason`.
5. GATE: `./mm dead-letter` empty; `pipeline.items.dead_lettered` stops growing; funnel counts drop the 12 fixtures.

## 4. PHASE 2 — DEDUPE + INTAKE NORMALIZER (prevents recurrence)

1. **Dedupe:** merge duplicate businesses (lowest id wins; FKs re-pointed in ONE transaction; loser suppressed with reason `duplicate_of:<id>`). Regression test proving re-import of the same name+domain adds 0 rows.
2. **Intake URL normalizer** (`normalize_intake_url()`, runs BEFORE `public_url()`): trim, prepend `https://` when scheme missing, lowercase host, strip fragment/userinfo. Validator stays strict afterward — this is intake-time tolerance, not validator weakening.
3. **Reserved-TLD rejection at intake:** `.example`, `.invalid`, `.test`, `example.com/net/org` (RFC 2606) → `suppressed` with reason, never queued, never retried.
4. Tests: `test_dedupe_merges_and_repoints_fks`, `test_dedupe_rolls_back_on_error`, `test_reimport_adds_zero_rows`, `test_bare_domain_gets_scheme`, `test_reserved_tld_suppressed_at_intake`, `test_normalizer_never_accepts_private_ip`, plus keep `test_public_url_rejects_garbage` (validator strictness unchanged).
5. GATE: `./mm intake` of a fixture CSV containing `acme.example.com` + `not-a-url` + a dup → 1 normalized row, 1 suppressed, 0 duplicates, 0 retries burned.
---

## 5. PHASE 3 — NETWORK GUARD & SELF-HEALING CONTINUITY

1. **Multi-probe guard:** env-overridable `MM_NETWORK_PROBE_HOSTS` (default `example.com:443`), tried in order, per-attempt timeout; success if ANY responds. Result cached 60s → max ONE `network_degraded` error row per TTL window (fixes the observed flood: 2 rows/5min).
2. **Degraded mode surfaced:** `mm health` gains `"network": {"mode": "ok|degraded|unknown", "since": ...}`. Deferred-due-to-network workers MUST still heartbeat (supervisor must never reap them as stale) — verify explicitly.
3. **Self-healing continuity without launchd:** new `./mm supervisor ensure-running` (idempotent start-if-dead, no-op-if-alive) + ONE user crontab line (built into macOS, zero new software):
   `*/5 * * * * cd /Users/dd/WEBSITE-AUDITOR && ./mm supervisor ensure-running >> state/ensure-running.log 2>&1` plus same under `@reboot`. Document removal (`crontab -e`) in RUNBOOK.
4. Tests: `test_guard_multi_probe_fallback`, `test_guard_error_dedup_within_ttl`, `test_deferred_worker_still_heartbeats`, `test_ensure_running_noop_when_alive`, `test_ensure_running_no_duplicate_workers`.
5. GATE: `kill -9 <supervisor_pid>` → recovered with NEW pid within 5 min, no duplicate workers, no queue dupes; `mm errors` shows ≤1 network row/hour.

## 6. PHASE 4 — SANDBOX-PROOF TEST SUITE

1. `tests/conftest.py` capability probes: `HAS_SOCKET`, `HAS_DNS`, `HAS_PLAYWRIGHT` (stdlib attempts); dependent tests `pytest.skip(reason=...)` instead of erroring. Red from environment noise teaches operators to ignore red — that is how real regressions slip through.
2. `./mm doctor` reports the three capabilities so "why skipped" is one command away.
3. GATE: full suite green in sandbox AND on host with explicit skip counts; total ≥ 70 tests (58 baseline + all new).

## 7. PHASE 5 — EVIDENCE THROUGHPUT (25 evidence-less prospects → funnel movement)

1. **Audit backfill:** batch `./mm audit <id>` for all 25; even `unreachable` outcomes count as recorded evidence (keeps evidence-first scoring honest).
2. **Free on-site contact discovery:** crawl each prospect's OWN site only (homepage + /contact + /about) via stdlib `urllib` + `html.parser` for `mailto:`, visible emails, forms, phones → `mm_contact_evidence` rows with URL + timestamp provenance. Guessed patterns/MX/catch-all alone NEVER mark verified (P8 policy) — add regression test `test_guess_alone_never_verified`. No external APIs, no new deps. Per-domain politeness delay via stdlib `time.sleep`.
3. **Search lane without SearXNG:** typed `BLOCKED_SEARCH_*` errors instead of raw URLError tracebacks; `discover-search --dry-run` produces a ranked candidate list that works service-absent. Wrap only — frozen signatures.
4. **P5 trace:** every score deduction traceable finding→delta (write `reports/fable/p5_trace.md` demonstrating it).
5. GATE: evidence coverage 39/39 attempted, ≥85% with ≥1 evidence row; `human_review: REQUIRED` unchanged; `outreach_eligible` flips only via existing approval path; funnel shows movement DISCOVERED→AUDITED→QUALIFIED.

---

## 8. PHASE 6 — PROOF-OF-WORK REPORTING & OBSERVABILITY

1. **`./mm report daily`** → `reports/YYYY-MM-DD.md`: funnel delta vs yesterday, new audits/evidence/drafts, DLQ triage actions, guard flaps, safety attestation line (`external_sends: 0 · model_calls: 0 · model_cost_usd: 0.0`), top-3 deterministic next-action recommendations. Stdlib only.
2. `./mm metrics` gains per-stage funnel counts.
3. **Alert rules** `state/alert-rules.yaml` (dead_lettered_growth>0/hr, disk_free<2048MB, heartbeat_age>120s) surfaced as `"alerts": [...]` in `mm health` and the daily report.
4. **Retention:** extend existing logrotate to `state/errors.jsonl` + `state/metrics.jsonl` (30 days).
5. **Negative proof of fail-closed:** pytest proving outreach send is IMPOSSIBLE (cap 0, provider none) — `mm transport-status` + test.
6. Optional (defer if tight): `./mm dashboard` — stdlib `http.server` on 127.0.0.1:8899, one read-only self-refreshing HTML page.
7. Tests: `test_daily_report_contains_safety_attestation`, `test_funnel_counts_per_stage`, `test_alert_rules_evaluate`, `test_errors_jsonl_rotates`, `test_send_impossible_when_fail_closed`.
8. GATE: first `mm report daily` edition attached to the phase report; `mm health` shows alerts array.

## 9. PHASE 7 — RUNBOOK & CLOSEOUT

1. `docs/RUNBOOK.md`: DLQ disposition decision tree, test-data quarantine procedure, supervisor restart / stale-lease recovery / PID-lock removal, cron `ensure-running` install+removal, sandbox-vs-host capability table, backup/restore.
2. Update `CURRENT_STATE.md` with before/after numbers (baseline §1 vs closeout).
3. Closeout summary with every GATE output pasted.

---

## 10. EXECUTION ORDER & GLOBAL ACCEPTANCE

| # | Phase | Gate highlight |
|---|---|---|
| 1 | P0 baseline | green snapshot saved |
| 2 | P1 quarantine | DLQ = 0 |
| 3 | P2 dedupe + normalizer | fixture intake test passes |
| 4 | P3 guards + ensure-running | kill -9 self-recovery proven |
| 5 | P4 test suite | green w/ explicit skips |
| 6 | P5 evidence | ≥85% coverage, funnel moves |
| 7 | P6 reporting | first daily report attached |
| 8 | P7 runbook | human review |

**Run after EVERY phase and paste output:**
```bash
cd /Users/dd/WEBSITE-AUDITOR
./mm health | python3 -c "import json,sys; h=json.load(sys.stdin); assert h['guards']['external_sends']==0 and h['guards']['paid_calls']==0"
python3 -m pytest tests/ -q
./mm doctor
```

**Closeout checklist (all must be true):**
- [ ] DLQ = 0, all 12 fixtures dispositioned (none deleted)
- [ ] Supervisor survives `kill -9` via cron with no duplicate workers
- [ ] Bare-domain intake normalizes; reserved TLDs suppressed at intake; re-import adds 0 dupes
- [ ] ≥85% prospect evidence coverage; contact provenance rows on file
- [ ] `mm report daily` exists; first edition attached
- [ ] `external_sends: 0`, `model_calls: 0`, `model_cost_usd: 0.0` in every report
- [ ] Full suite green (≥70 tests) in sandbox and host

**Human-only, FABLE must never touch:** external sends · model enablement · pricing/quotes to customers · approval decisions · launchd host install · SearXNG host service · merging to master · remote pushes.
