# 16 October 2026 — local Codex–Opus integration candidate

Location: `/Users/dd/WEBSITE-AUDITOR-codex`, branch `agents/codex-r00`.
Pinned Opus handoff: `dfc5dc397504dc80e6d9ffc5f09f3c0c9682ab75`.
Tested application revision: `b032c8c1d22d4000bb5db1d19fe5a4fa21f5d845`.

The corrected Opus chain and Codex evidence are combined locally. Focused
integration checks passed 73 cases. Full canonical coverage passed 1,131 cases
with three skips; MoneyMachine passed 693 cases with two skips and 83 passing
subtests. Both full receipts have unchanged tracked sources and zero observed
loaded-code mismatches. Canonical lint and dependency checks pass.

See `evidence/codex/integration-dfc5dc39/INTEGRATION.md` and its exact-revision
receipts for scope, changed files, isolated fixtures and remaining gates.
The imported search-DLQ A10 label does not complete the canonical runtime-
attestation A10. No shared integration branch update, remote push, deployment,
service restart, production DB/configuration change, soak or outreach occurred.
Earlier authorization statements below are historical, not activation approval
for this local candidate.

---

# 15 October 2026 — authorized controlled rollout candidate

The signed-in Sonar review resolved five findings with source-specific comments and independent API confirmation. The remaining nine were traced: five are explicit local operator input-file selectors with no lower-trust caller identified in the searched repository; their source-system findings remain open rather than assuming unknown deployment boundaries.

Three runtime boundaries are hardened: draft captures must stay inside the recorded owned review job, including absolute paths and symlinks; soak directories must stay inside repository state; FCC bridge HTTP endpoints must be loopback, with proxies and redirects disabled. The configured 127.0.0.1 endpoint is unchanged. No provider request, credential use or configuration activation was used to test these changes.

Final frozen verification: 1,124 canonical tests passed, three documented skips; 687 MoneyMachine tests plus 83 subtests passed, two independent acceptance skips. Both final receipts have exit_code=0 and changed_during_run=[] and compare loaded modules with fresh compilation. Scoped Ruff and pip check pass. Prior exploratory runs are not acceptance receipts.

The two tracked live daily reports are removed from Git tracking only. Their actual files and pre-change backups remain local, and prior Git history remains available. Existing ignore rules cover future output. No user backup or unrelated worktree was modified.

The user explicitly authorized a controlled existing-supervisor restart and rearming the existing controller for one fresh 24-hour window, then instructed execution of source review/fixes and rollout. The final candidate will bind the service startup and controller expectations to the new exact commit. No duration from previous attempts will be credited. Prior attempts, service identity, environment/provider configuration and no-send gates must remain intact. Release remains held for independent contact acceptance, historical ownership evidence, human PR review, unresolved Sonar findings and a completed exact-revision soak.


---
Previous records retained below as historical evidence.

# Remaining V44 gates — verified 15 October 2026

Latest tested application commit: `7a6a4d50b9acbf4e4eb844fce97452733a1a9587`, normally pushed on `integration/v44-local-machine-convergence`. Documentation-only descendants do not alter that Python source.

- Cookie-consent passive observation is implemented; complete rendered execution is possible with actual cookie/control evidence. It never clicks choices, retains cookie values, or asserts legal compliance.
- All ten fixture skips were repaired: correct existing corpus/rollback paths, independently scoped synthetic tests and disposable loop database. Final local suites: **1,110 canonical passes**, **683 MoneyMachine passes plus 83 subtests**, six Chromium journeys; only two independent acceptance skips remain in MoneyMachine.
- Exact module-execution startup proof and soak enforcement are implemented and tested but **not activated**. Help-only verification used exited PID `89903`; the actual supervisor remains PID `66896`. No service restart, controller rearm or new soak occurred.
- Latest configured Website Auditor gate at `2e642d0a` passed with 88.2% new-code coverage. Hosted results for later exact commits are separate. The secondary project gate and human review remain open.
- Current read-only independent readiness has 1/30 confirmed examples, 1/10 hard cases and eight unmet gates. The 16 historical owner/restriction inputs remain pending. No acceptance labels or receipts were manufactured.
- Two tracked daily reports changed during the work and remain preserved, unstaged. The backup remains locally preserved and is now ignored. A strict clean-worktree soak cannot begin until runtime-output publication is reconciled.

