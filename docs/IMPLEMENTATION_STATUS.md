# Website Auditor release reconciliation

Evidence reviewed on 20 November 2026 (NZDT) against master
`894bed60f7348612895bf08d1f86c289a14f87fa`. This is a point-in-time release
record. [Architecture](ARCHITECTURE.md), [operations](OPERATIONS.md),
[recovery](RECOVERY.md), [security](SECURITY.md), and [cost limits](COST_LIMITS.md)
describe the existing controls.

## Authority and current evidence

The Durable Cloud Draft Pipeline uses GitHub Actions encrypted artifacts as its
production recovery source. The latest scheduled worker run observed in this
review was [44097376009](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44097376009).
The worker restore, audit and checkpoint upload steps completed successfully.
GitHub listed the `pipeline-state` artifact as unexpired at inspection. Preserve
this path while [#112](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/112)
is open. [Schedule-health run 44380092462](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44380092462)
passed, with monitoring subject to the same GitHub scheduling dependency.

The hosted persistence gate is tracked in
[#112](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/112). A verified
Actions connection and independent restore are still required.

The [master check rollup](https://github.com/yabigdd-9/WEBSITE-AUDITOR/commit/894bed60f7348612895bf08d1f86c289a14f87fa/checks)
shows successful Python regression, browser/PDF regression, CodeQL static
analysis, dependency audit and Gitleaks checks. The
[Website Auditor SonarCloud job](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/44531639706/job/135586190671)
failed server processing at 50,030 against the 50,000 line allowance. Its
branch-level diagnostic returned a previous analysis result. The separate Hermes
project quality gate also failed. A fresh successful Website Auditor analysis
and its own gate result are still required. [PR #127](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/127)
pins the diagnostic to the analysis being evaluated.

## Verification on macOS

- Current master passed 75 focused offline tests (22 subtests) and 32 disposable
  Postgres and hosted-portal tests. The database fixtures used a supported C
  locale and local sockets only.
- Applying the changes from #114 and #116 to a disposable checkout of master
  produced 111 checkpoint, acceptance and outreach passes (24 subtests and two
  skips for unavailable live evidence). The browser, loopback and supervisor
  group passed 49 tests on that checkout, and the portable MoneyMachine group
  passed 113 tests (45 subtests).
- The fresh macOS dependency installation could not build the required
  cryptography 50.0.2 without OpenSSL development files. These local results
  used an existing environment with cryptography 46.0.7. The full candidate must
  still pass with reviewed dependencies and the Linux hosted checks.
- No customer messages, paid operations, hosted writes, migrations, secret
  changes or production cutover were performed during this review.

## Dependency and completion matrix

| Phase | Existing implementation and observed status | Smallest remaining verification or change |
| --- | --- | --- |
| 0. Reconciliation | #82–#88, #105–#107, #110–#111 and #113 merged. #89 is a closed issue. #90 and #99 are open drafts. | Review open candidate heads and CI before integration. Preserve the worker described above. |
| 1. Build and test | `ci.yml`, `toolkit-tests.yml`, and security checks exist. macOS fixture fixes are in #114. The SonarCloud allowance blocks current analysis. | Verify and integrate #114, then rerun CI and restore Sonar capacity without changing thresholds or weakening scan coverage. |
| 2. Supabase | `scripts/postgres_store.py`, `scripts/supabase_connection_preflight.py`, `deploy/postgres/`. #107 and #110 merged. #118 and #124–#126 cover preflight and TLS follow-up. | Verify the reviewed session-pooler/TLS configuration and dedicated role read-only from Actions. Independently verify schema/grants and isolated writes. |
| 3. Encrypted recovery | `scripts/cloud_pipeline_checkpoint.py`, `scripts/supabase_checkpoint_store.py`, `scripts/checkpoint_to_postgres.py`. #106 and #113 merged. #119 and #120 cover disposable import and request-budget restore. | Verify independent runner recovery, concurrent claims, corruption handling and rollback against the selected authority. Keep #112 open pending evidence. |
| 4. Discovery and audits | `scripts/cloud_discovery.py`, `scripts/cloud_prospect_pipeline.py`, `scripts/cloud_opportunities.py`. Reviewed imports and evidence-based proposals landed in #83 and #84. | Verify scheduled acquisition, canonical deduplication and audit transitions on an approved synthetic input. |
| 5. Owner review | `scripts/approval_controls.py`, `auditor_toolkit/hosted_portal.py`. Owner actions and version-bound controls landed in #85, #86 and #113. #115 covers desktop/mobile fixes. | Verify login and concurrent review on the hosted candidate with exact proposal version and recipient binding. |
| 6. Outreach | `scripts/approval_controls.py` and MoneyMachine outreach controls. #116 covers synthetic acceptance/outreach testing. | Verify suppression and replay safety through mock transport. Verify consent, sender identification and a functional unsubscribe path before any separately authorised send under #109. See [DIA guidance](https://www.dia.govt.nz/Spam-Three-Steps). |
| 7. Acceptance and delivery | `scripts/client_projects.py` and `toolkit_tests/test_client_projects.py`. Project lifecycle landed in #87. | Verify scope, staged remediation evidence and closure in a synthetic project. Keep payment handoff inert. |
| 8. Cloud and monitoring | Durable worker, missed-schedule checks and failure issue alerts. #105 and #111 merged. #108 tracks schedule and retention. | Verify missed-run and controlled-failure alerting and recovery. Establish independent monitoring if available within the approved constraints. |
| 9. Security and costs | Workflow permissions, encrypted state, RLS controls and durable audit budgets. #88 merged. | Verify real restricted-role denials, budget survival, current security alerts and key-retention procedures on the candidate. |
| 10. End to end | `toolkit_tests/test_platform_internal_e2e.py` covers the synthetic business lifecycle and paired local restore. | Exercise hosted owner review, mock outreach, independent encrypted restore and controlled failure in one recorded acceptance run. |
| 11. Cutover | `postgres-checkpoint-cutover.yml` and `RECOVERY.md` describe staged import and rollback. | Require #112 evidence and explicit production approval before changing database authority or dispatching the cutover. |
| 12. Handover | This matrix supplements the existing architecture, operations, security and cost documents. #117 proposes release acceptance documentation. | Reconcile the final acceptance record with the deployed commit only after operational gates pass. |

Release tracking remains open in [#54](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/54),
[#78](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/78),
[#108](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/108),
[#109](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/109) and
[#112](https://github.com/yabigdd-9/WEBSITE-AUDITOR/issues/112).
