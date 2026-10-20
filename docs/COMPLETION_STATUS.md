# Completion status — 20 October 2026

This is the current completion register for the isolated `codex/completion-20261020`
candidate. Earlier state reports are retained as historical evidence. The complete
objective includes every outstanding requirement in the review checklist and the
corrected v3.2.1 plan; this batch does not redefine the goal as a smaller code repair.

## Implemented and locally verified across batches

- Preserved 246 existing dirty/untracked files in a private, byte-verified archive.
  The shared checkout, approval records, other worktrees and running services were
  not modified by this batch.
- Fixed operator log queries: requested UTC windows, offset-aware ordering,
  newest-first limiting across all files, bounded result retention, malformed
  record handling and argument validation. Fifteen focused cases pass.
- Adapted the previously isolated reliability fixes without replaying old shared
  commits: runner ownership/deadlines and process-group cleanup; approval queue
  preservation, atomic replacement and content deduplication; screenshot input
  handling and cache validation; truthful test-case counts, Auckland reporting
  dates, failure-state accounting and unknown global cost reporting.
- Strengthened worker report parsing against duplicate fields and excessive
  nesting. Require fresh screenshot artifacts from the current attempt and the
  browser's reported artifact path; stale or invalid files cannot become new proof.
- Added a source/ownership inventory mapping all 23 canonical work packages to
  53 observed files, with definition line numbers and hashes. This is source
  evidence, not independent approval of every component.
- Completed a new redacted Git-history scan across local refs using the current
  repository rules. It found 107 candidates in five commits. Existing path
  allowlists remain a coverage limitation; ownership/restriction/purpose and
  active credential status remain unverified. No values were published or
  credentials rotated. Prior 87/15/16 counts describe other historical scopes.
- Confirmed prior integration proposal commits are already in current ancestry.
  Do not cherry-pick them again. The separate reliability candidate remains
  preserved; this batch selectively adapts reviewed source/test paths.

## Second implementation batch

- All four standalone staging workers now share the scheduled runner's stable
  lock protocol. An explicit inherited descriptor hands ownership to the worker;
  the parent retains the lock through timeout and process-group cleanup.
- Staging snapshots are reused across restarts. Explicit snapshot generations,
  atomic publication, interrupted-publication recovery and committed-evidence
  progress reconciliation preserve previous work. Legacy snapshots without a
  manifest and schema/source drift remain held for review.
- SQLite online backup and validation have bounded deadlines. Missing website
  rows no longer starve later eligible records; child arguments and staging
  MM_ROOT are explicit rather than interpolated code.
- Worker contract tests now copy reviewed source into temporary synthetic
  fixtures, use real runner/worker/storage code and compare complete source
  database dumps. Only the browser fixture is simulated. Tests no longer import
  the canonical runner, hard-code production DB paths or remove real logs.

## Earlier batch validation

The candidate is based on `ec86481ccd6c674c6dfee8d7856d71d97581d08f` with
uncommitted source changes. Do not mistake that base SHA for the candidate's
unchanged Git tree or for an activated runtime revision.

- Clean-source baseline: 1,141 canonical passed / 3 skipped; 747 MoneyMachine
  passed / 2 skipped / 83 subtests passed.
- Repaired candidate: 1,141 canonical passed / 3 skipped; 764 MoneyMachine
  passed / 2 skipped / 83 subtests passed.
- Full Hermes suite: 116 passed with a separate current source/loaded-code receipt.
- Prior focused runner/reporting/screenshot/approval/log checks: 85 passed. These
  overlap full-suite coverage and must not be added into a unique total.
- All three current full receipts exit zero, record no tracked or selected new-source
  changes during execution and observe no loaded-code mismatches. Scope is the
  parent test process; child execution and production runtime are not attested.
- Canonical and changed-file Ruff, compileall, installed dependency checks and
  offline wheel build passed. Real Chromium/PDF/browser checks and 17 imports
  from the extracted wheel outside the source directory passed; the wheel's axe
  asset was also verified. Browser cases overlap opt-in skips in the full run;
  their passing opt-in evidence does not erase the original skip records.
- The first MoneyMachine baseline attempt failed because its harness omitted
  `MM_TEST_SOURCE` and `MM_PYTHON`. That failure is retained. Correcting only the
  harness produced the passing unchanged-source baseline; no tests were weakened.

## Third implementation batch: financial admission

One SQLite coordinator now reserves request quota before repository chat calls.
Git common-directory selection shares it across worktrees and worker runtime roots.
Private reviewed account evidence, exact model/endpoint/output bounds and an
explicitly initialized ledger are required. Unknown cost, quota/billing/auth
blocks, mismatched models and expired dispatched leases persistently stop further
admission. Unmetered Claude/Codex CLI fallbacks and unsupported image generation
remain held. Shell helpers default to status and cannot perform broad service
start/stop. No live financial control files, route activation or provider request
were created. See [the boundary and remaining work](FINANCIAL_ADMISSION.md).

Current validation: **1,150 canonical passed / 3 skipped; 806 MoneyMachine passed /
2 skipped / 83 passing subtests; 116 Hermes passed; 96 overlapping focused passed**.
All three final receipts have exit zero, no source drift and no observed parent
module mismatch. Canonical/changed scoped Ruff, compileall, dependency check and
shell syntax pass. The legacy full-pipeline.py scope has 152 remaining lint
diagnostics (159 at base) and an unmet tenacity dependency. Image acceptance is
function-level only; the complete legacy CLI is not verified. The earlier import
failure and fragment/module attestation mismatch are retained with their fixes;
the attestation probe and secret-scanner allowlists were not weakened.