See `reports/v44-integration/2026-10-15/REMAINING_GATES.md`. **Full goal and release acceptance remain incomplete.** Original no-restart, no-live-DB-write, no-outreach, no-paid-call, no-provider-change and no-merge constraints remain enforced.

A10 (search DLQ tagging): `mm_pipeline.fail()` accepts `provider_state`/`lane` kwargs merged into existing `pipeline_items.payload` JSON (no DDL change, per A8). `test_dead_letter_distinguishes_provider_outage_from_prospect_failure` passes; evidence at `reports/search-service/a10-dlq-tag.txt`. Two categories separable by single query with no schema change. Committed locally as bfa4b31; no push.

## Earlier verification history

The earlier text below is retained as history. Its cookie/fixture status and counts are superseded by the record above.

---

# Current V44 integration verification — 15 October 2026

The authoritative checkout is `/Users/dd/WEBSITE-AUDITOR`, branch `integration/v44-local-machine-convergence`. Verified application SHA `2bd7a12274ea3403329f45d0cc270bffc1fb2033` was normally pushed to origin; PR #52 is open, draft and mergeable. The three requested starting commits are preserved. Documentation-only descendants do not change the tested application source.

- Audit repair `2cc0910b`: four required static analyzers and two rendered event analyzers now execute with version-3 evidence. Missing/failed observations retain partial coverage. Cookie-consent analysis is still explicitly unimplemented; rendered audit health remains unavailable while that requirement is missing.
- Hermes repair `2bd7a122`: synthetic acceptance tests, staging alias protections, nonzero failure/timeout/placeholder results, corrected cumulative reporting and unknown-accounting handling. Live-mutating runner jobs are blocked pending separately approved staging work. Human review and no-send gates remain intact.
- Frozen local validation: **1,096 canonical tests**, **662 MoneyMachine tests plus 77 subtests**, **30 Hermes tests** passed; **6 real Chromium journeys** and **29 tier-1 tests** passed. Canonical has 3 skips; MoneyMachine has 12 explicit fixture/acceptance skips. Counts overlap. Ruff, compile, pip check, wheel/import, staged whitespace and scoped secret checks passed.
- Whole-module comparisons against fresh compilation verified loaded code and source remained unchanged during frozen validation. Receipts, exact skip reasons and historical metric reconciliation are under `reports/v44-integration/2026-10-15/`.
- All 13 latest configured PR statuses passed on the application SHA. Website Auditor SonarCloud passed at **87.5% new-code coverage**. A separate `HERMES_MONEY_ENGINE` automatic analysis attached an earlier failed Security E/Reliability D check to the same commit; its 14 open bug/vulnerability annotations remain recorded for separate review and must not be hidden by the later same-name successful check.
- Read-only live DB observation: integrity `ok`, 0 FK violations, 0 model invocation rows/calls/cost and 0 recorded message/proposal sends. Supervisor PID `66896` had a fresh heartbeat. This does not prove that the new revision is loaded or soak-accepted.
- No live DB writes, outreach, paid calls, service restarts, provider/routing changes, merge, ready-for-review action or deployment command were performed. The untracked runner backup and separate dirty worktrees remain preserved.

**Release readiness: HELD.** Remaining gates include secondary Sonar triage, independent model/provider/contact/receipt acceptance, missing fixture coverage, historical privacy/secret review and an explicitly authorized exact-revision runtime/soak acceptance. Publication and tests do not authorize production, outreach or spending.

## Historical review snapshot retained below

Everything below is the earlier review snapshot, retained as history. Its checkout, publication, CI and validation statements are superseded by the verified V44 record above; earlier runtime evidence does not transfer to this revision.

---

# WEBSITE-AUDITOR — Current State

_Last updated: 2026-10-15 · branch `integration/v44-local-machine-convergence` · PR #52_

## Canonical direction

