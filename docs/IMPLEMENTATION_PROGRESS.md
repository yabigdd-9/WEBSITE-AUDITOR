# Cloud platform implementation progress

## Session 2026-11-16

- Fetched master; base e8da967379e38508fe3fee43ac6b49f202e35bbd; focused branch
  cloud/platform-integration. Original work branch was stale; no user edits existed.
- Phase 0 completed: inspected README, CURRENT_STATE, workflows, queue/checkpoint,
  outcomes, vault, review ledger, local discovery, portal, quote and CI definitions.
  Dependency map, classification matrix and backlog: ARCHITECTURE.md.
- Recent merged source includes PRs #79, #80, #77, #76. Runtime CI inspection is
  blocked by GitHub API Forbidden; no new production verification claim.
- Phase 1 implementation: private opt-in PipelineStore SQLite integrated through
  --database; transactional schema v1, unique domains, FK outcomes/attempts,
  append-only history, sticky suppression, private backups, pagination, existing
  checkpoint compatibility. Audit run metadata includes version/checks/evidence,
  statuses and failure categories; source metadata is retained. Daily budget <=6
  committed attempts across runs, per-run <=3. CI includes the new tests.
- Verification (supported Python 3.11.17): 71 targeted tests + 14 subtests passed;
  116 portable MoneyMachine tests + 45 subtests passed. Full toolkit/tests run:
  770 passed, 5 skipped, 14 subtests passed, 3 failures. All three reproduce on
  untouched master in /tmp/mm-platform-baseline: supervisor start/stop and crash
  recovery, plus DNS-dependent integration handler. Initial sandbox portal hang
  was isolated; portal security test passed outside restricted networking.
- After the final checks-completed metadata addition: 36 relevant tests passed.
  Ruff canonical + toolkit/tests and changed new code passed; pip check passed;
  wheel built; workflow YAML/safety assertions and git diff --check passed.
  Both existing strict pip-audit gates found no known vulnerabilities. Gitleaks
  is not installed locally; its existing CI gate remains required.
- No new cloud persistence, archive retention, browser E2E or production run has
  been verified. Five full-suite skips reflect optional browser/PIL dependencies.
- Phase 1 code is implemented and locally tested; hosted phase exit is BLOCKED.
  Phases 2-7 are not claimed complete. See ordered backlog in ARCHITECTURE.md.
- Production: no merges, deployment, workflow dispatch, sends, payments, paid
  activation, new scraping source or live client changes performed.

## Blockers / next task

Phase 1 cloud exit requires a durable hosted destination; Actions artifacts expire
and runner disks are ephemeral. Implement/test private SQLite integration first.
Managed database, remote dashboard and encrypted archive need provider/quota/
access-control review and explicit activation approval. No private keys requested.
Continue independent synthetic implementation while these remain blocked.

## Continued execution — Phase 2

- Phase 1 commit: 64d672e957ea4971aedab1f4c50f59c98a25add1, draft PR #82:
  https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/82. Connector Actions inspection
  now works for this commit (gh remains Forbidden). CI run 43819284858, toolkit
  43819284769, security 43819286996, CodeQL 43819285087, scheduled review regressions
  43819284946 and durable pipeline regressions 43819284950 succeeded. The latter's
  production draft-pipeline job was SKIPPED as required on a PR. These are CI
  results, not a hosted persistence or production gate pass. Sonar result pending.
- Separate Phase 2 branch cloud/discovery-integration, based on PR #82. Reuses
  existing MoneyMachine curated/NZBN/OSM export adapters with optional strict
  cloud URL validator and public category metadata. No new scraper.
- Adds bounded private discovery candidate/provenance history, www-alias dedupe,
  idempotent source imports, schema migration v1 -> v2 and reviewed-prospect links.
  Discovered candidates never independently authorize requests/audits. Suppression
  and original reviewed audit identities remain intact. Import logs are counts only.
