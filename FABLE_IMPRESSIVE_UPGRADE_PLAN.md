# FABLE EXECUTION PLAN v3 - Impressive Upgrade, Better in Every Workpath, $0, Zero New Software

**Repo:** `/Users/dd/WEBSITE-AUDITOR` - **Branch:** `upgrade/v32-canonical-execution` (NEVER master; PR 36 stays draft)
**Executor:** FABLE - **Date:** 2026-09-22 - **Owner:** Dion
**Supersedes:** FABLE_EXECUTION_PLAN.md v2 for run-order (docs/*SEARXNG*PLAN.md stay as tech reference).

## 0. Iron constraints (violation = stop and report)

1. **$0 spend:** paid_allowed=false, max_cost_usd=0. Never set MM_ALLOW_EXTERNAL_FREE_MODELS=1.
2. **Zero new software:** NO pip/npm/brew/playwright-install/docker-pull/clone. Only: system python3 + .venv-email (3.11, NOT global 3.14), existing node/npx, existing Chromium/Playwright IFF present, Docker observe-only.
3. **No new deps:** never add to requirements/pyproject/package.json. New code = stdlib only.
4. **Fail-closed:** external_send_allowed=false, daily_cap=0, provider none. Never touch send/approve/email paths except guards/tests. Never send/publish/price-to-customer/auto-promote.
5. **Frozen:** test_discovery.py (12 tests) + searxng_candidates() signature + mm_pipeline transitions = DO NOT EDIT. Wrap only.
6. **Loopback-only:** probes touch 127.0.0.1 only. Non-loopback = REJECTED_ENDPOINT before socket.
7. **Hygiene:** git status before every commit. Never add state/*, *.db, .env, reports/ outputs, caches, secrets. One commit per workpath with test evidence.
8. **Gates:** each phase ends at a GATE. Paste raw output. BLOCKED/DEFERRED/SKIPPED with reason = PASS. Fake green = FAIL.

**Verified baseline 2026-09-22:** supervisor RUNNING PID 26743 - health OK, external_sends 0, models_enabled false, model_calls 0 - metrics 48 retry / 12 dead_lettered - 12 DLQ RETRYABLE_FAILURE 5/5 attempts - discovery 12 passed - transport DRAFT_ONLY/none - doctor research-only green, db ok.

## 1. Done-per-lane (before -> after, all free/zero-install)

- W1 P3 control-plane: running-unproven -> restart + double-start-refusal + kill-recover proven, no dupes, heartbeat fresh. Proof: supervisor restart/status + queue diff.
- W2 P6/P7 DLQ+dedupe: 12 opaque DLQ, ids 35-40 dupes of 29-34 -> every item has why+next-action; re-import adds 0 + regression test; malformed-URL tolerance test. Proof: dead-letter + test_dedupe_reimport.py.
- W3 P6 search: no-service = raw URLError traceback -> typed BLOCKED_SEARCH_* + searxng verify exit 2 + discover-search --dry-run ranked list, works service-ABSENT. Proof: verify + dry-run.
- W4 P4 audit: assumed pass -> deterministic green on fixture + recorded browser/external matrix (SKIPPED=pass per never-download policy). Proof: wa audit + matrix md.
- W5 P5 verify/score: scores exist -> evidence-to-deduction trace (finding->delta). Proof: p5_trace.md.
- W6 P10-P13 chain: works un-redemonstrated -> CONCEPT_ONLY + live_site_changed=false + HUMAN_APPROVAL_REQUIRED + fixed-NZD determinism re-proven. Proof: jq asserts + diff.
- W7 P14 outreach: disabled-assumed -> provably impossible (fail-closed negative test, cap 0). Proof: transport-status + pytest.
- W8 P15 models: ledger assumed 0 -> ledger 0.00 + DEFER + env-unset recorded. Proof: model-routes + metrics.
- W9 P17 observability: JSON exists -> snapshot w/o DB mutation (sha256 pre/post) + human OPERATOR_SNAPSHOT.md from existing JSON (stdlib only). Proof: checksums + file.
- W10 P18/outcomes: challenger exists -> outcomes read-only, recommend-only never-promote demo. Proof: outcomes output.
- W11 Obsidian: sync exists -> obsidian-status + read-mostly sync vs real vault WEBSITE-AUDITOR-BRAIN, non-authoritative. Proof: obsidian-status.
- W12 docs: scattered -> CURRENT_STATE table + reports/fable bundle + draft-PR update, zero runtime committed. Proof: git status clean.

## Run order (binding)
Wave A (no service/host change, biggest wins): Phase 0 -> Phase 1 (W2) -> Phase 2 (W1+W9) -> Phase 3 (W3 Layer-A absent-value).
Wave B (deterministic chain): Phase 4 (W4) -> Phase 5 (W5/W6/W7/W8/W10/W11).
Wave C: Phase 6 (24h soak + closeout). Never start Wave B before Wave A gates pasted.

## PHASE 0 - Lock baseline (30min, no code) -> GATE G0
```
cd /Users/dd/WEBSITE-AUDITOR
git status --short; git branch --show-current; git log --oneline -3
./mm supervisor status; ./mm health; ./mm metrics; ./mm errors; ./mm queue
./mm dead-letter > /tmp/fable_dlq.json; wc -l /tmp/fable_dlq.json
./mm transport-status; ./mm model-routes | head -n 30; ./mm doctor --profile research-only | head -n 60
./.venv-email/bin/python -m pytest money-machine/test_discovery.py -q
mkdir -p reports/fable
```
Save raw outputs to reports/fable/p0_baseline_<date>.md (NEVER git-add reports/).
GATE G0: running:true, sends 0, cost 0.0, discovery 12 passed, tree = only untracked runtime. Dead supervisor -> start + log. Cost/send mismatch -> halt BASELINE_MISMATCH.

## PHASE 1 - DLQ triage + dedupe (most impressive win, ~2h, stdlib) -> GATE G1
1. Classify: python3 read /tmp/fable_dlq.json (id/state/last_error). Ground-truth rows:
   sqlite3 database/money_machine.db "SELECT id,name,public_website,region,current_status FROM businesses WHERE id IN (29,31,32,34,38,39,40);"
   grep -rn "Public HTTP(S) website URL required" money-machine/*.py  (expect mm_core.py:42)
   Expect: 34/40 = not-a-url; 35-40 byte-dupes of 29-34, all discovered.
2. Win A - disposition enrichment, NO validator weakening: pure-stdlib helper by dead-letter view mapping why (missing-URL|malformed-URL|unactionable) + next_action (needs_url_repair|suppress_with_reason|operator_review). Never delete rows. New intake STILL raises ValueError; tolerance is display-only for historic rows.
3. Win B - dedupe regression: at ingest, key (canonical_host(public_website), lower(name), region); skip+count deduped_skipped. New money-machine/test_dedupe_reimport.py: import fixture twice -> 2nd adds 0.
4. Tests: new tests + discovery 12/12 unedited + toolkit quick pass.
5. Evidence: reports/fable/p1_dlq_<date>.md per-item table + dedupe counts.
GATE G1: 12/12 explained, 0 deleted; re-import 0 + test green; discovery 12/12; $0/0-sends.

## PHASE 2 - Control-plane + human snapshot (no host privs) -> GATE G2
1. Restart: supervisor restart; sleep 3; status; queue. Diff business_id list before/after (identical, no dupes). Heartbeat fresh.
2. Single-instance: start twice -> 2nd refuses (PID lock). Kill-recover: kill <pid>; start; status same depth.
3. Growth: du -sh state/; grep max_bytes|retention|rotate supervisor/logrotate.py.
4. FREE WIN - human snapshot (stdlib): new ./mm snapshot-report reading health.json+metrics.jsonl+errors.jsonl+dead-letter/ -> reports/fable/OPERATOR_SNAPSHOT_<date>.md (uptime/depth/DLQ-top-reasons/$0/0-sends/disk). Prove no DB mutation: sha256sum database/money_machine.db pre/post equal.
5. launchd: ONLY read-only status from money-machine/; NEVER install to ~/Library/LaunchAgents unasked. Else BLOCKED (direct supervisor = equivalent).
6. Evidence: reports/fable/p2_recovery_<date>.md + CURRENT_STATE P3 row.
GATE G2: restart+refusal+kill proven with diffs; snapshot checksum-equal; launchd shown-or-BLOCKED.

## PHASE 3 - SearXNG Layer A, useful service-ABSENT (zero installs) -> GATE G3
Ref: docs/SEARXNG_SERVICE_PLAN.md P0+P1 only. Layer B real service = DEFERRED_OPTIONAL (no clone/install unless owner approves).
1. P0 typed states: new stdlib money-machine/mm_search_backend.py probe() -> OK|BLOCKED_ABSENT|BLOCKED_TIMEOUT|BLOCKED_NOT_JSON|REJECTED_ENDPOINT (non-loopback/creds = PermanentError pre-socket). discover-search preflights first: absent -> named state + remedy, NEVER traceback. Add ./mm searxng verify (exit 2 absent) + discover-search --dry-run (stable hit_count-ranked DRY_RUN stub, no network).
2. P1 cache/replay/breaker/metrics/doctor: state/ file-cache by query-hash TTL 30s; replay when absent; reuse breaker row searxng-local; search.* counters in metrics; typed search block in doctor.
3. Tests offline (no sockets): test_search_backend.py (absent/timeout/non-JSON/non-loopback/redirect-off-loopback/2MiB-cap/dry-run-stable/replay). Frozen 12 untouched.
4. Evidence: curl 127.0.0.1:8888 expect 000/exit-7 side-by-side with typed output.
GATE G3: nothing on 8888 yet verify=exit-2 typed; dry-run ranked; new tests green; frozen 12 green; no dep diff; $0/0-sends.

## PHASE 4 - Audit matrix (never download) -> GATE G4
which chromium; ls ~/.cache/ms-playwright; which lighthouse lychee node npx
wa audit https://example.co.nz --profile nz  (deterministic MUST pass always)
IFF chromium+playwright present: WA_BROWSER_E2E=1 .venv-email/bin/python -m pytest toolkit_tests/test_browser_e2e.py toolkit_tests/test_monthly_browser_e2e.py -q
IFF lighthouse+lychee present: wa audit https://example.co.nz --profile nz --external-tools
ELSE SKIPPED (policy) = pass. Evidence: reports/fable/p4_matrix_<date>.md 3-line matrix.
GATE G4: deterministic green + matrix recorded. Zero installs.

## PHASE 5 - Every remaining lane, one focused win each (1 commit + 1 test) -> GATE G5
Order; each = small commit. Needs-install/schema -> DEFERRED_WITH_REASON, move on.
1. P5 trace: on Phase-4 fixture emit reports/fable/p5_trace.md: deduction -> finding_id+evidence_ref+delta (add tiny read-only stdlib join if missing).
2. P10-P13 chain: wa remediate -> demo --render -> quote --hourly-rate-nzd 150 -> packet on fixture; assert concept_only+!live_site_changed, HUMAN_APPROVAL_REQUIRED, quote determinism (run twice, diff).
3. P12 guard: re-run pricing test (LLM cannot price, fixed NZD). 4. P14: transport-status none/cap-0 + negative fail-closed test (draft->send raises). Attempt NOTHING live.
5. P15: model-routes DEFER + env grep MM_ALLOW_EXTERNAL_FREE_MODELS=0 + metrics cost 0.0.
6. P17: observability-snapshot with sha256 pre/post equal; health/metrics/errors/DLQ/heartbeats updated.
7. P18: outcomes read-only demo; challenger recommends-only never-promotes.
8. Obsidian: obsidian-status + sync vs WEBSITE-AUDITOR-BRAIN read-mostly (supervisor PID unchanged after).
GATE G5: reports/fable/p5_lanes_<date>.md per-lane proof or DEFERRED_WITH_REASON; $0/0-sends re-verified.

## PHASE 6 - 24h soak + closeout -> GATE G6 (done)
1. Supervisor >=24h. Before/after: health/metrics/errors/dead-letter/snapshot + OPERATOR_SNAPSHOT regen.
2. Accept: no dupes (business_id sets equal modulo retries), DLQ explained-not-shrunk, cost 0.00, sends 0.
3. Update CURRENT_STATE.md table + CLAUDE.md baseline (commands+results). Focused commits on branch only; push; PR36 draft.
4. Final reports/fable/FINAL_<date>.md: before->after table + soak + deferred + invariant re-check (health/metrics/transport-status).
GATE G6: soak pasted, CURRENT_STATE updated, branch pushed, PR draft, $0/0-sends.

## FABLE protocol
Order G0->G6 binding; never stack unverified paths; one commit per path (fable(W<n>): win -- tests: file:result -- $0/0-sends).
Evidence>adjectives: every claim = command + raw output in reports/fable/.
Halt: frozen-12 fail; pipeline-transition edit needed; install-only path; non-loopback bind; cost/send>0; secret/DB/state about to commit.
Never: edit test_discovery.py; add deps; vendor SearXNG; root/sudo; bind beyond 127.0.0.1; ingest non-OK; store queries/contacts; install launchd unasked; merge master; undraft PR.

*Operator one-liner: Wave A explains DLQ, kills dupes, proves restarts, humanises status; Layer A makes search typed+useful with zero installs; Wave B re-proves every lane deterministic+fail-closed; Wave C soaks 24h - all free, no new software, nothing sent.*

## APPENDIX V3-AD - Adopted deltas from FABLE_EXECUTION_PLAN_V3_ADDENDUM.md (2026-09-22 inspection, PID 26743 live)
These CORRECT and EXTEND the phases above; FABLE executes them as binding:
A. DLQ = 100% test_import fixtures (Acme/Beta/not-a-url), NOT real prospects -> correct disposition is QUARANTINE (is_dummy=1 + suppress test_fixture, idempotent/tx, DB backup first), not repair. Run BEFORE Phase 1 triage; then disposition classifier runs on remainder (expect near-zero). Tests: excludes-from-queue+metrics, idempotent, never-deletes.
B. Intake normalizer (extends Phase 1): normalize_intake_url() pre-validation (trim, prepend https:// if bare like acme.example.com, lowercase host, strip fragment/userinfo); reject RFC2606 reserved (.example/.invalid/.test, example.com/net/org) at intake -> suppressed, never retried; validator itself stays strict; never accept private IPs. Tests: bare-domain, reserved-TLD, no-private-IP.
C. Sandbox-proof suite (new): conftest capability probes HAS_SOCKET/HAS_DNS/HAS_PLAYWRIGHT (stdlib) -> pytest.skip not error; doctor reports the three; suite green in sandbox AND host with explicit skips; total >=70 (58 baseline+new).
D. Observability hardening (extends G2/G5): rotate state/errors.jsonl + metrics.jsonl (30d); state/alert-rules.yaml (DLQ-growth>0/hr, disk<2048MB, heartbeat>120s) surfaced as alerts[] in mm health + daily safety attestation. Tests: rotates/evaluates/surfaces.
E. Runbook: docs/RUNBOOK.md += quarantine procedure, DLQ decision tree, cron ensure-running removal, sandbox-vs-host table.
Order with addendum: G0 baseline -> A quarantine -> Phase1 disposition+dedupe -> B normalizer -> Phase2+D guards/alerts -> C suite -> G4 backfill + daily report (>=85% evidence, first report attached) -> E runbook -> Phase 6 soak.
Global accept each phase: health asserts sends==0+paid==0; pytest tests/ -q; ./mm doctor. Human-only (never FABLE): sends, models, pricing, approvals, launchd install, SearXNG host service, master merge.
