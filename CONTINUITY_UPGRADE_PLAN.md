# Continuity upgrade plan

_Updated 8 October 2026. Baseline b349cd9f; isolated candidate locally committed and unpublished._

This replaces the 20 September gap list with the current disposition. [CURRENT_STATE.md](CURRENT_STATE.md) records revision and acceptance; [docs/RUNBOOK.md](docs/RUNBOOK.md) documents operator procedures. The complete work order is [docs/GITHUB_TODO_REGISTER.md](docs/GITHUB_TODO_REGISTER.md).

## Suggestions already implemented

| Historical suggestion | Current disposition | Remaining acceptance |
| --- | --- | --- |
| P0.1 daemon/PID/signals and P0.2 daemon CLI | Implemented in the supervisor package and operator CLI. launchd owns the supported macOS service. | Exact-revision host ownership, restart/lease recovery and uninterrupted soak proof; do not install a second daemon. |
| P0.3 rotation/retention | Implemented in supervisor log rotation and operator/reporting paths. | Preserve event history and verify relevant changed behavior with fixtures; old speculative latency/retention targets are not measured results. |
| P0.4 status and P1.1 health | Health/status commands, passive evidence and alerts exist. | A current heartbeat is not proof of full acceptance. Some CLI inspections write state. |
| P1.2 structured logs and P1.3 metrics | Log-query and metrics modules exist. | Optional export/host verification only where required; heavier observability remains deferred. |
| Configuration validation/watch and worker reload | Existing modules provide these capabilities. | Frozen soak configuration must not change. Any rollout is controlled and explicitly authorized. |
| Dead-letter visibility and operator runbook | DLQ CLI and `docs/RUNBOOK.md` exist. | Do not resolve real failures or quarantine/delete data as part of documentation cleanup. |
| Lighthouse/Lychee integration | Adapters and synthetic tests exist in the canonical toolkit. | Real installed-tool execution on the accepted head remains host acceptance, not an unimplemented adapter. |

The old llama.cpp retry/cache proposals are superseded by the current deterministic/FCC-certified/Hermes-verified/DEFER policy. They do not authorize installing models or enabling providers. Secret rotation or a vault migration is a separately approved operational action; the local update only makes unsupported secret listing fail visibly without reading credentials.

## Remaining implementation work

The 8 October isolated candidate marks the seven no-op audit stages skipped instead of claiming success, rejects cached audits without current required coverage, routes missing audit implementation to NEEDS_REVIEW, and addresses the misleading secret-list command, quote input/effort consistency and Sonar maintenance suggestions. The analyzer bodies remain unimplemented. Five precommit fixes address malformed falsey effort bands, invalid JSON CLI errors, valid partial-rendered screenshot baselines, stale verification/resolution guards and contradictory rendered/browser coverage metadata. It is implemented, tested and committed locally on the isolated branch. The external review bundle records its commit SHA; it remains unpublished. Passing checks include 82 focused tests, 424 portable tests with 45 subtests, six freshly passing Chromium journeys, 29 retained tier-1 tests, scoped Ruff, compile/pip check, wheel build and both dependency audits. Final canonical regression passed 1,048 tests with three skips and three warnings; the rebuilt wheel passed 17 installed imports plus CLI help/local doctor and axe assets. Model generation remains untested because the local llama_cpp/model is absent. The fresh full Chromium suite passed in 47.98 seconds; all 39 Sonar suggestions were locally reverified against 19 current source hashes, with no new hosted analysis. Earlier 1,029/63-test receipts remain historical; final receipts and the exact local commit SHA are retained by the external review bundle. Do not borrow baseline CI or an earlier soak as candidate evidence.

Agreed candidate CI validation includes package build/import verification; the current wheel build and 17 installed-import checks passed, along with CLI help/local doctor and axe assets. Full-history gitleaks completed over 1,003 commits and 56.47 MB in 185.366 seconds, exiting 1. All 87 inputs were statically assessed individually, retaining duplicate-looking inputs: 71 not_actionable, 16 needs_review, 0 confirmed. T20 remains open for owner/restriction/purpose review of 14 captured Maps-key observations, one historical Stripe test-key-shaped example and one WPForms form token. Review-bundle `follow-up/HISTORICAL_SECRET_TRIAGE.md` and `historical-secrets-triage.json` preserve the assessment. This is not clearance; no credential values/provider calls/rotation/history rewrite/allow-list expansion is included. Deferred work has separate acceptance: actual implementation of the seven skipped analyzer stages, independent human labels and disjoint intelligence holdout, optional provider/browser/SearXNG host checks, and reviewed integration with `master`. No broader infrastructure, config hot reload, credential mutation or live queue work follows automatically from this plan.

## Current runtime recovery

The b349 soak ended incomplete on 6 October at 10:51:39 a.m. NZDT after both public TCP probes timed out in sample 140. Its 142 samples and 8,517.877019 seconds receive zero completion credit. Controller status is blocked with no active attempt or valid deadline. The accepted 24-hour e83121b run is historical proof at another revision.

The existing prepared Action A recovery preserves all attempts and control records, uses the inactive controller's current lock, retains source/configuration and the same supervisor, and starts one fresh controller-owned window after successful preflight. Controller rearm/start requires exact new authorization under the existing monitoring instructions. Preserve the original 86,400-second duration, maximum 420-second sample gap, fresh heartbeat, one owner, database/lease/DLQ/disk/network and zero-recorded-cost/send gates. Never reset an active collector or aggregate interrupted windows.

## Verification and rollout

1. Preserve the passing local regression/build/dependency evidence, retain the final canonical-suite/import smoke receipts, inspect source/doc changes and obtain owner/restriction/purpose review of the 16 historical-secret inputs still held after completed static assessment.
2. Record exact candidate revision and meaningful validation before any approved promotion; retain source/configuration/database backups for actual rollout work.
3. Recheck same-head GitHub checks, human review and required host evidence.
4. Execute only an authorized recovery/rollout; verify one owner and let the controller own its collector lifecycle.
5. Accept only a complete independently recalculated raw stream plus final acceptance at the frozen final revision. Production, outreach and payment authorization remain separate.

No deployment, service control, secret use, approval mutation or live-data testing is part of this documentation update.
