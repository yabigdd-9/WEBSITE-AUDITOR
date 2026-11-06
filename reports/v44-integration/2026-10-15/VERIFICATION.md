# V44 integration verification — 15 October 2026

Branch: `integration/v44-local-machine-convergence`
Tested code revision: `2bd7a12274ea3403329f45d0cc270bffc1fb2033`
PR: [#52](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/52), open and draft.

## Repository and publication

Authoritative checkout `/Users/dd/WEBSITE-AUDITOR` started at `1de6ebbc` with only the untracked `ops/hermes_zero_token/runner.py.bak`. Fetch showed that GitHub already contained the three supplied commits (`6786e11c`, `077ece21`, `1de6ebbc`). Local and remote were equal; no active rebase/merge or unresolved index conflicts existed. Separate dirty reliability worktrees were left untouched.

Verified repairs were committed as `2cc0910b` (audit execution/coverage) and `2bd7a122` (Hermes safety/reporting). A normal non-force push advanced the remote from `1de6ebbc` to `2bd7a122`, and PR #52 was confirmed at that exact SHA and mergeable. No merge or ready-for-review action was taken.

## Repairs

- Register four static analyzers as required observations and two rendered analyzers using actual browser request and console/page-error events. Version-3 evidence invalidates older analyzer caches. Failure or unavailable capture retains partial coverage and withholds health scores.
- Parse HTML attributes through BeautifulSoup; handle protocol-relative/same-origin resources, exact hreflang self references, malformed language/target declarations, language subtags, metadata attribute order/entities, and decorative empty alt text. Missing lazy-load hints remain heuristic. Domain location does not establish content language.
- Return nonzero worker timeouts/failures and placeholder outcomes; enforce no-send/zero-LLM flags on direct dispatch; block live-mutating worker dispatch pending a separately approved staging workflow. No schedules or services were reconfigured.
- Replace the live-discovery acceptance test with deterministic synthetic ingestion and duplicate checks. Database acceptance fixtures are disposable synthetic databases.
- Reject staging paths that alias production through equal paths, symlinks or hardlinks. Staging audit/schema/integrity failures return failure; foreign-key rows serialize correctly.
- Correct testing worker IDs and cumulative failed-run accounting. Unavailable database accounting remains unknown and cannot produce a passing zero-token attestation.

## Local validation

| Check | Result |
| --- | --- |
| Canonical full suite, including release/storage/pipeline | 1,096 passed; 3 skipped; 3 deprecation warnings |
| MoneyMachine focused schema/operator/pipeline/coverage | 125 passed; 2 explicit acceptance skips |
| Broader MoneyMachine non-slow suite | 662 passed; 12 skipped; 77 subtests passed |
| Hermes acceptance and safety | 30 passed |
| Six analyzer and safety edge-case tests | 45 passed (overlaps other suites) |
| Real Chromium/PDF/portal/proof journeys | 6 passed, including actual console and page-error assertions |
| Tier-1 offline suite | 29 tests OK with inherited credentials removed |
| Canonical and CI-selected MoneyMachine Ruff | Passed |
| Compilation, dependency graph, operator help | Passed |
| Final wheel build and nine imports directly from wheel | Passed |
| Whitespace and staged-diff checks | Passed before both commits |
| Scoped secret scans | Three supplied commits and each repair staged diff passed, with redaction |

Frozen canonical, MoneyMachine and Hermes receipts record unchanged source hashes and whole-module loaded-code comparisons against fresh compilation. Initial exploratory runs were superseded. The first MoneyMachine focused run had a subprocess import error; the supported repository `PYTHONPATH` resolved it. The first tier-1 run inherited an API key and failed its unkeyed quota fixture; the sanitized rerun passed. Neither required weakening assertions.

Canonical skips: two opt-in browser tests separately passed above; Pillow is unavailable for one image-rendering test. MoneyMachine skips: two independent model/provider/receipt acceptance gaps, seven missing email observation cases, one missing rollback migration fixture and two missing legacy Hermes source-database cases. Do not count these as passes. Suite counts overlap and are not additive.

## Hermes metrics investigation

The durable log exactly reproduces the stored reports at their generation timestamps:

| Report timestamp (UTC) | Completed | Failed/error counted | Timeouts omitted by old report | Testing failures omitted by old worker ID |
| --- | ---: | ---: | ---: | ---: |
| 2026-10-13 19:00:53 | 109 | 2 | 4 | 1 |
| 2026-10-14 13:14:15 | 184 | 9 | 7 | 6 |

The increase is 75 additional completed runs and seven additional failed/error runs within a cumulative log, plus three additional timeouts. It is not a per-day reset. Historical unknown-worker errors, testing exits, one queue-dispatch failure and site-auditor timeouts remain recorded. Some historical completed runs were placeholders, so their status is not feature acceptance. No counters or history were reset. `test_passed`/`test_failed` now explicitly count worker runs rather than individual pytest cases.

## Runtime and data safety

Read-only production SQLite verification returned integrity `ok`, zero foreign-key violations, zero model invocation rows/calls/cost, and zero recorded message/proposal sends. The existing supervisor PID `66896` had a fresh heartbeat during inspection. This proves observed process/heartbeat status, not that the newly committed revision is loaded or soak-accepted. Existing Hermes/supervisor services were not restarted or reconfigured. No worker was invoked to mutate the live database; no outreach, paid API/model, provider changes, deployment or n8n integration was performed.

The untracked runner backup remains local with SHA-256 `56231a4e165dde3f6cfefcea9b87cbe95c412706e0ab4502901e635e5c640b02`. Approval queues were not modified. No database, backup, generated cache, customer data or screenshot was added in repair commits. An older tracked `database/money_machine.db.bak` already exists in history; it was not changed or newly staged. Scoped secret scans do not replace the earlier unresolved historical privacy/secret review.

## Hosted checks and readiness

At the starting revision, full regression passed but toolkit lint failed with eight analyzer errors and SonarCloud failed its 80% new-code coverage gate at 31.8%. Both root causes were addressed with real analyzer execution, focused behavioral coverage and lint fixes. No outstanding PR review comments or submitted reviews were returned; CodeRabbit status success on a draft is not human review. The master branch protection API reports no protection, so no enforced required-check list was available.

All 13 entries in the latest PR rollup at `2bd7a122` succeeded: tier-1, toolkit fixtures/browser checks, full Python regression, smoke, both secret/dependency runs, configured SonarCloud workflow and Website Auditor quality gate, CodeRabbit status and existing Vercel statuses. Website Auditor Sonar new-code coverage increased from 31.8% to **87.5%**, with zero new security hotspots and 0.0% duplication; 18 maintainability annotations remain. Hosted coverage job recorded 1,094 passes/5 skips because Playwright was absent there; separate hosted toolkit browser coverage and six local journeys passed. No deployment command was invoked; existing repository integrations emitted their automatic preview statuses following the explicitly authorized push.

A distinct automatic Sonar check for `yabigdd-9_HERMES_MONEY_ENGINE` also attached to this exact commit and failed (Security E, Reliability D; check-run `116036225345`). Its generic check name is later replaced in the PR rollup by the successful Website Auditor check, so the latest all-green rollup must not erase this separate failure. Its API lists 14 open bug/vulnerability annotations. Three TLS annotations encounter explicit validating default contexts; the IndexError annotation encounters a guarded nonempty list. These observations are preserved without silently suppressing issues. Other CLI/path and provider annotations need separate triage and an owner-reviewed resolution. See `secondary-sonar-review.json`. The project's automatic analysis/binding is not configured in this repository's selected Sonar workflow; no remote quality gate, project binding or provider configuration was changed.

Publication and configured CI are verified. **Release readiness remains HELD** pending the secondary Sonar review, remaining independent acceptance/fixture gaps and an exact-revision runtime acceptance decision. Cookie-consent analysis remains explicitly unimplemented and required in rendered mode, so rendered audits correctly remain partial. Hreflang reciprocity and exhaustive browser interaction are outside bounded page observations. Do not grant a new-revision soak, production, contact-release or external-send acceptance from these tests.
