# Website Auditor release acceptance

Reconciled 19 November 2026 against [master snapshot](https://github.com/yabigdd-9/WEBSITE-AUDITOR/commit/9964a83eba42f4f3811c19cdbccaaf832dca2fcc). Historical records remain in [implementation progress](IMPLEMENTATION_PROGRESS.md). Use the [architecture](ARCHITECTURE.md), [operations runbook](OPERATIONS.md), [recovery procedure](RECOVERY.md), [security policy](SECURITY.md), and [cost limits](COST_LIMITS.md) alongside this release checklist.

## Dependency and completion matrix

| Phase | Existing implementation and evidence | Remaining gate |
| --- | --- | --- |
| 0. Reconcile | [#82–#88](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pulls?q=is%3Apr+is%3Amerged), [#105](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/105), [#106](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/106), [#110](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/110), and [#111](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/111) are merged. #89 was an issue. | Review the release branch heads and private repository configuration before merge. |
| 1. Build and CI | Linux CI, security, CodeQL and SonarCloud succeeded at f572af9. [#114](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/114) fixes macOS checkpoint test fixtures while preserving path validation. | Collect required checks on the exact release candidate and inspect private security alerts. |
| 2. Supabase | [Checkpoint schema and grants](SUPABASE_CHECKPOINT_STORE.md), the merged read-only preflight, and [#107](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/107). #107 targets master and had passing Postgres CI at the reviewed head. | [Read-only preflight 44084270932](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44084270932) failed at the live verification step on both attempts. A separate read-only catalog check confirmed the dedicated role can log in, is a checkpoint-writer member, and has no superuser or RLS bypass privileges. Both checkpoint tables have RLS enabled. Privately verify login and secret configuration, then repeat the read-only check before isolated writes. |
| 3. Recovery | [Scheduled run 44097376009](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44097376009) restored a checkpoint, processed the queue, and uploaded its encrypted successor. | [#112](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/112) requires independent Postgres runner recovery, stale revision and invalid key rejection, crash and dedupe evidence, and rollback. |
| 4. Discovery and audits | Reviewed discovery import, transactionally bounded queue, evidence and scoring in #82–#84 and #88. [Canonical audit run 44407014752](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44407014752) succeeded. | Verify permitted discovery through persisted evidence and proposal generation on the candidate. |
| 5. Proposals and owner review | Exact-version approvals and authenticated persisted SQLite review in #84–#86. | [#113](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/113) is stacked on #107. Reconcile the stack, integrate the browser fix in [#115](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/115), and verify hosted authentication and review on shared state. |
| 6. Outreach | #86 includes recipient and message approval, suppression and sandbox transport. | Before any live pilot, verify recipient consent, sender identification and a functional unsubscribe path against [New Zealand DIA guidance](https://www.dia.govt.nz/Spam-Three-Steps). [#109](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/109) tracks a separate owner-approved rollout. |
| 7. Customer acceptance and delivery | #87 records accepted scope, project tasks, evidence and delivery closure. | Verify the complete staged delivery flow with synthetic data and an authorised staging target. |
| 8. Cloud and monitoring | [Schedule monitor run 44380092462](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44380092462) passed. #111 added failure issues. | Capture the next schedule checkpoint in [#108](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/108) and prove notification on a controlled failure. Existing alert runs skipped on successful source runs. |
| 9. Security and cost | Worker policy and workflows define workload caps, authorization checks and fail-closed controls. | Verify private settings, alerts and real runner grants. Recheck budgets and recovery on the candidate. See [#54](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/54). |
| 10. Full acceptance | [Local internal E2E test](../toolkit_tests/test_platform_internal_e2e.py) exercises audit, approval, project closure and paired recovery. | Run the synthetic sequence across independent runners, including interruption, deduplication, queryable state and a controlled alert. |
| 11. Cutover | The encrypted GitHub Actions artifact remains authoritative. | Obtain owner approval for authority changes after #112 passes. Compare stores, retain the trusted checkpoint, run a limited smoke test, and record the candidate commit and rollback evidence. |
| 12. Handover | This matrix and the linked repository runbooks. | Record final runner IDs and check results once the release gates pass. |

## Branch disposition

- #107 is open and reviewable. Its CI uses test Postgres. #113 remains draft and depends on #107.
- [#90](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/90) is the draft encrypted report index. [#92](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/92) adds browser work on that branch. [#99](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/99) is a provisioning record stacked on #92 and overlaps the configuration history in #110 and #112.
- The older open drafts #42–#46, #51–#53 and #55–#58 cover v32/v44, Catalyx and dependency work. Several checks are stale or failing. Port independently required changes after checking master for equivalents. The cloud platform scope is tracked in [#78](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/78).

## Verification on this review

- #114 uses fully resolved temporary paths in encryption and restore fixtures. The macOS checkout passed 67 focused pipeline tests and 18 subtests, with two optional driver tests skipped in that run. Both skipped cases later passed in the dedicated 16-test Supabase suite after installing the driver.
- #115 fixes the field shared by approval and rejection. Both desktop and mobile Chromium review and acceptance tests passed on synthetic data. The master-based Chromium and PDF suite passed 24 tests separately.
- [#116](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/116) removes the acceptance and outreach suites' local database requirement. The portable MoneyMachine run passed 205 tests and 69 subtests, with two existing skips for external receipt and historical model reconciliation.
- The macOS canonical run in the restricted sandbox passed 964 tests and 51 subtests. Eight local HTTP tests initially failed due to socket permissions. Their targeted loopback rerun passed, as did the four supervisor tests and the 24-test browser and PDF suite.
- [PR #114's SonarCloud run](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44497637967) initially returned HTTP 403. Confirm its latest result and security alert status before using it as release evidence.
- Review activity used zero customer sends, paid operations, customer site changes, migrations or cutovers.

## Release decision

Keep the current encrypted artifact recovery path. Before accepting the Postgres candidate, capture a successful authenticated read-only preflight, record the two synthetic runner IDs and their checkpoint revisions, then record the outcomes for a stale writer, invalid key, forced interruption, duplicate attempt and controlled alert. Record rollback evidence before requesting a production cutover. Keep customer sending and paid operations disabled throughout this release verification.