C20/C30 remain partial: global/installed clients, multi-account requirements,
independent account/provider reconciliation and acceptance are still outstanding.

## Runtime and publication facts

Read-only process inspection found two supervisor-like processes associated with
the canonical and Opus checkouts. The supported launchd lookup returns 113.
Initiators and loaded revisions remain unverified; missing launchd registration
does not prove the system is stopped. No signal, restart, migration or rollout
was performed. The host has 8 GiB RAM and four logical CPUs; workload profiling
and accepted resource policy remain outstanding.

PR #52's last inspected remote head was `09ab41ab`; hosted checks at that head do
not verify this candidate. Candidate publication, independent review, same-head
hosted checks, master integration and runtime activation are still open.

## Required remaining work

| Work | Current evidence and next requirement |
| --- | --- |
| R00/R01 | Current Git/source/process inventory is recorded. Reconcile cross-agent ownership and obtain independent review; no live process identity is inferred. |
| S10/S20 | Review actual historical candidates, owner/restriction/purpose and active exposure. Obtain specific rotation decisions or signed no-rotation-required evidence. |
| S30 | Existing CI/redaction controls are inventoried; finish prompt-injection, permission and secret-regression acceptance across real entry points. |
| C10 | Account-level entitlement, billing, supported-route and reset/quota evidence is missing. External route eligibility remains unverified. |
| C20/C30 | Shared repository chat admission and offline concurrency/crash/failure controls pass locally. Independent billing evidence, global clients, multi-account requirements and acceptance remain open; no route activation occurred. |
| A10 | Startup manifest checks exist. Independent scheduler/process identity, actual DB correspondence and continuous drift observation remain incomplete. |
| Q10 | Current local fixture baseline and repaired full suites pass. Remaining independent accounting/provider/Pillow limits, external tool coverage, hosted checks and review remain separate. |
| D10 | Prior isolated restore drill retained. Fresh release-specific backup/restore/rollback and production-data preservation remain required for rollout. |
| Worker ownership | Scheduled and standalone staging paths, durable generations/progress, bounded backups and isolated contracts pass locally. Independent integration/runtime acceptance remains separate. |
| E10/E20 | Transport remains preview-only. Independent stop-control persistence, durable outbox, uncertain acknowledgements and stale/exact approval acceptance remain required. |
| B10 | Demonstrate an authentic existing review-only NZ lead pipeline on isolated staging data, through audit/demo/proof/quote/draft. Synthetic tests alone do not satisfy this. |
| B20 | Finish freshness/identity deduplication and genuine independent contact labels plus prospect-disjoint holdout acceptance. User confirms independent labels are unavailable; acceptance remains open. |
| B30 | Establish actual delivery effort, explicit operator rate and measured commercial baseline. User confirms no NZD hourly rate is approved; example prices cannot grant acceptance. |
| Reporting | Tested reporting fixes exist locally. Confirm recurring Obsidian destination, retention, period semantics and accepted export behavior. |
| O10/O20 | Hardware is observed; actual worker resource/throughput profiling, confirmed outcome feedback and independent improvement evaluation remain required. |
| G10 | Finish a non-bypassable aggregate release manifest/gate. Ordinary dependency preflight does not satisfy release acceptance. |
| G20 | Complete staging canary and dry-run rollback with outbound off, tested recovery and durable-state preservation. |
| G30 | Reconcile executable duration/config requirements; prepare and obtain exact 24h/72h authorization; capture full-duration independently checked evidence. |
| G40 | Prepare then obtain approval for an exact-revision review-only production canary. No restart is authorized by a green suite. |
| G50 | Optional outreach remains off until sender/eligibility/exact recipient-message approval and delivery safeguards are independently satisfied. |
| Optional adapters | Competitor research, genuine AI prototypes and BrowserGym/Inspect adapters remain unfinished where the intended product requires them. Unsupported secret listing remains documented. |
| Legacy lint | Broader website_auditor scope has 168 diagnostics, verified identical to the base revision. Canonical CI scope and all changed Python paths pass; separate cleanup remains open. |
| Data roadmap | Inventory and complete confirmed gaps in enrichment/provenance, NZ authoritative spine, Overture/OSM, entity resolution, web/market/security intelligence and independent evaluation datasets. These were not silently removed from the objective or claimed implemented. |

No spending, provider activation, recipient approval, live send, production
migration, service control, master merge or deployment follows from these local
results. Missing evidence remains open. Overall goal: **IN PROGRESS**.

The user confirmed that no verified account evidence is available and directed
that external routes remain disabled. No external route activation is authorized.
This policy is recorded in the state ledger; it is not an attestation of what
unidentified already-running processes can do.

See `evidence/completion-20261020-batch3/` for the current ledger, source hashes,
three full-suite receipts and preserved-file verification. The earlier
`evidence/completion-20261020/` retains the historical component inventory, runtime
observation, restore/browser/package checks and redacted scan triage; those receipts
are not relabelled as new runtime or browser runs. User-facing batch reports and preservation
evidence are retained by the completing chat outside the production checkout.
