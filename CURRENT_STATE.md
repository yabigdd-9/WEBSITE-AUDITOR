# WEBSITE-AUDITOR — Current State

_Last updated: 2026-10-08 (Pacific/Auckland). Verified baseline: `b349cd9fb23b6cf9c5a2e8a8c74691158e9cda8f`, PR #52._

## Verified baseline and local candidate

The authoritative service checkout is `/Users/dd/WEBSITE-AUDITOR`, on `integration/v44-local-machine-convergence`. The combined V44/V45 kit has a separate V45 branch; it has not been merged into `master`.

On 8 October, [PR #52](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/52) remains open and draft at **b349cd9f**. Its latest **13 check runs succeeded**. The [SonarCloud result](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/52#issuecomment-6001612868) has **39 maintenance suggestions**: 33 compound assertions, four exception-assertion scopes and two technology-detection suggestions. There are no unresolved inline review threads or open repository issues in this inspection. CodeRabbit skipped review because the PR is draft; that is not completed review.

The 8 October update is a **locally committed candidate in the isolated `codex/github-todo-update` checkout**. It marks seven unimplemented audit stages explicitly skipped and addresses audit-cache coverage guards, audit-handler review holds, secret-list behavior, quote safety, the 39 maintenance suggestions and planning drift. Precommit review also fixed five issues: malformed falsey effort bands, invalid JSON CLI handling, screenshot comparisons for valid partial browser captures, stale verification/resolution acceptance and contradictory rendered/browser coverage metadata. The external review bundle records the local commit SHA. Local validation passed as recorded below, including the final canonical-suite rerun and installed-wheel import smoke; the final report retains the receipts. Existing b349 checks do not validate this new diff, and the authoritative checkout, running service, database, configuration and approvals remain unchanged. See [the suggested TODO register](docs/GITHUB_TODO_REGISTER.md).

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
| Supervisor/control plane | IMPLEMENTED | Single-instance protections, heartbeats, leases, recovery, health/log commands, rotation and DLQ triage exist. Current-revision full acceptance remains outstanding. |
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
