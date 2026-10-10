# Website Auditor agent execution plan

_Updated 8 October 2026. Canonical baseline b349cd9f / draft PR #52. Isolated candidate locally committed and unpublished._

## Sources of truth

Read [CURRENT_STATE.md](../CURRENT_STATE.md) for current project status, [MASTER_PLAN.yaml](../MASTER_PLAN.yaml) for canonical requirements, [the TODO register](../docs/GITHUB_TODO_REGISTER.md) for ordered work and acceptance, and [approval/APPROVAL_QUEUE.yaml](../approval/APPROVAL_QUEUE.yaml) for human approval records. The older `state/HERMES_EXECUTION_STATE.yaml` link is unavailable in this checkout and must not be used to assert current tasks, retries or sending capability.

SQLite and actual state evidence remain the runtime authority. The plan is not an approval record. APR-004 and APR-006 remain awaiting human action; APR-007 is partially complete in the inspected queue. These records are unchanged by this update, and older descriptions of active engines or mail transport do not establish current sending permission.

## Current objective

Produce a reviewable isolated update from GitHub/static suggestions while preserving the live combined V44/V45 runtime, $0 policy and human gates. Baseline PR #52 has 13 successful latest checks; CodeRabbit skipped draft review. The 39 Sonar maintenance suggestions and immediate safety TODOs are implemented locally with passing regression evidence; the local commit is recorded in the external review bundle, with no push or new hosted Sonar analysis.

## Recorded local evidence

Focused coverage/quote/worker tests: 82 passed. Portable suite: 424 passed and 45 subtests passed. Fresh full Chromium suite: six passed in 47.98 seconds. All 39 Sonar annotations were locally reverified against 19 current source hashes; no new hosted result exists. Tier-1: 29 tests OK. Scoped Ruff, compilation, pip check, wheel build and project/email dependency audits passed; audits reported no known vulnerabilities. Final canonical regression: 1,048 passed, three skips and three warnings. Two opt-in Chromium skips are covered by the six freshly passing journeys; the other is unavailable PIL.Image. The rebuilt wheel passed 17 installed imports, CLI help/local doctor and axe assets; operator CLI help passed. Doctor reports missing llama_cpp/model and no model generation was tested. A supplemental formerly skipped image test passed once with work-only Python 3.12.14/Pillow 12.3.0 and network denied; canonical Python 3.11 skips/counts remain unchanged and no host/source/environment was changed. Earlier 1,029-test canonical and 63-test focused receipts remain historical; portable/tier-1/dependency/image evidence is retained. The external review bundle records the exact local commit SHA and final receipts.

T20 static assessment is complete: all 87 inputs from the exit-1 full-history scan were assessed individually, retaining duplicate-looking inputs. There are 71 not_actionable, 16 needs_review and 0 confirmed. Owner/restriction/purpose review remains open for 14 captured Maps-key observations, one historical Stripe test-key-shaped example and one WPForms form token. Read review-bundle `follow-up/HISTORICAL_SECRET_TRIAGE.md` and `historical-secrets-triage.json`. No credential value, provider call, rotation, history rewrite or allow-list expansion is included. This is not clearance; any later confirmed credential requires exact remediation/rotation authorization.

## Confirmed precommit fixes

Malformed falsey effort bands are rejected rather than silently defaulted; invalid JSON reaches handled CLI validation. Valid partial browser captures can supply integrity-checked screenshot baselines without claiming full audit acceptance. Stale verification/resolution records and contradictory rendered/browser metadata cannot bypass current coverage. These five fixes are included in the final local candidate and its focused validation.

## Work order and roles

| Owner | Work | Completion evidence |
| --- | --- | --- |
| Orchestrator | Reconcile baseline, current GitHub suggestions and runtime holds; assign one writer per file. | Exact baseline SHA, sources, full candidate diff and final report. |
| Audit maintainer | Mark seven unimplemented modules skipped. Static language/hreflang/images/social stages are required; browser-only stages are required only in requested rendered mode. Preserve reports and artifacts. | Required skips yield partial status and unknown health; optional skips stay visible without falsely claiming measurement. No analyzer implementation is included. |
| Pipeline maintainer | Add current coverage/version guards to audit History reuse and route unimplemented required audit coverage to `NEEDS_REVIEW`. | Legacy/incompatible/incomplete cached audits are rejected; audit-handler holds remain explicit instead of claiming completion. Contact-review cache and live prospects are unchanged. |
| Safety/CLI maintainer | Make unsupported secret listing fail clearly without invoking Keychain or printing values; validate deterministic quote inputs. | Mocked CLI proves no credential lookup; quote tests reject non-finite/out-of-range rates and use shared effort bands. |
| Maintenance reviewer | Resolve 33 compound assertions, four exception-assertion scope suggestions and two technology suggestions. | Preserve every original assertion; precompute helper arguments so `pytest.raises` contains one intended throwing invocation. Use `DetectedTechnology` with the `Technology` alias and retain documented `url`/constructor/wire compatibility. New Sonar analysis is separate from source edits. |
| Documentation maintainer | Update canonical status, continuity dispositions and this plan; remove unavailable state links. | Sources and implementation/host/approval states agree; no approval record is changed. |
| Integrator/reviewer | Inspect full diff and validate the final isolated candidate, including agreed CI and package build/import verification. | Actual test/lint/schema/build/import results and explicit skips in the final bundle; no baseline CI is counted as candidate CI. |

## After local candidate validation

Keep candidate code local and separate from the authoritative checkout until the requested promotion is authorized. Publishing a branch/PR, enabling review, synchronizing combined branches, merging into `master` and runtime rollout are distinct actions. Actual analyzer implementation is deferred separately; package build/import verification belongs to agreed candidate validation. Independent contact/intelligence acceptance remains held for its own evidence.

The b349 soak is terminal blocked after one public-network sample timed out; its 2-hour-21-minute incomplete attempt contributes no 24-hour acceptance. The accepted e83121b soak belongs to its earlier revision. A prepared controller recovery requires exact new authorization. Reuse the existing completion monitor, preserve all eight attempts and start a wholly new frozen window only after approved preflight. No supervisor restart is implied by the observed connectivity failure.

## Human and commercial gates

Research, permitted evidence collection and local DRAFT_ONLY preparation can continue within existing policy. Machine corrections do not create human precision labels or independently verified contacts. Prices require an explicit valid operator rate; missing rates remain unpriced. Approval must bind the finished recipient/message/attachments/evidence/price and all production/sender/contact checks. Never infer consent or sending permission from public publication, a generated packet, a partially completed approval record or passing tests.

No outreach, provider/model calls, paid route, deployment, credential mutation or live database/queue change is part of this isolated update.