- Local verification: 60 tests passed (cloud discovery, store, pipeline, existing
  MoneyMachine discovery). Changed-code Ruff passed. New tests cover offline-only
  CLI, URL normalization bypasses, source adapters, terms attestation, immutable
  provenance, FK migration/backup, capacity, alias dedupe and review boundaries.
- Supabase read-only account discovery found an organization on the free plan,
  one active and two inactive projects, none mapped to this repository by config.
  No project contents read or modified, no project created/resumed. Requested
  intended storage mapping while independent implementation continues. Project
  suitability, quota and access review remain open. No private project IDs are
  committed here.
- Phase 2 export integration is locally tested, not live acquisition or production
  verification. Phase 3 evidence/scoring/proposal integration is next independent
  implementation work; durable hosted phase acceptance still pending.

## Continued execution — Phase 3 internal evidence pipeline

- Phase 2 commit 129bb54eb30846e1c97aec211dc618fa8463f1e7; draft PR #83:
  https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/83 (base PR #82). Its eligible
  stacked-PR workflows succeeded: security 43820510604, cloud tests 43820510666,
  toolkit 43820510661. Master-only checks must run again after retargeting;
  stacked CI is not permission to merge. All reported Phase 1 workflows, including
  SonarCloud 43819284842, succeeded. Production workers remain skipped on PRs.
- Separate branch cloud/evidence-proposals. Adds explicit-config five-dimension
  scoring, hard evidence/suppression/service gates, canonical run/page/check links,
  structured immutable proposal versions and recorded owner rejection reasons.
- Reuses toolkit remediation classification and calculate_quote. Cloud rates and
  effort bands remain unset; missing context contributes zero, buyer intent is
  unknown, contact eligibility stays false, prices remain unconfigured by default.
- Existing queue CLI now preflights the policy before requests and enriches
  complete audit records in the same private-store/checkpoint transaction.
- Local verification: 89 cloud/discovery/store/MoneyMachine discovery tests passed;
  Ruff on changed code passed. New coverage: deterministic scoring, all hard
  evidence/service gates, missing context, pricing configuration, exact content
  hashes, existing NZD quote rules, version persistence, rejection persistence,
  immutable version/review records and preflight failure before requests.
- No customer communication, live-site change, paid call, production merge or
  service activation performed. Phase 3 is synthetic/local until hosted state
  and a bounded reviewed run can be verified. Secure dashboard integration is
  the next independent task. Storage mapping question remains pending.

## Continued execution — Phase 4 owner views

- Phase 3 commit 49dd1e14ed09bfc418ff9bcf6b39e0e14ab609a4; draft PR #84:
  https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/84. Eligible stacked workflows
  passed: cloud tests 43821541191, security 43821541306, toolkit 43821541259.
- Separate branch cloud/owner-pipeline-dashboard. Extends the existing loopback
  authenticated portal with opt-in --pipeline-db, responsive overview, prospect
  search/pagination/detail, discovery, health and exact-version owner rejection.
  No browser decryption, remote bind, send or production change is added.
- Reuses server-side sessions/CSRF; adds bounded review bodies/reasons, write
  rate limit, stale-version protection, safe HTML escaping and private DB errors.
  Store reads no longer need a writer lock after migration, so audit selection
  remains serialized while owner views see the last committed state.
- Local verification: 99 connected portal/store/evidence/discovery/release tests
  passed, then 24 store/ledger tests after installed-path hardening. Ruff and diff
  checks passed. Wheel build includes integration dependencies; an installed-wheel
  smoke test mounted the dashboard outside the source checkout. New tests cover
  unauthorized pages/actions, CSRF/origin, stale/repeated rejection, input/rate
  limits, expiry, HTML escaping, no page-view mutation, read-during-write, missing/
  public DB paths and Git-worktree detection.
- Remote authentication/TLS deployment, mobile real-browser acceptance and review
  of real hosted records remain blocked by storage/deployment configuration. No
  production dashboard or Phase 4 hosted exit gate pass is claimed.

## Continued execution — Phase 5 approval controls

- Phase 4 commit 8fd5552eca2fe5e7fa7d691e5fcb0fb310beb70b; draft PR #85:
  https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/85. Eligible stacked workflows
  passed: cloud tests 43822857772, security 43822857826, toolkit 43822857830.
- Separate branch cloud/approval-controls. Added proposal approval via the
  existing authenticated, CSRF/rate/version-controlled review endpoint. Approval
  applies to one exact internal proposal and never grants message sending.
- Added separate immutable message versions/approvals, staged review/eligibility,
  evidence-backed permission gates, immediate recheck, revocation/opt-out,
  content-recipient idempotency and a bounded built-in sandbox transport.
  No live transport, API send endpoint, automatic sending or paid service exists.
- Added owner outreach-history view. Sandbox SENT records are explicitly
  simulated with external_sends=0 and cannot inflate real contact metrics.
- Local verification: 108 exact cloud CI tests passed; 35 connected portal/
  approval/store tests passed before final additional permission/cap tests;
  30 approval/store tests passed after those additions. Ruff/diff checks passed.
  Coverage includes proposal-vs-message approval separation, stage/consent gates,
  exact hashes, expiry, immediate suppression recheck, revocation, opt-outs,
  transport injection rejection, duplicate simulations across store reload,
  error redaction, per-prospect sandbox cap and history immutability.
- Live outreach remains DISABLED pending separate owner activation and verified
  sender/recipient/NZ compliance/provider/unsubscribe evidence. No send claimed.
  Client acceptance and project tracking are next independent integration work.

## Continued execution — Phase 6 client project records

- Phase 5 commit af44824a71cfff8773c5bdba7154939900b33703; draft PR #86:
  https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/86. Eligible stacked workflows
  passed: security 43823956783, cloud tests 43823956693, toolkit 43823956699.
- Separate branch cloud/client-projects. Connects exact approved proposal +
  explicit owner-verified customer acceptance evidence to an idempotent project
  with frozen scope, tasks, access/assets and sequential delivery milestones.
- Owner portal acceptance and completion forms reuse authenticated CSRF/origin/
  body/rate/version controls. Projects view shows private tracking records.
  Task/milestone completion requires evidence and prerequisites; handover closes
  tracking. No site change, customer handover send, invoice, charge or credential
  collection occurs. Accepted scope/completed evidence/history are immutable.
- Verification: 41 connected portal/project/approval/store tests passed, including
  an authenticated synthetic approve -> acceptance -> tasks -> QA -> handover
  closure flow; 33 project/approval/store tests also passed. Ruff/diff checks pass.
- Customer acceptance remains owner-attested, not independently signature-verified.
  Real customer/project/production acceptance is not claimed. Remaining Phase 7
  work includes interrupted-work quota durability, operational recovery evidence
  and final integration checks. Hosted activation remains blocked on destination
  mapping, quota/access review and explicit deployment approval.

## Continued execution — Phase 7 bounded operational hardening

- Phase 6 commit c5f56f67bc72041fc2940658f097906d0725200c; draft PR #87:
  https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/87. Eligible stacked workflows
  passed: cloud 43825129749, security 43825129902, toolkit 43825129798.
- Separate branch cloud/operational-recovery. Schema v3 requires a private paired
  operational ledger before requests, including first bootstrap. It records
  jobs and durable quota reservations independently of queue rollback. Existing
  SQLite writer locking still prevents overlapping work; readers remain available.
- Quotas include legacy committed events and interrupted reservations, avoid
  double counting committed IDs, and enforce per-job/daily/per-prospect caps.
  An atomic last-committed-job marker repairs interrupted status finalization.
- Backups preserve state + operations with private permissions/integrity checks.
  Missing ledger, corrupt/mismatched schema or history caps fail closed. Added
  explicit CLI pause/lower-budget controls and operational health summaries.
- Local tests cover actual killed subprocess, rollback quota durability, failed
  bootstrap ledger loss, legacy attempts, day/per-job caps, no double charging,
  paired restore, missing-ledger rejection, schema v2 -> v3, pause/caps before
  work and no requests after denial. Current hardening/migration set: 63 passed.
- Earlier integrated full run: 849 passed, 5 skipped, 3 failures, 14 subtests.
  The three failures are the same supervisor/DNS failures reproduced on untouched
  master. Final v3 run: 855 passed, 5 skipped, the same 3 baseline/environment failures,
  14 subtests passed. The exact final cloud CI command passed 124 tests.
  116 portable MoneyMachine tests + 45 subtests passed; canonical/new-code
  Ruff and pip check passed.
- Formal Security Diff Scan is BLOCKED: required config-preflight resource is
  unavailable and its helper is not exposed. SKILL.md says to run that preflight
  before scan review/goal creation. See SECURITY.md for the exact skill source.
  No formal scan success is claimed. Other security CI checks remain enforced.
- Existing README/pyproject declare MIT; no standalone LICENSE was found. Source
  export/provider licensing and current free quotas still require owner review.

## Remaining owner/external gates

No merges, cloud provisioning, deployment dispatch, customer sends, charges,
paid activation or client-site changes were performed. The intended Supabase/
hosted-storage mapping question remains pending. Next owner information needed:
identify the intended existing project, or request a separate free-tier project
proposal. Before activation: verify quotas/access, remote TLS/auth, durable
encrypted archive/retention, formal security review, paired hosted restore and
two independent bounded hosted runs. Stacked PRs must be reviewed and retargeted
with required checks before any authorized merge. Release authorization and
production activation remain unconfirmed; no merges have been performed.

Final synthetic internal E2E also passed: existing discovery adapter -> real
canonical auditor with mocked public-site HTTP/TLS fixtures and real SSRF URL
validation -> evidence/score/proposal -> separate owner/message approvals ->
sandbox result (zero external sends) -> explicit acceptance -> tasks/QA/handover
closure -> paired backup/restore with preserved quotas. No real network or
customer message is used by this test. The dedicated CI command now includes
this test. Latest wheel build/installed-package smoke also passed for schema v3,
paired quotas, restore and the owner project portal outside a source checkout.

The final integration draft targets master so master-only CI/CodeQL/Sonar can
run over the accumulated changes before any future authorized merge. Earlier
phase drafts retain their focused stacked reviews. No merge or activation occurs
from opening this integration review. The formal scan remains blocked as noted.

## Final integration review and CI correction

- Integration draft PR #88 targets master:
  https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/88. Initial integrated commit
  142e75663a99f0f0c66e5f3c79f5fe9d9e9571f2 passed CI 43829568077, security
  43829568043, CodeQL 43829568139, toolkit 43829568125, private-ledger tests
  43829568115 and cloud regressions 43829568039 / 43829568072 / 43829568244.
- SonarCloud 43829568040 failed its unchanged quality gate. Diagnostic issues
  identified portal factory complexity, direct request-ID HTML interpolation,
  repeated literals, and composite/ambiguous exception assertions in new tests.
- Corrected by separating owner/session and pipeline view handlers into explicit
  route controllers, splitting body parsing/decision dispatch/rendering helpers,
  escaping request-derived form/history links, using shared literals and naming
  transactional test operations. Input validation, auth/CSRF/version checks,
  sandbox-only transport, workload caps and test assertions remain enforced.
- Post-correction verification: 125 dedicated pipeline tests and 37 portal/
  history/delivery tests passed; canonical/test Ruff and diff checks passed.
  Full CI and the unchanged Sonar gate will rerun before reporting final status.

## Verified integrated implementation — final source evidence

Source commit **7339e4c1c560354976a9ea40f32243359197ec2c**, integration draft
[PR #88](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/88): all nine workflows
completed successfully after the quality corrections:

| Workflow | Run ID | Result |
| --- | --- | --- |
| CI | 43832640119 | success; canonical 850 passed / 14 optional skips / 14 subtests; portable 113 passed / 45 subtests |
| Local toolkit tests | 43832640298 | success; lint, dependency check, wheel and existing real-browser E2E steps passed |
| security | 43832640193 | success; existing secret/dependency gates |
| CodeQL | 43832640256 | success |
| SonarCloud | 43832640042 | success; unchanged quality gate passed |
| Durable cloud pipeline tests | 43832640084 | success; worker explicitly skipped on PR |
| Scheduled canonical regression | 43832640097 | success; no production worker execution on PR |
| Review shortlist regression | 43832640161 | success |
| Private ledger tests | 43832640493 | success |

The dedicated cloud/vault suite and local command cover 125 passing tests.
Optional vault tests skipped in the generic CI job are exercised by the separate
vault-enabled regression jobs. Local post-correction portal/history/delivery
coverage passed 37 tests. Existing real-browser checks are not a claim that the
new dashboard has passed remote/mobile acceptance.

Implementation is committed/published in seven focused phase branches and
reviewable through drafts #82-#88. PR #88 contains the integration and fixes;
no merge has occurred. Current docs-only evidence updates do not change the
implementation above. Production gates, external configuration and the formal
scan limitation remain as documented. The next owner information needed is the
intended hosted storage/project mapping; no private key or paid activation is
requested. Continue with provider-specific deployment/security planning only
after that mapping is known.

## Encrypted report custody extension — cloud/encrypted-report-index

Built on integration commit `872bf62307d27a355f437946fbe56e431d19d917`.

Completed:
- Pipeline schema v4: unique report checksums, foreign-key audit associations,
  immutable metadata/links, migration and paired database restore coverage.
- Explicit owner-reviewed, offline ciphertext import into a dedicated private
  local archive; original report vault cryptography unchanged.
- Authenticated report index and bounded downloads in the existing owner portal;
  missing/corrupt/expired files fail closed. No browser decryption or key input.
- Backup, recovery, retention, cost and deployment documentation updated.
- Added archive regression/lint coverage to the cloud test job; expanded existing
  CI/CodeQL/Sonar PR base filters to focused `cloud/**` branches. Schedules and
  production-worker guards are unchanged.

Verified locally:
- Archive/store/discovery/operational tests: **80 passed**.
- Report portal/pipeline portal/release tests: **28 passed**.
- Full canonical regression: **888 passed, 5 skipped, 14 subtests passed**, with
  the same three previously reproduced baseline environment failures (two
  supervisor process-reaping cases and the DNS-dependent integration audit).
- Ruff passed across canonical code/tests and changed archive/store scripts;
  diff whitespace check passed.

Not deployed, merged or production-verified. No owner archive/key, external send,
paid provider or new storage service was used. Hosted storage/project mapping,
remote dashboard deployment and real archive recovery remain blocked on owner
configuration and release review. The formal Security Diff Scan tool/preflight
limitation recorded above remains unresolved. Next: inspect focused PR CI and
resolve any regressions, then prepare provider-specific integration when the
owner identifies the intended storage/project.

### Focused archive PR and CI evidence

Draft [PR #90](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/90) targets
`cloud/operational-recovery` (#88). Implementation commit:
`053b81cf5c74413b16a07cae46c5ae0ce9615169`.
All six triggered workflows completed successfully on that exact commit:

| Workflow | Run ID | Result |
| --- | --- | --- |
| CI | 43841613688 | success: canonical 881 passed / 15 optional skips / 14 subtests; portable 113 passed / 45 subtests |
| Local toolkit tests | 43841613700 | success |
| security | 43841613899 | success |
| CodeQL | 43841613716 | success |
| SonarCloud | 43841615545 | success; unchanged quality gate |
| Durable Cloud Draft Pipeline | 43841613693 | success; no production worker on PR |

The built wheel was installed outside the checkout and passed schema v4,
ciphertext round-trip and authenticated report-page smoke checks. No deployment
or production verification is implied by CI. This evidence-only update does not
change tested source. Remaining owner/storage/security-release gates are unchanged.

## Desktop/mobile owner workflow — cloud/dashboard-browser-verification

Based on archive PR #90 evidence commit
`cf983e070a7dbde6e17d8954e2cbccd4e8168910`, whose six workflows all passed:
CI 43842126839, toolkit 43842126739, security 43842126802, CodeQL 43842126761,
SonarCloud 43842126799 and cloud pipeline 43842126708.

Completed:
- Added real desktop/mobile Chromium acceptance covering synthetic private
  pipeline review, search, ciphertext download, exact-version approval,
  independently attested customer acceptance, project creation and logout.
- Verified page loads preserve state, sessions protect records, downloads match
  ciphertext, all screens fit the viewport, and browser requests remain loopback.
- Fixed the reproduced mobile login viewport defect; clarified the proposal
  review reason field for both approve/reject actions.
- Added the suite to the existing required browser CI command.

Local verification: **30 passed** across the new desktop/mobile workflows and
existing pipeline/report portal/release tests. Ruff and whitespace checks passed.
The first run reproduced mobile failure before the viewport fix; desktop passed.
No owner key, actual customer acceptance, new storage service or send was used.
Hosted persistence/project mapping remains unanswered. No merge, production
activation or hosted mobile acceptance is claimed. Next: verify focused PR CI;
connect storage only after the owner identifies its intended project/service.

### Browser acceptance PR and verified CI

Draft [PR #92](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/92), targeting
archive branch #90, implementation commit
`cc9731b255909df87d3381ce317cd166fec4674d`:

| Workflow | Run ID | Result |
| --- | --- | --- |
| CI | 43842972373 | success |
| Local toolkit tests | 43842972269 | success; canonical 881 passed / 17 optional skips / 14 subtests; real Chromium suite 8 passed, including both new desktop/mobile workflows |
| security | 43842972527 | success |
| CodeQL | 43842972301 | success |
| SonarCloud | 43842972348 | success; unchanged quality gate |

All five workflows triggered by this focused diff passed. A separate cloud-worker
run is not triggered by these UI/test-only paths. No production worker, hosted
storage, client action or deployment was activated. This subsequent evidence
update changes documentation only. The implementation is reviewable and browser
verified locally and in GitHub CI; the complete platform is still gated on an
identified durable cloud store, reviewed remote deployment and real recovery /
bounded production execution evidence. The owner's storage question remains
pending; no project was assumed from account names.

## Supabase proposal and account verification — cloud/supabase-free-tier-proposal

The owner requested a separate free-tier setup proposal and explicitly selected
`yabigdd-9's Org` (`luvtvzzhzutxizpfdsgb`). Read-only account inspection verified
its Free plan, one active/two inactive projects, and a project quote of **$0 per
month**. Official current docs confirm the two-free-project allowance, excluded
paused projects, included quotas, inactivity pausing and Free backup limitations.
A free slot appears available; it has not been reserved or creation-tested.

Completed: concrete `moneymachine` / Sydney proposal in DEPLOYMENT.md, cost
boundaries, proposed private schema/RLS/roles and ciphertext custody, backup /
restore gates, and staged activation plan preserving existing integrations.
No existing project contents were inspected. No project, schema, bucket, paid
add-on, secret or production workload was created or changed. This is a docs-only
proposal; no implementation tests or production verification are claimed.
The changelog endpoint returned HTTP 403; current official docs were consulted
through the connected plugin. Next owner action: approve creation of this exact
$0/month project. Creation is separate from approval to deploy or enable sending.

## Approved Supabase project created — 2026-11-16

The owner approved creation after reviewing the $0/month proposal in draft
[PR #99](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/99). A fresh cost quote
remained zero, and inventory showed no existing `moneymachine`. Creation succeeded
in the selected organization/region. Independent project lookup verified
`srymerkhraklwuttzexi`, name `moneymachine`, `ap-southeast-2`, `ACTIVE_HEALTHY`;
organization lookup verified `free` / `tier_free` after creation.

A read-only SQL query succeeded on PostgreSQL 17.11 and returned zero public
base tables and zero Storage buckets. Supabase's security advisor returned an
empty lint list. No application schema, credentials, bucket, data collection,
paid upgrade, external send, existing-project change or production deployment was
performed. This is verified database provisioning, not platform deployment.

Updated DEPLOYMENT.md with the public project reference and actual verification
boundary. Docs-only whitespace check passed; no code changes/tests are implied.
Next: implement/test the Postgres adapter against existing store/quota contracts,
configure least-privilege server credentials securely, and prepare migrations and
access/restore verification before production activation. Storage destination
selection is resolved; the integration and production release gates remain open.

## Supabase pipeline adapter — cloud/supabase-pipeline-adapter

Recovered the published base `ca020ac` in the replacement workspace; the prior
uncommitted adapter files and temporary environment were not retained. Recovered
the exact already-applied migration SQL from Supabase migration history and
reimplemented/retested the adapter before publishing. No existing schedules or
production workloads were switched or deployed.

Completed: private normalized Postgres store, shared immutable transition rules,
CLI/portal integration, separately committed crash-durable job/request ledger,
verified-TLS selected-project/dedicated-role checks, bounded private paired
export/restore, pinned optional driver/lockfile, database CI job and manual-only
independent-runner verification workflow. Documentation records secure credential
configuration and the actual deployment boundary.

Verified locally: **59 passed** across real Postgres, SQLite store, operational
ledger and pipeline/report portal tests; Ruff and diff whitespace checks passed.
Verified remotely: project healthy, migration `20261116105816` present, 12 private
RLS-forced tables, denied anonymous/authenticated access and no quota-deletion
privilege. After a prior automatic-review usage-limit failure (no execution),
the normal continuation write succeeded. A separate restricted-reader connection
confirmed one durable state/event with zero prospects and zero reservations.

Blocked: dedicated runtime LOGIN/`WA_POSTGRES_DSN` must be provisioned through
trusted configuration; available connectors do not provide or securely install
this server credential in GitHub secrets. No password/key is requested in chat.
Python-to-hosted worker connectivity, independent cloud-runner workflow, hosted
restore, remote dashboard and formal security scan remain unverified. Next:
publish focused PR, inspect CI, then configure the runtime secret securely before
an owner-authorized manual persistence run. No sending, paid upgrade or live-site
change is enabled by these additions.

### Focused PR #107 and first integrated checks

Published source `25c5af7de8b4f6c608a7af62a46a2e2aa7a0f8ba` in draft
[PR #107](https://github.com/yabigdd-9/WEBSITE-AUDITOR/pull/107), targeting #99.
Initial cloud/database CI 44075115686, CI 44075115675, toolkit 44075115876,
CodeQL 44075115617 and secret scanning passed. Security audit failed because
pip-audit treats `.[postgres]` as a project path rather than a selectable extra.
Corrected by retaining the original root/email audits and separately auditing a
requirements file derived from the declared optional Postgres dependency.
The local optional-driver audit found no known vulnerabilities.

Initial SonarCloud 44075115623 failed its unchanged quality gate with zero code
issues in its issue summary. Its coverage environment lacked the new optional
Postgres driver/server, skipping the portal's new Postgres path. Added those
pinned test dependencies to coverage and added non-blocking gate-metric
diagnostics without changing quality conditions, exclusions or scan results.

Full local regression on that source: **909 passed, 7 optional skips, 14 passing
subtests**, with the same three baseline supervisor/DNS environment failures.
Added two positive direct/session verified-TLS configuration cases; the dedicated
real Postgres suite now passes **23 tests**. Workflow YAML and embedded Python
compile checks passed. Corrected CI is pending; no merge/deployment performed.

### Verified corrected integration — PR #107

Exact source: `e72f50eea8b14a59d68b466724a58b10872a9005`.
All six triggered workflows passed after the audit/coverage corrections:

| Workflow | Run ID | Result |
| --- | --- | --- |
| CI | 44075718056 | success |
| Local toolkit tests | 44075718136 | success |
| security | 44075718028 | success; existing root/email plus optional Postgres audit |
| CodeQL | 44075718046 | success |
| SonarCloud | 44075718196 | success; new-code coverage 88.2%, duplication 0%, unchanged quality gate |
| Durable Cloud Draft Pipeline | 44075718150 | success, including real Postgres tests; production worker skipped |

Dedicated local real Postgres suite: **23 passed**. Sonar's expanded full
coverage job: **904 passed, 17 optional skips**. A built wheel installed outside
the checkout passed real Postgres persistence, operational-summary and private
export smoke checks. Workflow YAML and embedded Python were validated. Full
local regression evidence and its three baseline environment failures are
recorded above; no failures were hidden or tests disabled.

Credential inspection checked presence only: no WA_POSTGRES_DSN, database URL or
password was available in this workspace, and no local .env exists. A read-only
GitHub check for the secret's name returned Forbidden, so its repository presence
could not be verified. Never request or paste credentials in chat. The smallest
remaining owner action is secure dedicated LOGIN provisioning and server/GitHub
secret configuration according to DEPLOYMENT.md. Then the reviewed manual-only
workflow can verify independent runner connectivity. No merge or dispatch was
performed. This evidence-only follow-up changes no tested source.

## Trusted-device runtime setup — cloud/private-postgres-credential-setup

Continuation checks: Supabase healthy; one synthetic state/event and zero
prospects remain. The dedicated `moneymachine_runner` LOGIN now exists. Read-only
role inspection verified no superuser/CREATEDB/CREATEROLE/BYPASSRLS privileges,
NOINHERIT and membership in `moneymachine_worker`. Its actual credential is not
available here; environment presence checks were false, and a secret-name-only
GitHub lookup still returned Forbidden. No role was created, reset or rotated.

Added a private interactive setup command, read-only by default, with an explicit
option to install the validated connection string in the fixed repository's
Actions secret. It refuses non-TTY input/echo fallback, verifies the DB before
upload, uses stdin rather than secret command arguments/files, redacts errors
and unknown arguments, and never starts jobs/audits/sends/deployments. Pinned
github.com authentication and destination prevent a GH_HOST override from
selecting a different service. GitHub CLI 2.46 help verified the supported flags.
Updated deployment/security/operations documentation and database CI coverage.

Local checks: initial helper plus real Postgres suite **33 passed**; added an
argument-redaction case brings helper coverage to **11 passed**. Ruff and diff
whitespace checks passed. Real owner setup/secret installation has not run:
all secret transports in tests are mocks with synthetic values. Next: publish
focused PR and inspect CI; the remaining owner action is one trusted-device
setup command using the existing runner credential, never a chat upload.

Previous PR #107 evidence commit `232c274` was independently rechecked: all six
workflows succeeded (CI44076207070, toolkit44076207009, security44076207152,
CodeQL44076207077, Sonar44076207066, cloud/database44076206985).

### Current integration base preserved

When PR #130 opened, its remote base had advanced to `37808ac`. Fetched and
merged that base into this feature branch, preserving current master activation
guards, separate encrypted-checkpoint mirror/preflight work and owner-form fixes.
The PR diff remains focused on private structured-store setup. No master merge
or production dispatch occurred. Reconciled SUPABASE_RELEASE_STATUS.md with the
new independent observation that `moneymachine_runner` is LOGIN-enabled; its
credential remains unavailable, and this helper never creates/rotates it.

Post-merge targeted regression: **57 passed, 22 passing subtests**, including
all 11 credential boundary cases, real Postgres transactions/recovery, activation
checks and both separate checkpoint/preflight contracts. The helper-plus-real
Postgres suite alone passed **34 tests**. CI is rerunning on the integrated source.

### Authenticated principal checked before secret installation

Added an explicit read-only `session_user` check to distinguish the authenticated
LOGIN from the adapter's switched worker group. Installation now rejects admin
sessions or unsafe runner privilege drift before passing any value to GitHub.
Real disposable Postgres tests verify the dedicated NOINHERIT runner succeeds,
a fixture administrator fails, and a later CREATEDB grant is rejected. All DDL
for this test remains inside the disposable local server; no hosted role changed.
Combined helper/database suite: **36 passed** (12 credential cases, 24 database
cases); Ruff/diff checks passed. Built-wheel installation outside the checkout
verified command availability and argument redaction. No owner credential or
real secret installation was used. CI will verify this final source revision.
