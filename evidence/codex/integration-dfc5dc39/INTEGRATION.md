# Local Codex–Opus integration candidate

Status: LOCAL_INTEGRATION_VERIFIED; shared integration and release not performed.

The human integration owner asked Codex to integrate with Claude's completed
work. Codex combined the pinned committed handoff with its evidence branch in
`/Users/dd/WEBSITE-AUDITOR-codex`, branch `agents/codex-r00`.

## Exact revisions and source scope

- Codex evidence parent: `d0459d8301becb45b6f5f0f5b8102d609002d4ac`.
- Pinned Opus parent: `dfc5dc397504dc80e6d9ffc5f09f3c0c9682ab75`.
- Conflict-free merge: `adec8b282f43f3f2918a4fe4aefcd9c54860324b`.
- Tested application revision: `b032c8c1d22d4000bb5db1d19fe5a4fa21f5d845`.

The merge retains seven Opus commits across nine files: supervisor/PID repairs,
dashboard SQL and missing-import repairs, the required daemon inversion
correction and isolated tests, pipeline provider-state/lane tags and their test,
and the source handoff/evidence documents. `provenance.json` lists every commit
and changed file. The original inverted daemon change is never accepted alone;
its required corrective descendants are included in the pinned tree.

The compatibility commit changes only `toolkit_tests/test_daemon_start.py`
import ordering and intentional local-source bootstrap lint annotations, plus
the extra blank line at EOF in `money-machine/supervisor/pid.py`. Canonical lint
passes. No behavioral source repair was added by Codex in this integration.

The separate seventeen-file `a365d6b1` candidate is excluded. The shared dirty
checkout was not used as a source or merge destination. Opus's branch/worktree
was read-only throughout integration.

## Verification

| Check | Result | Wall-clock receipt duration |
| --- | --- | --- |
| Daemon, supervisor CLI and pipeline focused tests | 73 passed | 42.889 seconds |
| Full canonical toolkit and upgrade tests | 1131 passed, 3 skipped | 102.861 seconds |
| Full MoneyMachine non-slow suite | 693 passed, 2 skipped; 83 passing subtests | 121.544 seconds |
| Dashboard aggregation SQL and missing-contextlib smoke | Both passed with synthetic DBs | See legacy-smoke.json |
| Canonical lint including tests | Passed | Recorded local command |
| Integration helper lint | Passed | Recorded local command |
| Installed dependency graph | No broken requirements | Recorded local command |
| Requirements, schema SQL and CI workflow diff | Empty | Against d0459d83 |

Focused tests ran against the merge plus the recorded compatibility diff, whose
hash remained unchanged. Both full suites ran at the exact committed application
revision above, with `changed_during_run=[]` and `loaded_mismatches=[]`.
The parent-process source probe compares executed module code with fresh source
compilation and handles pytest rewriting. It does not attest child-process code
or the already-running production supervisor.

Run `python -B evidence/codex/integration-dfc5dc39/run_validation.py
--expected-sha <exact-current-candidate-SHA>` with the existing reviewed synthetic
Q10 source fixture. The wrapper freezes HEAD, redirects reports and basetemp to
integration-specific paths, removes inherited credential variables, retains
no-send/no-paid flags and executes suites sequentially. Raw logs, JUnit and
receipts are retained; raw log/XML whitespace is not reformatted.

## Handoff corrections and open gates

Claude's reported review identified its own source SHAs as Codex evidence
commits. The actual Codex evidence commits are 6c4b8143, 67c6f378, 37833d85 and
d0459d83. That report therefore does not establish independent review of those
four evidence commits. The actual Git parents and tests govern this candidate.

The imported search-DLQ work uses the label A10 in its local report. It adds
optional `provider_state` and `lane` arguments to `mm_pipeline.fail()` and tests
their JSON tagging. That does not complete canonical master-plan A10 runtime
attestation, prove automatic provider-error producer wiring, or verify live
provider entitlement. A10_SPEC.md remains a specification with separate source
assignment and activation gates.

The standalone daemon PID-check/write path remains non-atomic. No new atomic
ownership claim is made for it. The existing CLI uses its separate PIDFile path.

Canonical skips remain two opt-in Chromium/PDF cases and one missing-Pillow
case. MoneyMachine skips remain global Hermes accounting reconciliation and
independent provider receipt verification. Historical Hermes ops lint findings,
security/entitlement evidence, exact runtime attestation, independent acceptance,
and separately approved full-duration soaks and release actions remain open.

No shared integration branch update, remote push, deployment, service restart,
production database/configuration change, real provider request or outreach send
was initiated. This is a local reviewable integration candidate, not a release.
