# Hermes Website Auditor execution report

Generated 2026-10-16T09:14:19.416895+13:00. Final status: **BLOCKED_REMEDIATION_REQUIRED** for production expansion.

## Repository

Authoritative branch: `integration/v44-local-machine-convergence`, HEAD `09ab41ab61656ae4b63110d4ee7d418f3fbf07b8`. Original tracked source is preserved. Twenty stashes and all ten original worktree registrations remain; one isolated candidate worktree was added.

Created local commit `a365d6b1ed301cb85d5ade58aa2ae042aa693fcd` on candidate branch `codex/hermes-production-readiness-20261016`, based on `09ab41ab61656ae4b63110d4ee7d418f3fbf07b8`. **Not pushed, not merged, not deployed.** Existing PR #52's base checks were green; those hosted checks do not attest this candidate.

## Implemented and verified

- Repaired stale `.venv` editable registration pointing to a deleted worktree; offline install and dependency checks pass.
- Closed nested JSON production-write bypass; added shared worker ownership and bounded process-group timeout/SIGTERM cleanup.
- Preserved approval metadata/owner decisions and prevented duplicate identical drafts; isolated concurrent-writer tests pass.
- Removed screenshot URL-to-Python interpolation, verified cached URL/hash identity and propagated failed capture status.
- Validated router response model/cost evidence and persisted private stops on unknown/nonzero cost; no paid fallback hides an incident.
- Corrected JUnit pass/fail/skip reporting, Auckland report date and both actual-state dead-letter counters.
- Corrected historical smoke to 63.7059 seconds without editing raw evidence; repaired an optional-Pillow test's invalid empty-path fixture.

## Tests

| Suite | Passed | Failed | Skipped | Executed modules verified |
| --- | ---: | ---: | ---: | ---: |
| final-canonical | 1127 | 0 | 0 | 157 |
| release-money-hermes | 751 | 0 | 2 | 105 |
| zero-token | 18 | 0 | 0 | 5 |

Total separate outer-suite cases: **1896 passed, 0 failed, 2 skipped**; MoneyMachine additionally reports 95 passing subtests. Independent final source review: 90 passed and 12 subtests; the final image-fixture delta has its own independent check. Full canonical coverage includes real local Chromium/PDF and Pillow rendering; no browser/image skips remain.

Every final receipt has unchanged source during its run and zero loaded-code mismatches. Raw marshal-byte comparisons from earlier runs were inconclusive because of serialization identity; final structural code comparisons resolve them. Earlier failed/inconclusive runs remain in the evidence archive. Fresh Python 3.11 environment and offline candidate installation reuse verified local dependencies; this is not a claim of independent dependency re-resolution.

Two release-relevant acceptance skips remain: global/legacy Hermes calls are not reconciled to the workflow ledger; independent live mail/bank receipt evidence is unavailable. The original ten live-path worker-contract checks were not presented as isolated acceptance: they hardcode active checkout paths and could change real artifacts. Synthetic replacements cover the repaired contracts. No final new regression is known.

## FCC and financial controls

FCC has one loopback listener; the model catalog responds, but repeated health evidence is intermittent. Configured global Hermes/FCC model identifiers differ and some fallbacks are unavailable. Nous account telemetry reports a Free plan with zero usable paid credits; this does not establish eligibility of a particular free-model route. No Ollama/llama runtime listener was available.

The maximum additional budget remains NZ$0. No paid inference, credit purchase, subscription upgrade or outreach send was initiated. Workflow ledger model/sent counts remain zero at inspected snapshots. **Actual historical invoices, unrecorded global usage and final remaining provider quotas are not reconciled.** Cost-latch tests are mocks, not verified free entitlement or a shared pre-request quota reservation system. Global Hermes, direct FCC bridge and fallback routes still need common financial admission before activation.

## Production, recovery and scheduling

Eight private SQLite backups and eight separate restores passed schema/count, hash, integrity and FK checks, including independent verification. Nineteen exact DB/directory/sidecar modes were hardened with original modes saved privately. No production business-record migration or live database restore occurred.

Nine affected existing jobs are paused: queue dispatcher, identity resolution, site auditor, NZ discovery, competitor research, weekly review, screenshot, demo blueprint and outreach draft. Eight existing monitoring/testing/reporting jobs remain enabled. The scheduler doctor passes. The prepared six-hour staging schedule is disabled and not installed; no duplicate scheduler exists. No service was restarted, and the active process's loaded revision remains unverified.

Rollback material exists for environment metadata, exact permission modes, private DB backups and per-job resume IDs. Candidate code rollback is its base reference. Production rollback has not been exercised in place. A manual operational dashboard was added to the registered existing Obsidian vault; recurring export is not installed.

## Outreach

No batch is approved for sending in this execution. Actual sends initiated: **0**. Email transport remains disabled. Existing workflow verified sends/send-ledger rows were zero; historic outreach claims are not thereby validated. Delivery failures, replies and unsubscribes were not live-tested. Existing suppressions are retained. NZ consent, sender identification, unsubscribe, address-harvesting and privacy gates are documented from current official sources in P8.

## Remaining gates

1. Verify official allowance/model eligibility and implement shared admission covering every route.
2. Finish full-history redacted secret triage: recent 100 commits scan clean; the incomplete older-history scan produced 15 unconfirmed candidates.
3. Complete exact-candidate hosted acceptance, runtime loaded-revision attestation and remaining worker/emergency-control checks.
4. Reconcile executable soak/configuration and duration criteria, then obtain separate 24-hour/72-hour staging authorisation. No such soak ran this turn; historical elapsed time is not reused.
5. Complete worker-specific production acceptance and exact sender/recipient/message canary approval before writes/sends.

The repaired source is reviewable locally. Production expansion remains gated; safe live containment and recovery work are complete for the stated scopes.
