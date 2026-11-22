# Website Auditor release acceptance

Reconciled 19 November 2026 against [master snapshot](https://github.com/yabigdd-9/WEBSITE-AUDITOR/commit/9964a83eba42f4f3811c19cdbccaaf832dca2fcc). Historical records remain in [implementation progress](IMPLEMENTATION_PROGRESS.md). Use the [architecture](ARCHITECTURE.md), [operations runbook](OPERATIONS.md), [recovery procedure](RECOVERY.md), [security policy](SECURITY.md), and [cost limits](COST_LIMITS.md) alongside this release checklist.

## Dependency and completion matrix

| Phase | Existing implementation and evidence | Remaining gate |
| --- | --- | --- |
| 0. Reconcile | [#82–#88](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pulls?q=is%3Apr+is%3Amerged), [#105](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/105), [#106](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/106), [#110](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/110), and [#111](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/111) are merged. #89 was an issue. | Review the release branch heads and private repository configuration before merge. |
| 1. Build and CI | Linux CI, security, CodeQL and SonarCloud succeeded at f572af9. [#114](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/114) fixes macOS checkpoint test fixtures while preserving path validation. | Collect required checks on the exact release candidate and inspect private security alerts. |
| 2. Supabase | Both hosted read-only checks and the opt-in two-runner persistence test passed. See the run IDs below. | Keep the existing checkpoint as authority during recovery and rollback verification. |
| 3. Recovery | [Scheduled run 44097376009](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44097376009) restored a checkpoint, processed the queue, and uploaded its encrypted successor. | [#112](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/112) requires independent Postgres runner recovery, stale revision and invalid key rejection, crash and dedupe evidence, and rollback. |
| 4. Discovery and audits | Reviewed discovery import, transactionally bounded queue, evidence and scoring in #82–#84 and #88. [Canonical audit run 44407014752](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44407014752) succeeded. | Verify permitted discovery through persisted evidence and proposal generation on the candidate. |
| 5. Proposals and owner review | Exact-version approvals and authenticated persisted SQLite review in #84–#86. Hosted dashboard code is merged in [#113](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/113). | Verify hosted authentication and review on shared state before enabling the hosted portal. |
| 6. Outreach | #86 includes recipient and message approval, suppression and sandbox transport. | Before any live pilot, verify recipient consent, sender identification and a functional unsubscribe path against [New Zealand DIA guidance](https://www.dia.govt.nz/Spam-Three-Steps). [#109](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/109) tracks a separate owner-approved rollout. |
| 7. Customer acceptance and delivery | #87 records accepted scope, project tasks, evidence and delivery closure. | Verify the complete staged delivery flow with synthetic data and an authorised staging target. |
| 8. Cloud and monitoring | [Schedule monitor run 44380092462](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44380092462) passed. #111 added failure issues. | Capture the next schedule checkpoint in [#108](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/108) and prove notification on a controlled failure. Existing alert runs skipped on successful source runs. |
| 9. Security and cost | Worker policy and workflows define workload caps, authorization checks and fail-closed controls. | Verify private settings, alerts and real runner grants. Recheck budgets and recovery on the candidate. See [#54](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/54). |
| 10. Full acceptance | [Local internal E2E test](../toolkit_tests/test_platform_internal_e2e.py) exercises audit, approval, project closure and paired recovery. | Run the synthetic sequence across independent runners, including interruption, deduplication, queryable state and a controlled alert. |
| 11. Cutover | The encrypted GitHub Actions artifact remains authoritative. | Obtain owner approval for authority changes after #112 passes. Compare stores, retain the trusted checkpoint, run a limited smoke test, and record the candidate commit and rollback evidence. |
| 12. Handover | This matrix and the linked repository runbooks. | Record final runner IDs and check results once the release gates pass. |

## Branch disposition

- #107 and #113 are merged. #125 and #126 enabled the verified TLS setup and read-only-first workflow.
- [#90](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/90) is the draft encrypted report index. [#92](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/92) adds browser work on that branch. [#99](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/99) is a provisioning record stacked on #92 and overlaps the configuration history in #110 and #112.
- The older open drafts #42–#46, #51–#53 and #55–#58 cover v32/v44, Catalyx and dependency work. Several checks are stale or failing. Port independently required changes after checking master for equivalents. The cloud platform scope is tracked in [#78](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/78).

## Verification on this review

- #114 uses fully resolved temporary paths in encryption and restore fixtures. The macOS checkout passed 67 focused pipeline tests and 18 subtests, with two optional driver tests skipped in that run. Both skipped cases later passed in the dedicated 16-test Supabase suite after installing the driver.
- #115 fixes the field shared by approval and rejection. Both desktop and mobile Chromium review and acceptance tests passed on synthetic data. The master-based Chromium and PDF suite passed 24 tests separately.
- [#116](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/116) removes the acceptance and outreach suites' local database requirement. The portable MoneyMachine run passed 205 tests and 69 subtests, with two existing skips for external receipt and historical model reconciliation. [Linux CI](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44498874059), CodeQL, security and SonarCloud passed for the PR head.
- The macOS canonical run in the restricted sandbox passed 964 tests and 51 subtests. Eight local HTTP tests initially failed due to socket permissions. Their targeted loopback rerun passed, as did the four supervisor tests and the 24-test browser and PDF suite.
- [PR #114's SonarCloud run](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44497637967) returned HTTP 403 on the first attempt and passed on retry. Linux CI, toolkit, security and CodeQL passed for the same PR head. Private security alerts still need an owner-side check.
- Review activity used zero customer sends, paid operations, customer site changes, migrations or cutovers.

## Combined candidate verification

A local merge of master, #107, the #113/#115 hosted review stack and #114/#116/#117/#118 produced candidate `ee88ee3` without conflicts. On macOS, the broad toolkit run passed 995 tests and 57 subtests. Dedicated runs passed 80 PostgreSQL, hosted review, recovery, browser and monitoring tests, 34 loopback and Chromium tests, and 205 MoneyMachine tests. These counts overlap. The PostgreSQL tests used disposable local databases and exercised independent process recovery, crash-safe request budgets, duplicate writer exclusion, restricted permissions and encrypted backup. [#119](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/119) adds a verified regression for wrong-key rejection and idempotent replay through the encrypted checkpoint import CLI.

## GitHub-hosted evidence — 20 November 2026

- The restricted checkpoint mirror passed authenticated, TLS-verified, read-only preflight in [run 44603761401](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44603761401).
- The structured store passed its read-only runtime check in [run 44664177911](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44664177911). Both write jobs skipped with the default input.
- The explicitly opted-in [run 44664572515](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44664572515) passed the read-only check and both independent runner jobs. The second runner observed the first runner's committed pause event. Request reservation counts stayed constant on both runners.
- [Worker run 44664108097](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44664108097) uploaded a nonempty encrypted checkpoint. It was triggered by a push. The active workflow had no visible 20 November schedule-triggered run as of 7:42 p.m. NZDT, while its health monitor was still within the configured grace window.
- #107, #113, #125 and #126 are merged. Production authority stays with the encrypted GitHub artifact pending reviewed cutover, a rollback rehearsal against trusted state and controlled alert evidence.

## Disposable cross-runner recovery

[PR #132](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/132) ran the [synthetic rehearsal](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44690276157) on two GitHub runners. Preparation job `136134142923` exported the synthetic paused state with one interrupted reservation. Restore job `136134292749` downloaded the ciphertext, rejected an incorrect key, restored the pause event, refused a request for a different prospect at the original daily limit, and rejected import replay onto a populated database. The controlled alert test used a mock issue API and did not exercise live issue creation. The interrupted-audit replay guard is tracked in [PR #131](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/131).

## Release decision

Keep the current encrypted artifact recovery path. Before accepting the Postgres candidate, verify stale writers, audit replay, recovery against a trusted checkpoint, a reviewed rollback, and live controlled alert delivery. The disposable rehearsal covers wrong-key rejection and request-budget recovery. The authenticated preflights and two-runner persistence results are recorded above. Record rollback evidence before requesting a production cutover. Keep customer sending and paid operations disabled throughout this release verification.
