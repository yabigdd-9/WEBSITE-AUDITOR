# R00 — current repository and operating state

Integration owner: human operator, confirmed in chat. Execution worktree is
`/Users/dd/WEBSITE-AUDITOR-codex`, branch `agents/codex-r00`, source baseline
`09ab41ab61656ae4b63110d4ee7d418f3fbf07b8`.

## Evidence and provenance

- `r00-command-evidence.json`: timestamped commands, exit codes, branch, worktree,
  stash and process metadata. No provider inference requests or service changes.
- `r00-runtime-snapshot.json`: read-only SQLite checks, aggregate accounting,
  scheduler state and historical soak controller identity.
- `EXECUTION_STATE.json`: all 23 canonical packages, dependencies, owners,
  current evidence classification and remaining human gates.
- Canonical reference ZIP: Downloads/HERMES_WEBSITE_AUDITOR_MASTER_PLAN_v3.2.1_CORRECTED.zip.
  SHA256: `58e98a7a0d0b25f5a62c868c6ba99e1a6565aec04ddfb9297a2c2cba906d30cb`.
  CRC check passed; 15 listed manifest hashes matched during read-only inspection.
- The separate v3.2 one-master-prompt describes a planning task. Its embedded
  instructions do not replace the user's current execution assignment.

## Verified repository facts

The initial Codex checkout was clean. No active merge, rebase, cherry-pick,
revert or unmerged index entries were found. Twenty stashes and thirteen
worktree registrations were observed, including one stale registration.
None were modified, removed or restored.

Candidate `a365d6b1ed301cb85d5ade58aa2ae042aa693fcd` exists and descends
from this baseline, but is not included in it. It changes seventeen files,
including the model router, Hermes runner, daily reporting, screenshots,
outreach drafts and their regression tests. Review this existing work before
assigning overlapping repairs. No candidate was merged or cherry-picked.

The shared integration checkout had seven tracked changes plus untracked
artifacts at initial inspection. Dirty source included `auditor_toolkit/models.py`
and `money-machine/mm_email_network.py`. They were preserved. Opus's assigned
checkout was clean at the same baseline; clean status is not evidence that
its R01 assignment is completed or abandoned.

## Runtime truth and open blockers

The production supervisor was PID 66896 with a fresh heartbeat at inspection;
its loaded Python revision is unknown. The scheduler contains seventeen jobs:
eight enabled and nine paused. The snapshot retains each job's observed status.

FCC has duplicate port-8082 listeners, including an all-interface listener.
PIDs changed during inspection. Bounded local health/catalog probes failed;
subsequent probes timed out. The audit did not restart or stop either process.
The integrations and A2A launchd jobs had no running PID with recorded exit
statuses 2 and 78. The soak controller is blocked, has no active run, and
references historical revision b349cd9 rather than the current baseline.

Production and existing staging SQLite quick checks passed with zero foreign-key
violations. Observed production accounting records one blocked attempt, zero
model calls, zero recorded USD cost, zero sent messages and zero outreach-send
ledger rows. These aggregates do not reconcile global provider invoices or
unrecorded activity. Route entitlement and shared financial admission remain
unverified; no paid or unknown-cost route is approved by this evidence.

## Ownership and execution boundary

The user assigns R01 to Opus, overriding the plan's default Codex assignment.
No populated cross-agent ownership register or R01 completion artifact was
found. `OWNERSHIP.md` records Codex's current evidence and scratch scope only;
it does not claim ownership of application source or another agent's files.

R00 inspection is complete. Q10's supported synthetic baseline and D10's isolated
restore drill are now complete; see BASELINE_TESTS.md and RESTORE_DRILL.md.
A10's specification is complete in A10_SPEC.md; no source implementation is
included. A10/E10 and source implementation require the
R01 map and explicit file assignments. C20 additionally requires C10 route
entitlement evidence; S30 requires S10 triage. Production changes, exact
credential rotation, long soaks and outreach retain separate approval gates.

## Proposed source packages for integration-owner assignment

1. Review the existing a365d6b1 candidate as a unit before assigning its seventeen
   overlapping paths. Do not duplicate or silently integrate it.
2. A10: extend existing runtime/soak probes with read-only attestation fixtures;
   final paths depend on R01. Never label disk HEAD as the loaded process.
3. C20/C30: extend the existing canonical model-router boundary and tests after
   R01/C10, covering concurrent reservations, unknown costs, bounded failover and
   crash reconciliation. Global Hermes/FCC coverage must be demonstrated.
4. S30/E10: assign disjoint security and fake-transport tests after R01/S10;
   retain no-send defaults and existing approval/suppression records.

No source package is claimed implemented or released by this report.

## Finalized evidence batch

Canonical baseline: 1124 passed/3 skipped. MoneyMachine baseline: 692 passed/2
skipped plus 83 passing subtests. Both final source-run receipts have no tracked
source changes during execution and no observed loaded-code mismatches. Skips
and baseline Hermes lint findings remain open, not release clearance.

Opus correction/isolation at d61306b was independently checked in an exact-byte
scratch copy: seven committed tests passed and process signal handlers were
restored. New uncommitted Opus pipeline edits are excluded. See
OPUS_FINAL_REVIEW.md for exact commits and limits. These evidence-only Codex
commits do not integrate any application source or attest production runtime.

## Subsequent authorized local integration

The integration owner subsequently asked Codex to combine the committed Opus
handoff with this branch. Opus dfc5dc39 was merged locally as adec8b28; the
compatibility-only source revision b032c8c1 passed 1,131 canonical cases (three
skips) and 693 MoneyMachine cases (two skips), plus 83 passing subtests. See
integration-dfc5dc39/INTEGRATION.md. The original evidence-only batch above
remains historical; shared integration, production and canonical A10 activation
remain outside the completed local integration scope.
