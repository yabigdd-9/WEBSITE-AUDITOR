# FABLE EXECUTION PLAN — Impressive Free-Only Upgrade (v2, evidence-grounded)

**Repo:** `/Users/dd/WEBSITE-AUDITOR` · **Branch:** `upgrade/v32-canonical-execution` (do NOT merge to master; PR #36 stays draft)
**Hard constraints:** $0 spend · `paid_allowed=false`, `max_cost_usd=0` · `external_send_allowed=false`, `daily_cap=0`, transport `none` · no paid models/APIs/purchases/remote pushes · no new software installs (use only: system Python + `.venv-email`, Docker Desktop 29.8, Chromium/Playwright if present, local node/npm, Obsidian app, user-level launchd only on explicit ask) · never commit secrets/DBs/reports/caches/state · one writer per file · test evidence per change.
## v2 GROUND-TRUTH CORRECTIONS (verified 2026-09-22 — Fable, trust these over any earlier note)
1. **Schema**: `businesses` has NO `business_id`/`website`/`state` columns. Canonical columns: `id, name, industry_id, region, public_website, source, discovered_at, current_status, is_dummy`. Correct drill-down:
   `sqlite3 database/money_machine.db "SELECT id,name,public_website,region,current_status FROM businesses WHERE id BETWEEN 29 AND 40 ORDER BY id;"`
2. **DLQ root cause located**: `money-machine/mm_core.py:42` — `normalise_public_website()` raises `ValueError('Public HTTP(S) website URL required')` for non-URL values (e.g. id 34 & 40: `not-a-url`). Identity worker crashes on intake; retry → dead-letter. Fix is disposition/tolerance, NOT weakening the validator for new intake.
3. **Dedupe gap confirmed (free win)**: ids 35–40 are byte-identical duplicates of 29–34, all `current_status='discovered'`. Re-import added 6 rows → dedupe key currently missing/unused on this path. Phase 5.1 must fix with a regression test.
4. **SearXNG call site**: single wiring point `money-machine/mm_operator.py:282` calling `mm_discovery.searxng_candidates()` (`mm_discovery.py:306`). Signature + 12 tests in `test_discovery.py` are FROZEN — Layer A wraps, never rewrites. Loopback-only enforcement lives in `_loopback_endpoint()`.

**Baseline 2026-09-22 (verified):** supervisor RUNNING PID 26743 · health OK, external_sends 0, models_enabled false, model_calls 0 · metrics: 48 retry_scheduled / 12 dead_lettered · 12 DLQ items, identity worker `ValueError: Public HTTP(S) website URL required` · doctor research-only: db integrity OK · working tree: only untracked runtime files.

> Fable: phases in order. Stop-and-report at each GATE. Never weaken safety to bypass a sandbox. Missing host capability = record BLOCKED/DEFERRED + move on.

## PHASE 0 — Lock baseline (30 min, no code)
1. `git status --short && git log --oneline -3`
2. `./mm health; ./mm metrics; ./mm errors; ./mm queue; ./mm dead-letter; ./mm doctor --profile research-only`
3. `./mm supervisor status; ./mm supervisor health` (or `logs | tail -40`)
4. Save to `reports/fable/p0_baseline_<date>.md` (check .gitignore; do NOT git-add runtime outputs).
5. GATE: supervisor running, $0, 0 sends. If dead: `./mm supervisor start`, re-check, log it.

## PHASE 1 — DLQ triage (most visible win; free) — UPDATED
Why first: 12/12 DLQ items share one root cause — `mm_core.py:42` rejects prospects whose `public_website` is not a valid public HTTP(S) URL (verified: `not-a-url` rows exist in DB).
1. `./mm dead-letter > /tmp/fable_dlq.json`; classify: missing-URL vs malformed-URL vs unactionable. Cross-check each DLQ business id against the DB query in v2 correction #1.
2. Confirm validator behavior: (a) new intake still rejects bad URLs (`normalise_public_website('not-a-url')` raises — add/keep unit test), (b) historical malformed rows are tolerated + logged, never crash-looped.
3. Code win (test-backed): DLQ disposition classifier — `needs_url_repair` (re-queueable after enrichment) vs `unactionable` (suppress with reason, never delete). Enrich dead-letter view with why + next-action per item.
4. Tests: toolkit suite + acceptance run; record pass line.
5. GATE: 12/12 explained, none deleted, $0/0-sends intact.
## PHASE 2 — Control-plane hardening P3 (no host privileges)
1. `./mm supervisor restart` → status → same queue depth, no dupes (diff business_id list), heartbeat fresh.
2. Kill-and-recover: `kill <pid>` → `./mm supervisor start` → `start` twice: second must refuse (PID lock).
3. Check `state/` sizes + `supervisor/logrotate.py` config (no unbounded growth).
4. Record `reports/fable/p3_recovery_<date>.md`; update CURRENT_STATE.md P3 row.
5. launchd: DO NOT install to ~/Library/LaunchAgents without explicit owner ask. Only `cd money-machine && ../.venv-email/bin/python -m supervisor.launchd status`; else record BLOCKED. Direct supervisor = equivalent continuity.
6. GATE: restart proven, no duplicates, DLQ intact.

## PHASE 3 — SearXNG (P6) — FOLLOW docs/SEARXNG_SERVICE_PLAN.md (it supersedes this section)
Why: that doc has verified ground truth (G1–G12, captured 2026-09-22): discovery suite 12/12 green, port 8888 free, lane currently fails opaque (curl exit 7), Docker API NOT usable (Tier 2 only), Python 3.11 available via uv (no new software), upstream needs `search.formats += json`, no redis/uwsgi needed, `pip install searxng` is a wrong-package trap, wiring is one call site (mm_operator.py:277-288), metrics surface exists.
Design (two layers): Layer A (always-on, in-repo, stdlib-only mm_search_backend.py: probe/search/cache/breaker) + Layer B (optional host-level: ~/.local/share/searxng .venv on Python 3.11, `python -m searx.webapp` → 127.0.0.1:8888, settings add json, SEARXNG_SECRET env; AGPL code + venv stay OUTSIDE the repo; only wrapper scripts/in-repo). Rules: stdlib only, keep searxng_candidates() signature (12 tests frozen), loopback-only, named BLOCKED_SEARCH_* states never tracebacks.
CORRECTION to earlier draft: Docker path is Tier-2 opt-in only (docker API unavailable per G4) — default path is Layer A + optional Layer B venv, zero new system software.
Execution order per that doc: P0 typed BLOCKED states + --dry-run + discovery fallback docs (no service needed); P1 Layer A backend + cache/replay + breaker + metrics + doctor search block + offline replay tests; P2 Layer B scripts/searxng.sh + launchd user agent + verify; P3 provenance into identity/qualifier; P4 README runbook + rollback.
GATE: Layer A works with service ABSENT (typed BLOCKED + import fallback documented, tests green, no new deps); if Layer B installed, one loopback query with DISCOVERED-only evidence; loopback-only; AGPL/venv outside repo.


## PHASE 4 — Audit real-tool pass P4 (never auto-download)
1. Inventory: `which chromium; ls ~/.cache/ms-playwright; which lighthouse lychee node npx`.
2. Chromium present → `WA_BROWSER_E2E=1 .venv-email/bin/python -m pytest toolkit_tests/test_browser_e2e.py toolkit_tests/test_monthly_browser_e2e.py -q`.
3. lighthouse+lychee present → `wa audit https://example.co.nz --profile nz --external-tools` on fixture/local target. Absent → record SKIPPED (policy: never download) — that IS passing.
4. Always: `wa audit https://example.co.nz --profile nz` deterministic must pass.
5. GATE: matrix recorded (browser yes/skipped, external-tools yes/skipped, deterministic yes).
## PHASE 5 — Every-workpath polish (one win per lane, each = 1 focused commit + test) — UPDATED
1. dedupe: **VERIFIED GAP** — ids 35–40 duplicate 29–34 in `discovered` status. Fix: dedupe on `(canonical_host, name, region)` or `public_website` at import; re-import same fixture twice → 2nd adds 0. Add regression test using the exact 29–40 fixture.
2. identity: Phase 1 follow-through; malformed-URL tolerance test if missing.
3. audit→packet: `wa audit → wa remediate → wa demo --render → wa quote → wa packet` on fixture; packet = HUMAN_APPROVAL_REQUIRED, demo JSON CONCEPT_ONLY + live_site_changed=false.
4. quote P12: LLM cannot price (fixed NZD rules; re-run pricing test).
5. draft/review P13-14: `./mm transport-status` → none/cap 0. Attempt nothing live.
6. models P15: `./mm model-routes` → local-first/DEFER, ledger 0; MM_ALLOW_EXTERNAL_FREE_MODELS unset.
7. observability P17: `./mm observability-snapshot` → health.json, metrics.jsonl, errors.jsonl, dead-letter/, worker-heartbeats/ update with NO db mutation.
8. learning P18: `./mm outcomes` read-only; challenger recommends only, never promotes.
9. Obsidian: `./mm obsidian-status` + `obsidian-sync` vs real vault WEBSITE-AUDITOR-BRAIN (read-mostly; closing Obsidian never stops pipeline).
10. GATE: every lane has a recorded line; failures get focused fix+test, never mass-merge.

## PHASE 6 — 24h soak + closeout
1. Leave supervisor running ≥24h; capture health/metrics/errors/dead-letter/observability-snapshot.
2. Soak acceptance: no dupes, DLQ visible+triaged, $0.00 models, 0 sends.
3. Update CURRENT_STATE.md phase table + CLAUDE.md baseline with commands+results.
4. Focused commit(s) on upgrade/v32-canonical-execution only; push branch; PR #36 stays draft. Final report: per-workpath before→after + soak numbers + deferred list.

## WIN CHECKLIST (what "better" means per workpath) — v2 CONSOLIDATED
- discover: loopback SearXNG OR clean typed BLOCKED_SEARCH_* DEFERRED (no tracebacks when service absent) + NZBN import proven
- dedupe: re-import of the 29–40 fixture adds 0 (regression test) — VERIFIED GAP: ids 35–40 currently duplicate 29–34
- identity: DLQ dispositions + `mm_core.py:42` validator-tolerance test (new intake still rejects bad URLs)
- dlq: requeue works, invalid intake never retry-loops, 12/12 → triaged AND dispositioned
- guards: no-DNS environment no longer stalls workers or floods error log
- continuity: supervisor self-heals via cron `ensure-running` (kill -9 proven); PID lock refuses second start
- evidence: ≥85% prospect coverage, contact provenance rows on file
- audit: deterministic yes + browser/external matrix | verify/score: evidence-linked deductions
- remediate/demo/quote: CONCEPT_ONLY demo, fixed NZD pricing | draft/review/send: send provably impossible
- models: $0 ledger, DEFER-not-pay | observability: snapshot w/o db mutation
- learning: outcomes read-only, no auto-promote | Obsidian: real-vault sync, non-authoritative
- SearXNG: 12/12 frozen discovery tests green after Layer A; one live loopback query if Layer B installed; AGPL/venv outside repo; 127.0.0.1 binding only
- reporting: `mm report daily` produces the impressive update on demand
- observability: snapshot w/o db mutation | learning: outcomes read-only, no auto-promote
- Obsidian: real-vault sync, non-authoritative

---

## ADDENDUM v2 — Gap-fill pass (2026-09-22, verified against live system)

Live re-verification confirmed the plan's baseline (PID 26743 alive, 48 retries / 12 DLQ, $0, 0 sends). It also surfaced **five gaps the original plan doesn't close**. FABLE: execute these as Phase 1.5 (before Phase 2), each with a focused commit + test.

### G1 — DLQ has no requeue path (triage without requeue is a dead end)
Original Phase 1 adds dispositions but no way back into the queue.
- Add `./mm dead-letter requeue <business_id|all>`: resets `attempts=0`, restores origin state, **refuses** if the record still fails intake validation (prevents re-entering the retry loop).
- Add intake fail-fast: invalid/missing URL → new state `DATA_INVALID` on attempt 1, never leased. (Root cause of all 12 current DLQ items: `ValueError: Public HTTP(S) website URL required` burning 5 retries each.)
- Validation errors (ValueError) = permanent → dead-letter immediately; network errors = retryable → keep backoff+jitter.
- Tests: `test_requeue_resets_attempts`, `test_requeue_refuses_still_invalid`, `test_validation_error_dead_letters_immediately`.

### G2 — Network guard cries wolf in no-DNS environments
`./mm errors` shows repeated `network_guard` failures: probe target `example.com:443` unresolvable here → network workers defer indefinitely and the error log fills with duplicates.
- Probe a configurable list (config entry + IP-literal fallback), verdict `down` only if ALL fail.
- Dedupe guard-flap errors: one entry per 15-min window, not one per cycle.
- Workers deferring due to guard must still heartbeat (verify; supervisor must not reap them as stale).
- Tests: `test_guard_multi_probe_fallback`, `test_guard_error_dedup`, `test_deferred_worker_still_heartbeats`.

### G3 — No auto-restart without launchd (supervisor dies with the terminal)
launchd install is sandbox-blocked; original plan accepts manual restart as "equivalent" — it isn't after a reboot.
- Add `./mm supervisor ensure-running`: idempotent start-if-dead, no-op-if-alive.
- Install ONE user crontab line (built into macOS, zero new software, user-level only — allowed by constraints):
  `*/5 * * * * cd /Users/dd/WEBSITE-AUDITOR && ./mm supervisor ensure-running >> state/ensure-running.log 2>&1`
  plus the same line under `@reboot`.
- Acceptance: `kill -9 <pid>` → recovered with new PID within 5 min, no duplicate workers. Document removal (`crontab -e`) in RUNBOOK.

### G4 — 25 prospects have zero evidence; all contacts are NO_VERIFIED_EMAIL
`./mm status`: `prospects_without_any_evidence: 25`, every email contact unverified. The funnel can't produce review-ready packets without this.
- Evidence backfill: batch `./mm audit <business_id>` for the 25; even `unreachable` outcomes are recorded evidence (keeps P5 evidence-first honest).
- Free contact discovery: crawl each prospect's OWN site only (homepage + /contact + /about) via stdlib `urllib`+`html.parser` for `mailto:`, visible emails, forms, phones → `mm_contact_evidence` rows with URL/timestamp provenance. Guessed patterns still never count as verified (P8). No external APIs, no new deps.
- Acceptance: evidence coverage 39/39 attempted, ≥85% with ≥1 evidence row; `human_review: REQUIRED` unchanged; `outreach_eligible` only flips via existing approval path.

### G5 — No standing "impressive update" artifact
Original plan produces reports only at phase gates. Make proof-of-work automatic.
- `./mm report daily` → `reports/YYYY-MM-DD.md`: funnel delta vs yesterday, new audits/evidence/drafts, DLQ triage actions, guard flaps, safety attestation line (`external_sends: 0 · model_calls: 0 · model_cost_usd: 0.0`), top-3 recommended next actions. Stdlib only, no services.
- `./mm metrics` gains funnel counts per stage (DISCOVERED→…→REVIEW_QUEUED) so the daily report has real numbers.
- Optional `./mm dashboard`: stdlib `http.server` on 127.0.0.1:8899, one self-contained read-only HTML page, 30s refresh. (Defer if time is tight — the daily report is the must-have.)

### Updated WIN CHECKLIST additions
- dlq: requeue works, invalid intake never retry-loops, 12/12 → triaged AND dispositioned
- guards: no-DNS environment no longer stalls workers or floods error log
- continuity: supervisor self-heals via cron `ensure-running` (kill -9 proven)
- evidence: ≥85% prospect coverage, contact provenance rows on file
- reporting: `mm report daily` produces the impressive update on demand

### Updated global acceptance (all must be true at closeout)
- [ ] DLQ = 0 or 100% triaged + dispositioned (requeued or suppressed, none deleted)
- [ ] Supervisor survives `kill -9` via cron without human action
- [ ] Funnel shows movement through every stage; ≥1 human-review-ready packet per qualified prospect
- [ ] `./mm report daily` exists and its first edition is attached to the final summary
- [ ] `external_sends: 0`, `model_calls: 0`, `model_cost_usd: 0.0` in every report
- [ ] Full test suite green (58 baseline + all new tests)

## SAFETY REMINDERS
- Default MM_PYTHON (.venv-email); project runtime is 3.11 — don't "fix" with global 3.14.
- `git status` before every commit; never add state/, *.db, reports/ outputs, .env, caches.
- Never touch master. Never load launchd unasked. Never expose SearXNG beyond 127.0.0.1. Never send/publish/quote-to-customer.

---

## ADDENDUM v3 — FABLE EXECUTION ORDER (2026-09-22, live-verified)

**Verified state:** supervisor green (PID 26743, heartbeat fresh) · DLQ 12 (all RETRYABLE_FAILURE, attempts 5/5) · SearXNG absent on 127.0.0.1:8888 (curl exit 7) · `uv` + `python3.11` present at `/Users/dd/.local/bin/` → Layer B feasible with ZERO new software · no `scripts/` dir yet.

Execute in this exact order. Each step = one focused commit + test evidence. Stop-and-report at each GATE.

### STEP 1 — DLQ disposition + requeue (unblocks the funnel) [~1h]
1. All 12 DLQ items trace to `mm_core.py:42` ValueError on `not-a-url` rows (business_id 34, 40 lineage).
2. Implement DispositionClassifier → `needs_url_repair` | `unactionable` (suppress-with-reason, never delete).
3. Implement `./mm dead-letter requeue <id|all>`: resets attempts, REFUSES if `normalise_public_website()` still raises (fail-fast, no retry loop).
4. Intake fail-fast: ValueError → `DATA_INVALID` on attempt 1, never leased; network errors stay retryable with backoff.
5. Tests: `test_requeue_resets_attempts`, `test_requeue_refuses_still_invalid`, `test_validation_error_dead_letters_immediately`, `test_classifier_dispositions`.
6. GATE: 12/12 dispositioned, none deleted, health shows dead_lettered → 0 or suppressed-counted.

### STEP 2 — Dedupe regression fix (verified 6-row gap) [~30m]
1. Dedupe imports on `(canonical_host, public_website)`; re-import of the 29–40 fixture must add 0 (ids 35–40 currently duplicate 29–34).
2. Test: `test_reimport_fixture_adds_zero` using the exact 29–40 fixture. Do NOT silently delete existing 35–40 rows — surface them in the report.
3. GATE: re-import adds 0.

### STEP 3 — SearXNG Layer A (in-repo, stdlib-only, works with service ABSENT) [~2h]
1. Create `money-machine/mm_search_backend.py`: `probe()`, `search()`, disk cache (`state/search-cache/`, TTL), circuit breaker, typed `BLOCKED_SEARCH_UNREACHABLE` / `BLOCKED_SEARCH_DISABLED` states — never tracebacks.
2. Wire the ONE call site (`mm_operator.py:282`) through the backend; keep `searxng_candidates()` signature untouched (12 frozen tests stay green).
3. Add `./mm doctor search` block: probe → cache-replay → typed verdict. Metrics: `search_probes`, `search_cache_hits`, `search_breaker_state`.
4. Tests: offline replay (service absent → typed BLOCKED, no exception), cache hit, breaker open/half-open.
5. GATE: full suite green, zero new deps, service still absent and nothing crashes.

### STEP 4 — SearXNG Layer B (host-level service, free, no new software) [~45m]
Everything lives OUTSIDE the repo except the wrapper script. Use uv venv, not system pip.
1. `mkdir -p ~/.local/share/searxng && cd ~/.local/share/searxng`
2. `uv venv --python 3.11 .venv && .venv/bin/pip install searxng` (correct PyPI package ≈ searx; verify: `.venv/bin/python -c "import searx"`).
3. `~/.local/share/searxng/settings.yml`: extend `searx.settings` defaults PLUS `search: {formats: [html, json]}` (upstream requirement), `server: {bind_address: 127.0.0.1, port: 8888, secret_key: <openssl rand -hex 32>}`. No redis, no uwsgi.
4. `export SEARXNG_SETTINGS_PATH=~/.local/share/searxng/settings.yml`; start via `.venv/bin/python -m searx.webapp`.
5. In-repo wrapper `scripts/searxng.sh` (start|stop|status|health): PID at `~/.local/share/searxng/searxng.pid`, curl `http://127.0.0.1:8888/health`. NEVER bind non-loopback.
6. Verify: `curl -s 'http://127.0.0.1:8888/search?q=plumber+canterbury&format=json' | head -c 200` → JSON results.
7. Live acceptance: `./mm doctor search` → reachable; ONE `./mm discover --engine searxng --dry-run` → DISCOVERED candidates with `searxng-local:<hash>` provenance.
8. GATE: `lsof -iTCP:8888 -sTCP:LISTEN` shows 127.0.0.1 only; 12/12 frozen tests green; AGPL/venv outside repo. Any sandbox block → record BLOCKED_SEARXNG_HOST, keep Layer A, move on.

### STEP 5 — Continuity without launchd [~30m]
1. Add `./mm supervisor ensure-running` (idempotent start-if-dead).
2. Propose (do NOT install without owner ask): `*/5 * * * * cd /Users/dd/WEBSITE-AUDITOR && ./mm supervisor ensure-running >> state/ensure-running.log 2>&1`
3. Prove kill -9 recovery: `kill -9 26743` → `./mm supervisor start` → new PID, queue depth unchanged, no dupes, second start refuses (PID lock).
4. GATE: recovery recorded in `reports/fable/p3_recovery_<date>.md`.

### STEP 6 — Evidence backfill (25 prospects with zero evidence) [~1.5h]
1. Batch `./mm audit <id>` for the 25 evidence-less prospects — even `unreachable` counts as recorded evidence.
2. Own-site contact crawl: stdlib `urllib` + `html.parser`, homepage + /contact + /about only → mailto:/emails/phones into `mm_contact_evidence` with URL+timestamp provenance. Guessed patterns NEVER = verified (P8).
3. GATE: ≥85% coverage with ≥1 evidence row; `human_review: REQUIRED` unchanged; zero live sends.

### STEP 7 — `./mm report daily` (standing impressive artifact) [~45m]
1. Stdlib-only generator → `reports/YYYY-MM-DD.md`: funnel deltas, new audits/evidence, DLQ dispositions, guard flaps, top-3 next actions, safety attestation line (`external_sends: 0 · model_calls: 0 · model_cost_usd: 0.0`).
2. Add per-stage funnel counts to `./mm metrics`.
3. GATE: first edition generated, attached to closeout summary.

### STEP 8 — Per-lane polish sweep (1 focused commit each) [~2h]
audit→packet chain on fixture (CONCEPT_ONLY, HUMAN_APPROVAL_REQUIRED) · fixed-NZD pricing re-test · `transport-status` none/0 · `model-routes` local-first/DEFER ledger 0 · `observability-snapshot` no db mutation · `outcomes` read-only · `obsidian-sync` vs WEBSITE-AUDITOR-BRAIN vault.

### STEP 9 — 24h soak + closeout
1. Supervisor running ≥24h (cron recovery if Step 5 approved).
2. Acceptance: no dupes, DLQ 0-or-triaged, $0.00 models, 0 sends, full suite green (58 baseline + all new).
3. Update CURRENT_STATE.md + CLAUDE.md; commit to `upgrade/v32-canonical-execution` only; PR #36 stays draft. Final report = per-workpath before→after + soak numbers + BLOCKED/DEFERRED list.

**v3 estimated total: ~9h Fable execution, $0.00, zero new software installs** (Layer B uses existing `uv` + `python3.11`; everything else is stdlib).