- **Audit engine:** `auditor_toolkit/` with thin `wa` CLI; `./mm` is the operator interface.
- **Runtime authority:** SQLite and state files; one launchd-owned Money Machine supervisor.
- **Human workspace:** Obsidian is a review view, never queue, pricing or sending authority.
- **Model policy:** deterministic work first; exact-certified zero-cost FCC route, otherwise Hermes live-verified `:free` route, otherwise DEFER. Local llama.cpp and Ollama are not active Money Machine routes.
- **Cost:** `paid_allowed=false`, `max_cost_usd=0`; no automatic paid fallback.
- **Privacy:** repository default `data_collection: deny`; only explicitly attested public/synthetic requests may opt into a data-collecting free endpoint. Secrets and confidential/customer content remain held.
- **Outreach:** `MM_EXTERNAL_SEND_DISABLED=1`; exact human approval and all contact, production and sender gates remain required.
- **Optional services:** loopback SearXNG; n8n and Docker are not core runtime requirements.

## Implementation and acceptance

| Area | State | Evidence or remaining acceptance |
| --- | --- | --- |
| Configured GitHub checks | PASS at baseline | All 13 latest check runs succeeded at b349; candidate remains unpublished with no new hosted checks or Sonar analysis. |
| Human/code review | OPEN | PR #52 is draft; CodeRabbit draft skip is not review. |
| Supervisor/control plane | IMPLEMENTED | Single-instance protections, heartbeats, leases, recovery, health/log commands, rotation and DLQ triage exist. Four defects fixed on agents/opus-r01 (commit 5f461d43): pid.py import ordering, daemon.py macOS process check, mm_dashboard.py SQL typo, mm_ritual_cycles.py missing import. CAUTION: commit 5f461d43 inverted daemon.py.start() os.kill(pid,0) logic — it must NOT be integrated without corrective commit f12a83c7f028f52fca6d4b5c5e9c5d0495aeb586, which restores live-PID→blocked, dead-PID→recover+True, PermissionError→fail-closed-False, malformed→recover+True, adds regression tests (toolkit_tests/test_daemon_start.py: 6 passed), and notes daemon.py.start() is non-atomic (atomic guard remains cli.py's PIDFile flock+O_EXCL). Toolkit: 297 passed/2 skipped. Intelligence: 178 passed. Acceptance: 57 passed/1 pre-existing failure/2 skipped. Push blocked by sandbox (github.com:443 denied). |
| Discovery and contact review | IMPLEMENTED | Bounded discovery and automatic first-party evidence collection; uncertain contacts remain held. Draft preparation does not release a contact or authorize sending. |
| Lighthouse/Lychee | ADAPTERS IMPLEMENTED | `auditor_toolkit/external_tools.py` and fixture tests exist; exact-head real-tool host acceptance is separate. |
| Audit coverage safety and maintenance | IMPLEMENTED LOCALLY | Seven no-op stages are marked skipped with explicit required/optional coverage; History rejects incompatible cached audits and incomplete required audit coverage routes to NEEDS_REVIEW. Analyzer implementations remain deferred; focused safety/quote/worker validation passed. |
| Contact precision/intelligence | HELD | Human labels, independent release evidence and prospect-disjoint holdout acceptance are not replaced by machine corrections or CI. |
| Earlier-revision soak | HISTORICAL PASS | e83121b, 86,405.524033 seconds, 1,420 samples, no violations. It grants no b349 or candidate acceptance. |
| Current-revision soak | BLOCKED | b349 attempt failed an uncached public-network sample; active attempt is null and no valid new deadline exists. |
| Production, publishing and sends | NOT AUTHORIZED | Separate human decisions, exact-item approval and relevant production checks remain necessary. |

## Local candidate validation

| Check | Recorded result |
| --- | --- |
| Canonical regression | 1,048 passed; 3 skipped; 3 warnings. Two opt-in Chromium skips are covered by six freshly passing browser journeys; one skip is unavailable PIL.Image. |
| Focused coverage, quote and worker checks | 82 passed. Required browser/header/TLS failures retain retry handling before an implementation hold. Malformed falsey effort bands and invalid JSON produce handled CLI validation errors; stale/contradictory coverage cannot verify or resolve findings; valid partial rendered captures retain screenshot comparisons. |
| Portable regression | 424 passed; 45 subtests passed. |
| Real Chromium regression | Fresh full suite: 6 passed in 47.98 seconds. Earlier browser receipts remain historical. |
| Local Sonar suggestion receipt | All 39 annotations reverified against 19 current source hashes; no new hosted Sonar result. |
| Tier-1 regression | 29 tests OK. |
| Supplemental image check | The formerly skipped image test passed once using work-only Python 3.12.14 and Pillow 12.3.0 with network denied. The canonical Python 3.11 skip and all prior suite counts remain unchanged; no host/source/environment change. |
| Ruff / compile / dependencies | Canonical toolkit, V45 and changed worker Ruff passed; compile and pip check passed. |
| Package build/import | Rebuilt final-candidate wheel and 17 installed imports passed, plus CLI help, local doctor and axe assets. Operator CLI help also passed. Local doctor reports missing llama_cpp/model; no generation was exercised. |
| Dependency audits | Project and email environments passed with no known vulnerabilities reported. |
| Historical secret scan / static assessment | Scan completed over 1,003 commits and 56.47 MB in 185.366 seconds, exit 1. All 87 inputs were individually assessed: 71 not_actionable, 16 needs_review, 0 confirmed; duplicate-looking inputs remain retained. T20 owner/restriction/purpose review stays open for 16. This is not historical-secret clearance. See review-bundle `follow-up/HISTORICAL_SECRET_TRIAGE.md` and `historical-secrets-triage.json`. |

Earlier 1,029-test canonical and 63-test focused receipts remain historical in the review bundle; the counts above supersede them for this final candidate. Portable, tier-1, dependency-audit and supplemental-image receipts are retained evidence.

The candidate is committed locally and unpublished. Its exact commit SHA is recorded in the external review bundle rather than embedded in its own source; no push, deployment or runtime change is authorized. Local regression and dependency receipts do not establish runtime acceptance, production readiness or a clean historical secret scan.

## Runtime evidence

Read the authoritative checkout's `state/soak-control/status.json`, `expected.json`, `operational-policy.json`, `events.jsonl` and referenced evidence directory. Do not run health commands simply to refresh this document: some operator commands write state.

The b349 attempt `state/soak-evidence-20261005T192940740852Z` ended incomplete on **6 October 2026 at 10:51:39 a.m. NZDT**. Sample 140 recorded uncached TCP timeouts to both `example.com:443` and `github.com:443`; the controller then stopped its owned collector. The finish sample recovered connectivity, but the persisted failure remains. Duration was **8,517.877019 seconds**, with **142 samples** and `soak_passed=false`. These observations do not establish the upstream cause of the network failure. Earlier deadlines are invalid, and there is no current `final-acceptance.json`.

The previous accepted run `state/soak-evidence-20261003T114403133502Z` froze **e83121b**, from **4 October 00:44 to 5 October 00:44 NZDT**. It proves local runtime acceptance at that revision only. Accounting measures local database records, not independent external provider receipts.

A prepared recovery proposal calls for fresh preflight, preservation of all eight attempts, rearming only the inactive controller and a new uninterrupted 86,400-second window. Its existing monitoring instructions prohibit controller restart/reconfiguration without exact new authorization. Do not restart the supervisor, duplicate a collector, weaken a gate or combine failed windows. Use the existing completion monitor after authorized recovery.

## Next decisions and release gates

1. Preserve the final passing validation receipts, inspect the complete tested candidate diff and obtain owner/restriction/purpose review for the 16 historical-secret inputs still held after static assessment. See T20 in the TODO register; any later confirmed credential requires exact remediation/rotation authority.
2. Keep the candidate separate from the clean live checkout until promotion and rollout are explicitly authorized. Recheck GitHub head/checks and preserve combined-branch alignment at that time.
3. Complete exact-head host evidence where required: browser rendering, optional installed Lighthouse/Lychee, optional SearXNG and an explicitly authorized bounded free-model smoke.
4. Obtain exact controller recovery authorization for the selected frozen revision, refresh preflight and require one wholly new accepted 24-hour window.
5. Complete human contact/intelligence release evidence and code review; `master` integration, deployment and sending remain separate decisions.

The project plan does not change [the approval queue](approval/APPROVAL_QUEUE.yaml), human labels, provider policy or real prospect state. Older reports and `state/HERMES_EXECUTION_STATE.yaml` references are historical; that state file is absent from the current checkout. This document is the current project status; SQLite/state evidence and the approval queue retain their own authority.

---

# 29 October 2026 — transport-test repair and frozen accuracy holdout

Committed `1f30ad14` on `integration/v44-local-machine-convergence` (PR #52 still draft).

**Transport test repaired.** `toolkit_tests/test_outcomes_transport.py` failed because
`mm_transport.status()` honours a private owner override at `state/transport-policy.json`
(currently: enabled Gmail, unlimited cap), so a bare call returned `MANUAL_EXACT_APPROVAL`
rather than the committed `DRAFT_ONLY` default. The test asserted a schema default against
live runtime state. Fixed by pinning the default path explicitly and adding coverage for the
override path, the `MM_EXTERNAL_SEND_DISABLED` kill switch, and the private-file refusals
(directory / symlink / world-readable). Toolkit suite: **330 passed, 2 skipped**
(both opt-in Chromium). Money Machine acceptance: **56 passed, 2 skipped**. The live
`state/transport-policy.json` is preserved unchanged; no approval, suppression or send
state was modified.

**Accuracy holdout frozen** at `outputs/holdout-accuracy-20261029/`. 30 cases, 10 per
required stratum, 339 predicted observation units, SHA-256-frozen fixtures, 30 raw auditor
reports preserved. Deterministic replay reproduces the live auditor's defect-key set on
30/30 cases. Scorer: 22/22 synthetic contract tests pass; blank template still correctly
fails. Selection provenance and known weaknesses recorded in `STATUS.md` and
`REVIEWER-GUIDE.md`.

**Blocked on a human:** an independent reviewer must label all 339 units before any
precision/recall figure can be produced. The 16 historical security holds still carry
`decision: null`. Release remains held. No send, paid call, merge, deployment, restart or
delete was performed.

---

# 29 October 2026 — exports, restore rehearsal, security disposition draft

Pushed to `integration/v44-local-machine-convergence` (PR #52 still draft, not merged).

**Exports** (`exports/`, committed):
- `v44-bundle-20261029.git` — 38 MB Git bundle, `git bundle verify` OK, complete history,
  single ref → `8599e893`. Kept out of the tree as a binary artifact.
- `holdout-accuracy-20261029-redacted/` — 30-case accuracy holdout with third-party page
  content redacted (Google Maps keys, a JWT, secret-like assignments in holdout-008/014/016/027).
  Fixture and prediction hashes recomputed against redacted bytes. Post-redaction secret scan: 0.
  Also bundles the scorer, the 16-hold security inventory, the restore-rehearsal receipt and the
  report. Scorer binding verified on redacted bytes.

**Restore rehearsal** (`state/restore-rehearsal-20261029T200000Z.json`): the preserved
pre-soak snapshot restores cleanly — integrity ok, 0 FK errors, 67 tables, byte-identical to
the stored copy. Live database proven unchanged before and after (sha256 `f28e06fe…5074`).
Live has advanced past the snapshot (395 vs 375 pipeline rows, last write 2026-10-28), so a
restore would roll those back deliberately — that is an owner decision, not authorized here.
Accounting clean on both: 0 model invocations, 0 paid, 0 outreach sends, 0 proposals,
1 preserved owner transport test claim.

**Security disposition draft** (`security/DISPOSITION-DRAFT-20261029.md`): all 16 holds
re-inspected at byte level. 11 are scanner false positives — the flagged value is a 39-char
base64 blob decoding to a Google Maps embed key appearing once per captured third-party email.
`triage-044` is the same provenance in plaintext. `triage-007` (docs example) and
`triage-085/086/087` (cached captures) come from commits that are not ancestors of the frozen
source and are absent from the current tree. **All 16 remain `decision: null`.** No key tested
against a provider, no rotation, no history rewrite, no value printed.

**Still open:** accuracy labels (needs an independent human reviewer), owner/email operational
acceptance, stale-heartbeat root cause, paid-route entitlement, explicit release acceptance.
PR stays a draft. No merge, send, paid call, restart or delete was performed.
