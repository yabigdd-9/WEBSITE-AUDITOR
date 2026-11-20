# Production verification evidence

Inspection date: 2026-11-16. Base master:
`e8da967379e38508fe3fee43ac6b49f202e35bbd` (merged PR #79).

Source inspected includes PR #80 evidence provenance, #77 scheduled review/vault
integration and #76 private review ledger. These are implementation evidence,
not proof of runtime behavior. Existing runbook references runs 43787336509 and
43787336241, explicitly noting skipped workers; this session has not independently
revalidated them.

Attempts to inspect recent PRs and Actions via gh GraphQL/REST returned Forbidden.
Connected commit-workflow lookup for the full base SHA returned an empty list.
No production run, database state, repository variables/secrets, artifact upload,
retention retrieval or account billing has been verified here. No workflow was
dispatched; no merge, service activation or production deployment performed.

New implementation remains local/branch only until PR publication and CI evidence
are recorded in IMPLEMENTATION_PROGRESS.md. Synthetic local tests are not a
production release gate pass.

Before any authorized release record: exact commit, PR and required checks,
workflow/run/job IDs, non-skipped worker result, sanitized aggregates, actual
persisted state before/after, encrypted artifact retrieval/expiration, no-send /
zero-paid / no-live-mutation evidence, rollback and restore results. Verify two
independent hosted runs share the same durable store. Do not describe Actions
artifact carry-forward alone as the permanent database.

Local validation: see IMPLEMENTATION_PROGRESS.md. Full suite had 770 passes and
three failures, reproduced on untouched base master. Hosted acceptance remains
unverified. A draft PR must retain these limitations and cannot be merged based
solely on targeted unit tests.

## Incremental PR CI evidence (not production execution)

PR #82 / 64d672e: CI 43819284858, toolkit 43819284769, security 43819286996,
CodeQL 43819285087, Sonar 43819284842 and cloud regressions 43819284946 /
43819284950 succeeded. PR #83 / 129bb54: security 43820510604, cloud 43820510666,
toolkit 43820510661 succeeded. PR #84 / 49dd1e1: cloud 43821541191, security
43821541306, toolkit 43821541259 succeeded. PR #85 / 8fd5552: cloud 43822857772,
security 43822857826, toolkit 43822857830 succeeded. PR #86 / af44824: security
43823956783, cloud 43823956693, toolkit 43823956699 succeeded. PR #87 / c5f56f6:
cloud 43825129749, security 43825129902, toolkit 43825129798 succeeded.

All are draft/stacked changes. Master-only checks must rerun after any authorized
retarget/merge sequence; required branch protection was not independently read.
Production workers were correctly skipped on PRs. No CI result proves durable
hosted persistence, artifact decryption/retrieval, live communication, real
customer acceptance, a deployed mobile dashboard or actual revenue. No such
production actions or claims occurred in this session.

Final local v3 regression: 855 passed, 5 skipped, 3 failures, 14 subtests passed.
Failures match the previously reproduced untouched-master supervisor/DNS cases.
The exact final cloud CI command passed 124 tests; portable MoneyMachine tests
passed 116 + 45 subtests. These are local/CI implementation evidence only.
Formal Security Diff Scan and all hosted production release gates remain open.

The real canonical engine was exercised end-to-end against synthetic HTTP/TLS
fixtures through project closure and paired restore, with all network mocked
and zero external sends. This verifies internal wiring, not real-site audit
accuracy, real customer consent/acceptance or hosted operation.

PR #88's first master-targeted integrated run passed CI/security/CodeQL/toolkit/
private-ledger/cloud tests; SonarCloud's quality gate failed and is being fixed
without changing exclusions or gates. Its direct request-ID interpolation warning
was addressed with explicit HTML escaping while keeping the existing identity
validation. No formal vulnerability exploitation or formal diff-scan completion
is inferred from that analyzer warning. Exact correction verification is recorded
in IMPLEMENTATION_PROGRESS.md. Production activation remains unperformed.

### Corrected integration verified in CI

At source commit 7339e4c1c560354976a9ea40f32243359197ec2c on draft PR #88,
all nine workflows passed, including the unchanged SonarCloud quality gate
(43832640042), CodeQL (43832640256), security (43832640193), full CI
(43832640119), toolkit/browser checks (43832640298), cloud tests
(43832640084 / 43832640097 / 43832640161) and ledger tests (43832640493).
Generic CI reported 850 passed and 14 optional skips; separate vault-enabled
jobs cover encryption, and the existing real-browser steps passed.

These are PR CI runs. The durable production worker is explicitly skipped on
PRs, as confirmed by job inspection. No hosted database changes, production
archive retrieval, remote owner authentication or production deployment were
verified. Formal Security Diff Scan remains unavailable; a deployment-context
security review still needs the actual chosen host/database/archive settings.

## Encrypted report index: verification boundary

The archive/index/download extension is not deployed. Tests use synthetic records
and test-generated vault keys; no owner key, prospect archive, external send or
new storage service is used. Local regression results and the focused PR are
recorded in IMPLEMENTATION_PROGRESS.md. Hosted persistence between independent
cloud runs and real owner archive recovery remain unverified.

## Desktop and mobile dashboard browser acceptance

The dedicated `test_pipeline_browser_e2e.py` exercises a real Chromium browser
at desktop 1440×1000 and mobile 390×844 viewports with touch/mobile emulation.
It uses synthetic prospects, findings, proposals and ciphertext, plus a private
throwaway database and loopback-only server. Browser requests outside that server
are blocked and fail the test. No real prospect audit, owner key or send occurs.

Coverage includes owner login/logout, denied unauthenticated access, every
pipeline review screen, no page-load business mutations, prospect search,
private ciphertext download with byte-for-byte verification, explicit proposal
approval, separately attested synthetic customer acceptance and project creation
without live changes or invoicing. Each pipeline screen is checked for horizontal
viewport overflow, no-store headers and the existing script-blocking CSP.

The first mobile run reproduced a missing login viewport declaration (980px
layout at a 390px mobile width); the corrected responsive login passes both
viewports. The review reason label applies to either approval or rejection.
Local verification: 30 browser/portal/release tests passed, including the two real
Chromium workflows. The toolkit CI browser job now explicitly runs this suite.
This is local emulation, not proof of a remote HTTPS dashboard or real-device
production acceptance. Those deployment gates remain open.

## Supabase provisioning verification — 2026-11-16

Following explicit owner approval of the $0/month project proposal, a separate
Supabase project was created: `moneymachine`, reference `srymerkhraklwuttzexi`,
Sydney `ap-southeast-2`, organization `luvtvzzhzutxizpfdsgb`. The quote remained
zero immediately before creation. Separate post-create lookups verified
`ACTIVE_HEALTHY` and organization plan `free` / `tier_free`.

A read-only query verified a responsive PostgreSQL 17.11 database, zero public
base tables and zero Storage buckets. Security advisor returned `lints: []` for
the empty project. These are provisioning checks only: no pipeline adapter,
application migrations, prospect records, bucket, credentials, worker, hosted
dashboard or independent-run persistence test was activated or verified. Existing
projects were untouched. Exact reviewed code/run/restore evidence is still
required for a future authorized application release.

## Private schema and synthetic persistence verification

Applied migration: `private_pipeline_store`, recorded by Supabase as
`20261116105816`, in project `srymerkhraklwuttzexi`. A later independent inspection
confirmed 12 private tables and an initially empty state. Privilege checks
confirmed forced RLS, denied anonymous/generic authenticated access, and no
worker DELETE privilege on reservations. The security advisor returned no lints
after initial migration application.

The first attempted synthetic write was not executed because automatic approval
review failed at a usage limit; it was not a finding that the SQL was unsafe.
On continuation, normal approval review accepted the same bounded action.
A restricted worker-group transaction committed one empty-prospect state, one
synthetic storage-verification event and one completed verification job. A
separate reader-group connection confirmed one state, one synthetic event,
zero prospects and zero request reservations. No audit, outreach or customer
record was involved. This is management-connection persistence evidence, not
proof of the Python adapter connecting from a GitHub runner.

The Python adapter is tested against a real disposable PostgreSQL server for
separate-process reads, writer exclusion, rollback/crash quota durability,
limits, immutable histories, project/artifact relations, private paired restore,
authenticated portal behavior and missing credentials. The runtime credential
and future manual independent-runner workflow remain unverified.

### Corrected adapter integration CI verified

Draft PR #107 source `e72f50eea8b14a59d68b466724a58b10872a9005` passed
CI 44075718056, toolkit 44075718136, security 44075718028, CodeQL 44075718046,
SonarCloud 44075718196 and cloud/database tests 44075718150. Expanded Sonar
coverage exercised the Postgres portal path; unchanged gate passed with 88.2%
new-code coverage and 0% duplication. Local disposable Postgres suite passed
23 tests; installed-wheel persistence/private export smoke passed.

These checks verify implementation and synthetic database persistence, not an
unattended hosted application release. Runtime secret availability could not be
confirmed through GitHub (secrets-name lookup returned Forbidden); no runtime
database credential was present locally. No master merge, workflow dispatch,
external send, paid upgrade, hosted dashboard or client-site change occurred.
