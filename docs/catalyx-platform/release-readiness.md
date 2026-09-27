# CatalyxLabs Website Auditor release readiness

- **Status date:** 2026-09-28
- **Implementation base:** `f9e0694582c4cada39a08c91f86a4adaf083feff`
- **Latest committed implementation revision:** `eb9f262e231934a5c47b009c411c8e173edbd00c` on
  `codex/catalyx-rebuild-phase1-5` (checked 2026-09-28)
- **Original app implementation revision:** `ed182a76daab33622a27665596fc7654342b16ef`
- **Worktree follow-up:** atomic login and account-recovery email rate limits,
  cross-IP regression coverage, readiness inventory, and the FSM mapping
proposal are committed. Current local recovery-delivery/throttle hardening
  and this readiness update are uncommitted; untracked `experiments/` is
  preserved.
- **Worktree:** `/Users/dd/Documents/Codex/2026-09-27/build-me-a-new-website-with/work/catalyx-auditor-rebuild`

## Built in this local slice

- Public product pages and synthetic sample report.
- Customer workspace with verified-email accounts, password recovery,
  normalized site records, authorization receipts, audit status, cancellation,
  released-report viewing, privacy request intake, and an approved,
  account-scoped JSON export flow after administrator identity review.
- Administrator console with TOTP-protected named accounts, reviewer role,
  customer controls, authorization review, persisted failed-job review with
  attempt counts and reasons, reviewer-gated manual retry, quality review,
  report release/withhold, privacy request review, operations view, and activity
  log.
- Separate application store with workspace scoping, schema versioning,
  reset-token hashing, and local-only verification mail. SQLite is the local
  default; startup rejects a final-path symlink and verifies owner-only file
  mode `0600`. A PostgreSQL adapter and explicit migration command are
  implemented but have not been exercised against a live server.
- Versioned customer/admin API, CSRF checks, health liveness/readiness routes,
  and API contract documentation.
- Authentication rate limits persist across app instances in the database and
  store hashed client identifiers. Login failures also have a provisional
  per-normalized-email bucket (12 attempts/hour). Only failed credentials
  consume it; a valid sign-in bypasses and clears the bucket, so an attacker
  cannot lock out a customer who has valid credentials. Owner approval is
  still required for thresholds and production edge/client-IP behavior. Schema
  version 4 adds the shared buckets;
  version 5 adds a fencing token so an expired worker cannot commit after its
  job has been reclaimed. SQLite migration is tested; PostgreSQL migration is
  not live-verified.
- Verification and recovery links use `CATALYX_PUBLIC_BASE_URL` when set;
  serverless deployments reject dynamic host-derived links and require HTTPS.
- Local verification and password-reset messages now expire with their
  underlying one-time tokens and are removed from the staging mailbox when
  consumed or expired. This does not define production mail-provider log or
  retention behavior.
- Hosted startup now validates the presence and shape of a PostgreSQL URL,
  fixed HTTPS origin, administrator TOTP key, and authenticated SMTP settings
  for preview and production, then keeps the scan worker disabled. Migrations
  remain an explicit command; configuration validation does not establish
  provider reachability or email deliverability. A synthetic Vercel-preview
  test covers the configuration gate. A READY Vercel branch preview now exists
  for the current commit, but Vercel SSO intercepted unauthenticated route
  checks; the preview app/runtime and its environment configuration remain
  unverified. It is not an isolated staging rehearsal or production deployment.
- Public account registration is now closed by default in hosted environments;
  the registration page, submission route, and public signup calls to action
  stay hidden or unavailable until `CATALYX_REGISTRATION_MODE=open` is set.
  Local development remains open by default when that variable is omitted.
  This is a fail-closed implementation default, not owner approval of open
  self-service; A1 onboarding and any invitation/admin-review flow remain
  unresolved.
- The project now has `uv.lock` and a separate hash-pinned
  `requirements-catalyx-web.lock` for the selected web runtime (`web` and
  `portal` extras). `uv audit --locked` for the selected production web profile
  reported no known vulnerabilities in 62 packages on 2026-09-28. The full
  all-extras audit found two advisory records for optional `diskcache==5.6.3`,
  pulled in by the local `ai` extra; that package is absent from the web lock.
  The production profile explicitly includes `cryptography`, required for
  authenticated encryption of admin MFA seeds.
- Administrator MFA seeds use a versioned AES-GCM envelope bound to workspace
  and user identifiers. SQLite creates an owner-only `*.totp-key` sidecar
  (mode `0600`) when no key is supplied; PostgreSQL requires the explicit
  `CATALYX_TOTP_ENCRYPTION_KEY`. Initialization encrypts legacy plaintext seeds
  and fails closed if stored ciphertext cannot be authenticated. A dry-run-first
  `catalyx-totp-key-rotate` command validates and re-encrypts seeds in one
  transaction; synthetic SQLite tests pass. Production secret delivery, live
  database/backup rehearsal, coordinated key update, and lost-key recovery
  remain unimplemented.
- A source-derived data map and local data-flow diagram are drafted in
  `docs/catalyx-platform/data-map.md`. Provider/region, processors, retention,
  backup expiry, deletion, logging, and key-lifecycle decisions remain open;
  the draft is not owner or privacy/legal approval.
- A source-derived route/role matrix and synthetic authorization test are
  recorded in `docs/catalyx-platform/authorization-matrix.md`. Independent
  role review and deployed session/revocation checks remain open.
- Fixed one-page audit adapter with DNS pinning, strict redirects, robots policy,
  request/byte/time bounds, and sanitized reports. The customer-facing worker
  remains disabled; an operator can invoke the manual local harness only.
- Site submission now rejects alternate numeric IP forms, non-global/reserved/
  multicast literals, malformed DNS labels, scoped IPv6, credentials, and
  scheme/port mismatches. Public IPv6 literals are normalized with brackets;
  URL validation and the pinned transport share the same public-unicast check.
  The transport queries all A and AAAA answers under a two-second DNS lifetime
  and pins the vetted address to the TCP connection; the adapter no longer runs
  a redundant unbounded DNS preflight. Synthetic tests cover mixed
  public/private DNS answers and connection-time resolution; deployed worker
  egress isolation remains unverified.
- A first responsive visual system and synthetic-only marketing content. Privacy
  and terms pages clearly remain owner-review drafts.

## Verification recorded

- `python3.11 -m pytest -q toolkit_tests`: **224 passed, 5 opt-in browser tests skipped** on 2026-09-28; three upstream deprecation warnings.
- Catalyx web integration, authorization matrix, and migration checks: **23
  passed**; SMTP/configuration and synthetic delivery checks: **23 passed**;
  the separate Catalyx customer/admin browser walkthrough: **1 passed**.
- Combined Catalyx web/backend/configuration/mailer suite: **46 passed**; the
  customer/admin browser walkthrough separately passed **1 test** using
  disposable SQLite and synthetic `.invalid` accounts.
- `uv build --sdist --wheel --out-dir /tmp/catalyx-auditor-package-check`
  completed. Both artifacts contain the Catalyx web app, SMTP module, and
  static assets. Setuptools emitted a license metadata deprecation warning.
- After a naming-only security cleanup, the TOTP/robots-focused regression set
  passed: **7 passed, 14 deselected**.
- `WA_CATALYX_WEB_BROWSER_E2E=1 python3.11 -m pytest -q toolkit_tests/test_catalyx_web_browser_e2e.py`: **1 passed**. The browser covered synthetic registration, local email verification, site authorization, MFA admin sign-in, and queue approval; it used a disposable SQLite database.
- `WA_BROWSER_E2E=1 python3.11 -m pytest -q toolkit_tests/test_browser_e2e.py toolkit_tests/test_flow_e2e.py toolkit_tests/test_monthly_browser_e2e.py`: **4 passed** for the existing auditor's Chromium/PDF/portal flows.
- `MM_TEST_SOURCE=... python3.11 money-machine/test_acceptance.py`: **56 passed, 2 intentional safety skips** against a read-only source snapshot; its report and log were written under `/tmp`.
- Python compile check and `git diff --check`: passed.
- Ruff check of `catalyx_web` and all three Catalyx test files passed;
  `uv lock --check` passed.
- Focused hosted-registration closure, public-page behavior, and API tenancy
  regression checks passed: **3 passed**. Ruff and compile checks passed for the
  changed app and hosted-config test. These checks do not close the full Phase C
  or Phase E acceptance gates.
- Full `toolkit_tests` rerun after the hosted-registration change: **208 passed,
  5 skipped**, three upstream deprecation warnings. The five opt-in browser
  tests remained skipped in this run.
- Full suite after bounded DNS and address-class hardening: **225 passed, 5
  skipped**, three upstream deprecation warnings. The dedicated Catalyx
  synthetic browser journey separately passed **1 test** after its expected
  review-desk copy was refreshed. Nineteen focused URL/address-class/DNS and
  transport cases passed, including timeout, mixed A/AAAA, redirect, and pinned
  connection coverage.
- Latest full `toolkit_tests` run after schema version 5 worker-lease fencing,
  cooperative active-job cancellation, and failed-job operations visibility:
  **230 passed, 5 opt-in browser tests skipped**, three upstream deprecation
  warnings. The dedicated Catalyx browser E2E test separately passed **1 test**
  against the updated schema. Regressions confirm stale-worker fencing,
  cancellation invalidation, and reviewer retry boundaries. This is not a
  deployed worker rehearsal; no soak test was run.
- Ruff passed across `catalyx_web` and all three Catalyx test files. Gitleaks
  found no leaks in `catalyx_web` or `toolkit_tests/test_catalyx_web.py`.
- SQLite file-permission coverage confirms owner-only mode for new and existing
  databases and rejects a symlink database path.
- Bandit (`bandit -q -r catalyx_web`) completed with no findings.
- Gitleaks scans of the new web app, tests, Catalyx docs, decisions, project
  metadata, and lockfiles reported no leaks. The earlier broad multi-path scan
  reported 52 redacted findings; a fresh full-worktree scan on 2026-09-28
  attributed 53 findings across 60.46 MB: 52 in 23 tracked
  `money-machine/fixtures/email_captures/` files and one in an untracked
  vendored Pydantic probe file. A value-shape-only review found four repeated
  low-entropy placeholder strings, with no Google API-key-shaped value. No
  matched values or fixture lines were exposed. These findings are classified
  as placeholder false positives rather than evidence of live credentials;
  the source evidence remains unchanged.
- Current scoped refresh on 2026-09-28: Gitleaks reported no leaks in
  `catalyx_web`, the Catalyx web and mailer test files, or
  `docs/catalyx-platform`; `uv audit --locked --no-group dev --no-extra ai
  --no-extra browser --no-extra smtp` found no known vulnerabilities or adverse
  project statuses in 62 packages. The full scan's placeholder findings are
  attributed and classified above. Bandit's earlier no-findings result is retained as prior
  evidence; it could not be reproduced in this refresh because Bandit is not
  installed in the active Python 3.11 environment.
- Focused read-only source security review on 2026-09-28 covered authentication,
  session/CSRF handling, selected HTML/API routes, database query construction,
  SMTP composition, report rendering, and the manual audit adapter/egress
  transport. The reviewed paths use parameterized values, escaped rendered
  report fields, hashed one-time tokens, role and workspace checks, and bounded
  pinned outbound connections. No concrete exploitable defect was established
  in this focused pass. This is not an independent review or penetration test.
  Release gaps remain: production proxy/client-IP semantics are unverified,
  the provisional per-account threshold needs owner approval and live
  PostgreSQL verification, and the worker still lacks
  independent OS/network egress isolation and production quotas.
- Browser preview from the current worktree: public home, registration, sign-in,
  recovery, and sample-report pages opened. Their accessibility trees expose
  page headings, named links, labels, form controls, sample-data status, and
  report evidence. The opt-in browser walkthrough checks keyboard focus to the
  skip link and main content, active-link `aria-current`, and horizontal
  overflow at 320px and 640px CSS viewport widths. Doubling each body's
  computed font size at a 320px CSS width also passes the no-horizontal-overflow
  check on those five public/account pages; it is not a test of browser zoom or
  a human screen-reader review. Source styles include
  visible focus outlines, reduced-motion handling, and 46px form controls.
  Muted text color was darkened after a contrast calculation. This remains a
  focused review: a person still needs to review keyboard and screen-reader
  operation; actual browser zoom and non-text contrast measurements remain
  open. A rendered text-contrast scan now covers the local routes below.
- Local HTTP health is available at `http://127.0.0.1:4174/api/health`; the
  unauthenticated `/api/v1/me` request returns `401`.
- Focused staging security/regression checks on 2026-09-28 covered workspace
  dashboard counts, admin-role visibility, consumed and expired local mailbox
  bearer links, fixed-origin verification, and browser security headers:
  **6 passed, 41 deselected**. Ruff, Python compile, and `git diff --check`
  passed. Two upstream Starlette/httpx deprecation warnings remain. This is a
  targeted check only; no soak test was run.
- Privacy export and review-role checks on 2026-09-28: **3 passed, 45
  deselected**. Synthetic coverage includes customer-only account scope,
  released data boundary, secret-field exclusion, download audit logging,
  single-use completion, cross-customer denial, and refusal to approve deletion
  as an export.
- Full Catalyx web and mailer integration modules after these changes:
  **72 passed** on 2026-09-28, with two upstream Starlette/httpx deprecation
  warnings. This covers SQLite staging behavior only; PostgreSQL remains
  unverified.
- Refreshed preview on Python 3.11 returns healthy liveness/readiness and HTTP
  200 for `/resend-verification`. The prior Python 3.14 system runtime is not
  usable here because its cryptography installation is missing `_cffi_backend`.
- Local Cloudflare compatibility probe on 2026-09-28 returned FastAPI,
  `/runtime-check`, and `/crypto-check` responses. AES-GCM round-trip passed;
  310,000-iteration PBKDF2 matched the CPython reference (403 ms local wall
  time on the latest run). This is a narrow local prototype check, not a soak,
  Cloudflare CPU measurement, full auth integration, or production-host test.

The test runner emitted upstream deprecation warnings about the installed
Starlette/httpx test-client combination. A full all-extras dependency audit
reported two advisory records for optional `diskcache==5.6.3`, pulled in by the
local `ai` extra. It is excluded from the selected web runtime. The advisory
describes unsafe pickle deserialization when an attacker can write to the
cache directory; keep that optional feature out of the hosted app and review
its cache permissions before local use. This is dependency advisory evidence,
not an independent security assessment. No PostgreSQL integration, independent
security assessment, load test, backup restore, or production-like worker
isolation test was completed. The 2026-09-28 finite local Cloudflare
compatibility run passed `/`, `/runtime-check`, `/crypto-check`, and `/db-check`
on Wrangler 4.142.0. Native `hashlib.pbkdf2_hmac` remains unavailable in the
Python Worker runtime; standalone WebCrypto AES-GCM and 310,000-iteration
PBKDF2 reference checks passed at 388 ms local wall time, and the local D1
`SELECT 1` passed. First runtime request took about 51.9 seconds in local
development; the bundle was 31.59 MiB across 2,090 modules. These do not
establish Cloudflare CPU, deployed cold-start, quota, egress, or app-integration
fit. WebCrypto is not integrated with app authentication and no D1 app adapter
exists. Current official limits show Workers Free at 10 ms CPU/request, D1
Free at 5 million rows read and 100,000 rows written daily, and Queues Free
with 24-hour message retention. Free-plan commercial suitability and
continuity still need owner/legal review. See
`hosting-cost-and-terms-assessment.md` for the dated source review and caveats.

## Release blockers

1. Hosting is blocked. The current Vercel workspace is Hobby, whose terms
   restrict use to personal/non-commercial projects; that is not an approved
   host for the commercial Website Auditor. Cloudflare Workers Free remains a
   technical candidate, but the local compatibility probe is not the Auditor
   app; its 10 ms CPU budget, integrated WebCrypto auth, D1 application adapter,
   queue recovery after 24-hour message expiry, and scanner egress policy remain
   unproven. The applicable Free-plan terms,
   business-critical suitability, NZ data-processing obligations, and service
   continuity also need owner/legal review. Render Free explicitly advises
   against production use and its free Postgres expires after 30 days; Fly.io
   offers only a seven-day/two-VM-hour trial before paid compute. OCI Always
   Free is a technically plausible VM path, but its free instances can be
   reclaimed under low utilization, have no SLA/support continuity protections,
   and require Australian data residency in the nearest documented regions.
   No alternative is approved. The Workers Paid tier starts at US$5/month and
   conflicts with the current NZ$0 ceiling. Keep production hosting blocked
   until the owner selects and approves a verified $0 commercial path (including
   any OCI reliability and cross-border data tradeoffs) or changes the budget,
   followed by approved data region and live migration/restore rehearsal. See
   `hosting-cost-and-terms-assessment.md`. No production account or resource has
   been changed.
2. Select and approve a transactional email provider within the $0 constraint,
   configure its credentials outside Git, and verify delivery, retries, and
   sender-domain authentication. SMTP support is implemented but unconfigured.
3. Move scanning to a separate isolated worker with independent egress
   restrictions, quotas, durable queue, and a rehearsed abuse/rollback path.
   The local database records failed requests, attempts, and reasons, and lets
   a reviewer return an eligible failure to the queue. This is not a production
   dead-letter service or provider-outage recovery flow. Connection pinning in
   this local adapter is one control, not a substitute for that isolation.
4. Approve data retention, export field scope and identity proof, implement
   deletion across primary data and backups, and rehearse encryption-key
   rotation with a verified backup, plus restore, incident response, support
   ownership, and alerting.
5. Provide approved privacy/terms wording, business/support details, initial
   named administrator/reviewer accounts, audience and onboarding decisions.
6. Complete full role/tenant, SSRF/resource-abuse, accessibility, dependency,
   load, migration, backup/restore, and staging rollback verification.
7. Refresh provider console, DNS, current release, and rollback evidence. A
   read-only Vercel project/deployment inventory and public DNS/HTTP spot check
   are now recorded below; project settings, billing/environment details,
   Cloudflare zone settings, and rollback configuration remain unverified.

## Domain boundary

The PostgreSQL test is a fake-connection adapter check only; it does not cover a
live server, migrations, concurrent workers, backup, or restore. The selected
web runtime has a lockfile and scoped package audit; the optional all-extras AI
profile has the `diskcache` advisory described above. Vercel's official
documentation describes FastAPI support but identifies the Python runtime as
Beta. That is a staging evaluation target, not a production-readiness claim.

The production `.com` cutover has not been performed. No DNS record or Vercel
domain assignment was changed. `.shop` is outside the worktree changes and has
not been changed. The current local app is not connected to either live domain.
The plan's owner-authorized `.com` cutover can proceed only after the release
gates above pass and the live target and rollback values are freshly confirmed.

## Phase G continuation — enlarged-text reflow repair (2026-09-28)

At a 320px CSS width, a 200% computed-text-size simulation exposed overflow in
the public navigation, home-page headings and call to action, the authentication
card, and the sample-report heading. The small-screen navigation, report rows,
authentication card, and mobile headings now reflow without page-level
horizontal overflow. The opt-in Chromium walkthrough checks `/`, `/register`,
`/login`, `/forgot-password`, and `/sample-report` at 320px while doubling each
body element's computed font size. It also tabs through focusable controls on
those pages, the customer overview/sites/site-detail routes, and the
administrator overview/audit-detail routes, comparing keyboard focus with the
visible controls and table scroll region. Rendered text contrast is measured on
the same routes by compositing transparent CSS backgrounds and applying 4.5:1
for normal text or 3:1 for large text.

Verification on 2026-09-28: the local customer/admin browser walkthrough with
the five-page no-horizontal-overflow check and focus-sequence traversal passed
(**1 passed**). The full local
`toolkit_tests` suite passed (**230 passed, 5 opt-in browser tests skipped, 3
upstream deprecation warnings** in 84.89 seconds), and Ruff passed on the
changed browser test. The latest focused browser pass also measured rendered
text contrast on those public/account and authenticated customer/admin routes;
no text pair fell below the normal or large-text threshold. A source-palette
spot-check found low contrast on the focus outline and green step/check
numerals. The outline and numerals were darkened; selected text pairs now
measure at least 4.72:1, the large step number at 3.52:1, and the focus outline
at 3.04:1 on the dark banner, 3.23:1 on the proof strip, and 3.52:1 on the page
background. The browser check asserts the focus outline color after keyboard
navigation.

The font-size check doubles computed sizes in CSS. It does not establish browser
zoom behavior, cover every form of text clipping, provide human screen-reader
operation, or establish WCAG conformance. A human keyboard/screen-reader review
and complete non-text contrast review remain open. The rendered scan does not
include input placeholder rendering or non-text component boundaries. No soak
test was run, per user instruction; soak evidence is unavailable and is not
marked as passing.

## Phase F continuation — per-account login throttle (2026-09-28)

Failed password and privileged-account OTP attempts now increment a
database-backed bucket keyed by a hash of the normalized login address. Twelve
failures within one hour are limited across client addresses and app restarts;
successful sign-in clears the account bucket. The existing eight-per-minute
client-address limit remains. The threshold is provisional and can create a
temporary account lockout after distributed failures, so owner approval is
still required before production. Live PostgreSQL concurrency and deployed
client-IP handling are unverified.

Verification after this change: from the repository root,
`rtk .venv/bin/python -m pytest -q toolkit_tests` completed with **234 passed,
5 opt-in browser tests skipped, 2 upstream
deprecation warnings** in 49.75 seconds. The focused account-throttle test
passed, including cross-address failures, app recreation, hashed storage, and
successful-login clearing. Ruff passed for changed Python files, and
`git diff --check` passed. No soak test was run.

The opt-in local customer/admin Chromium walkthrough also passed separately
after loading the pinned `browser` extra: `1 passed` in 25.70 seconds. It uses
synthetic accounts and disposable local data. The browser exercise is not a
human screen-reader review, full WCAG assessment, production staging rehearsal,
or soak test.

## Phase F continuation — local administrator key rotation (2026-09-28)

Added a dry-run-first `catalyx-totp-key-rotate` command. It accepts old and new
32-byte keys from environment variables, validates all stored seed envelopes,
and by default reports counts without changing data. `--apply` re-encrypts
seeds in a single transaction using compare-and-set updates; it accepts
already-new envelopes for safe retry and aborts if a seed matches neither key
or changes during rotation. The command prints counts only.

Synthetic local SQLite verification passed: dry run preserved the old
envelopes; apply re-encrypted both test seeds; the new key decrypted them; a
repeated validation recognized already-current envelopes; and a wrong-key
attempt made no changes. The CLI dry-run and apply path passed with synthetic
keys and did not print either key. Three focused tests passed and Ruff passed.
This does not prove PostgreSQL locking, backup restore, secret-manager
coordination, production key rollout, or lost-key recovery. Keep those release
gates open. No soak test was run.

Final finite checks after the rotation implementation: full `toolkit_tests`
reported **238 passed, 5 opt-in browser tests skipped, 2 upstream deprecation
warnings** in 88.33 seconds. Ruff and `git diff --check` passed.
`uv build --sdist --wheel` produced both distributions; inspection confirmed the
wheel contains the rotation module and `catalyx-totp-key-rotate` console entry
point. Setuptools reports the existing deprecated TOML license metadata; the
build still succeeds. A follow-up regression test confirms that a missing local
database path is rejected before the rotation command creates a file. No soak
test was run. The wheel was rebuilt after that safeguard; inspection confirmed
the missing-file guard and console entry point are present in the wheel.

## Phase 4 continuation — Money Machine runtime isolation (2026-09-28)

The ASGI runtime factory now fails before app/database initialization if the
process has already loaded `mm_transport`, `mm_model_router`, or `mm_approval`.
The general `create_app` factory remains available for isolated test fixtures;
the module-level ASGI app uses the guarded runtime factory. A parameterized
regression test injects each forbidden module name and confirms startup fails
before the database file is created. This is an in-process startup assertion,
not an OS/container boundary, and it does not replace independent worker
isolation or egress controls.

Verification after the guard: full `toolkit_tests` completed with **241 passed,
5 opt-in browser tests skipped, and 2 upstream deprecation warnings** in 68.33
seconds. The opt-in Catalyx customer/admin browser walkthrough passed (**1
passed**); Ruff and `uv lock --check --offline` passed. The three startup-guard
regressions passed with the public readiness test (**4 passed**). No soak test
was run.

An additional full-suite rerun against the current checkout completed with **241
passed, 5 opt-in browser tests skipped, and 2 upstream deprecation warnings** in
58.64 seconds. Ruff passed for the changed app/security/test files, and
`git diff --check` passed. No soak test was run.

## Phase F continuation — independent source review and follow-up (2026-09-28)

Codex Security completed an offline Standard review of all 14 files in
`catalyx_web` at base revision `f9e0694582c4cada39a08c91f86a4adaf083feff`
(scan `291b76ca-52d2-41ce-9ce0-84afeb5fd795`). It reported two medium findings
and one low finding. The low finding was the non-atomic account login rate
check/increment sequence. The working tree now reserves the hashed account
attempt atomically before credential verification and clears the bucket after
successful login. The account-lockout finding remains open: distributed login
failures can trigger the configured one-hour account lockout. The email-churn
finding is mitigated in source by hashed account-level five-per-hour caps for
verification resend and reset email, in addition to per-IP limits. The
thresholds and recovery behavior still need owner approval before hosted SMTP
is enabled. The report marks coverage
partial because runtime and deployment behavior are unverified; its
historical deferred-candidate rows are stale after final validation.

Verification after the rate-limit change: full `toolkit_tests` completed with
**242 passed, 5 opt-in browser tests skipped, and 2 upstream deprecation
warnings** in 55.56 seconds. The new concurrency regression confirms exactly
12 of 32 simultaneous reservations are accepted across local SQLite
connections. Ruff and `git diff --check` passed. The opt-in Catalyx Chromium
walkthrough separately passed (**1 passed**), checking the synthetic
customer/admin flow, keyboard focus order, text contrast, narrow viewport
layout, and simulated 200% text sizing. It is not a screen-reader test or a
human WCAG 2.2 AA assessment. No soak test was run.

The account-lockout finding, approval of provisional auth-email thresholds,
hosted PostgreSQL behavior, independent worker isolation, production provider
configuration, privacy/retention/backup/restore,
manual screen-reader review, legal/support ownership, staging and rollback,
and fresh Vercel/Cloudflare/domain evidence remain release gates. No production
or DNS change was made; `.shop` remains outside the cutover scope.

## Money Machine FSM mapping proposal (2026-09-28 NZDT)

A privacy-minimizing, reviewable Phase 5 mapping proposal is in
[`money-machine-fsm-mapping-proposal.md`](money-machine-fsm-mapping-proposal.md).
It keeps customer authorization, release, and deletion authority in Catalyx;
proposes an idempotent event outbox into the separate Money Machine queue; and
blocks any automatic transition into commercial qualification or outreach.
The bridge remains unimplemented and disabled pending owner approval of the
authority split, event fields, retention/deletion, and `quality_review` versus
`released` mapping. It requires a synthetic dry run before customer data is used.

## Public domain spot check (2026-09-28 NZDT)

Read-only requests to `https://catalyxlabs.com/` and
`https://www.catalyxlabs.com/` returned HTTP 200. Both public hostnames resolved
to the same Cloudflare anycast A records at the check time; both responses
identified Cloudflare, and the apex response carried a Vercel `syd1` request
identifier. The rendered homepage is still the Grow OS site, not the Auditor.
This confirms the current public response only. Provider deployment aliases
are recorded in the inventory section below; Cloudflare dashboard settings and
rollback configuration remain unverified. No configuration was changed, and
`.shop` was not queried by the public HTTP check.

At 05:24 NZDT, the local preview health endpoint returned `200` with
`environment=staging` and `scan_worker=disabled`; an unauthenticated request
to `/api/v1/me` returned `401`. This is a point-in-time local smoke check, not
staging deployment or soak evidence.

## Finite verification refresh (2026-09-28 NZDT)

The current worktree's full `toolkit_tests` run completed with **242 passed,
5 opt-in browser tests skipped, and 2 upstream deprecation warnings** in 44.65
seconds. Ruff passed for `catalyx_web` and `toolkit_tests/test_catalyx_web.py`;
`uv lock --check --offline` and `git diff --check` passed. This validates the
local source/test scope only. The separately recorded Catalyx browser test
remains the latest browser evidence; this run did not include it. No soak test
was run.

The opt-in Catalyx customer/admin Chromium journey was then rerun at 06:28
NZDT: **1 passed** in 11.86 seconds against disposable local data. This refreshes
the browser-flow evidence for the current worktree; it is not a deployed
staging, screen-reader, or production accessibility assessment. No soak test
was run.

## Provider inventory refresh (2026-09-28 NZDT, read-only)

The connected Vercel account lists a `website_auditor` project and a separate
`catalyx-labs-grow-os` project. The latest inspected READY production
deployment for Grow OS (`dpl_91P8UftmD6puNa1D779wPvQmJWFb`) carries aliases for
`catalyxlabs.com`, `www.catalyxlabs.com`, `catalyxlabs.shop`, and
`www.catalyxlabs.shop`. This matches the public Grow OS homepage and confirms
the current `.com` and `.shop` aliases remain on the Grow OS deployment.
The newest observed production-target Grow OS deployment attempt, created
2026-08-25 from `main`, is `BLOCKED` with a Vercel account-configuration error;
the older READY deployment still carries the live aliases.

The inspected READY production deployment for `website_auditor`
(`dpl_FxGvWB8iPMWwzgKfjBT9nFysKHMn`) is based on the older
`WEBSITE-AUDITOR` `master` commit `9c4d30e3`; its deployment aliases are only
Vercel hostnames, with no `.com` alias. A newer READY preview deployment
(`dpl_22uDe8Xpwo8HFgq2L3onwNpTFvWV`) is built from current branch commit
`2c3b4f08` and has only Vercel hostnames. The deployment overview labels its
environment `Preview` and says custom-domain assignment was skipped. These
deployments do not put the current rebuild on `.com`.
The inspected READY production deployments report runtime region `iad1`; this
does not select or prove the region of any future Auditor customer database.

The Vercel dashboard labels the account `Hobby`. Direct unauthenticated HTTP
requests to the preview's `/` and `/api/health` returned `302` redirects to
Vercel SSO; browser visits to its deployment and branch hostnames returned
Vercel `404 NOT_FOUND`. Therefore the READY state proves build/deployment
creation only, not app-route correctness or runtime health. The preview remains
unverified without an authorized SSO access path.

Cloudflare read-only inventory found one Worker in one accessible account and
none in the other; neither account lists a D1 database. The Worker inventory
does not establish whether that existing Worker is relevant to another
application. The available connector did not expose DNS-zone settings, and its
project-detail lookup rejected the documented parameter shape. Therefore
Vercel project environment details and Cloudflare zone, plan, security, and
rollback settings remain open. No project, Worker, database,
environment variable, DNS, deployment, or `.shop` setting was changed.

## Authentication email abuse control (2026-09-28 NZDT)

The independent review's email-churn finding is mitigated in source by
account-scoped hashed limits on verification-resend and password-reset email
requests. Each request consumes both the per-client limit and a five-per-hour
account bucket, so rotating client addresses cannot bypass the account cap.
Responses remain neutral for unknown and throttled accounts. A regression test
submits each operation through six distinct client IPs and confirms only five
messages and one current token are retained per account. The five-per-hour
values are provisional and require owner approval before hosted SMTP is enabled.

Verification after this change: full `toolkit_tests` completed with **243
passed, 5 opt-in browser tests skipped, and 2 upstream deprecation warnings**
in 58.31 seconds. The focused abuse-control regression passed; Ruff and
`git diff --check` passed. No environment file or SMTP credentials were loaded,
and no message was sent outside the private local mailbox. No soak test was run.

## Finite verification refresh at current branch tip (2026-09-28 NZDT)

At `2c3b4f08`, a fresh full `toolkit_tests` run completed with **243 passed,
5 opt-in browser tests skipped, and 2 upstream deprecation warnings** in 50.33
seconds. Ruff passed for `catalyx_web` and `toolkit_tests/test_catalyx_web.py`;
`uv lock --check --offline` passed. The dedicated Catalyx customer/admin
Chromium journey then passed (**1 passed** in 13.12 seconds) against disposable
local data. `git diff --check` passed. The Vercel branch preview is READY but
still SSO-protected, so these local results do not verify its app routes or
production-like configuration. No soak test was run.

## Hosted account-mail default and explicit send gate (2026-09-28 NZDT)

Hosted runtime now defaults account mail to `disabled`. SMTP startup and the
direct mailer both require `CATALYX_EXTERNAL_SEND_ALLOWED=true` in addition to
`CATALYX_MAIL_MODE=smtp`; open registration is rejected when mail is disabled.
The example environment sets the send flag to false. Local mailbox mode remains
available for development and staging. No SMTP credentials were loaded and no
external message was sent.

Verification at the implementation branch tip: full `toolkit_tests` completed
with **247 passed, 5 opt-in browser tests skipped, and 2 upstream deprecation
warnings** in 45.10 seconds. Focused mail and web tests passed (**86 passed**);
Ruff, offline lock validation, `git diff --check`, and scoped Gitleaks scans of
application, tests, and Catalyx platform documentation passed. No soak test
was run.

## 2026-09-28 continuation — current source security review

Codex Security completed Standard scan
`50ab6ee6-819d-4818-b25b-eb4fb31f76a9` for the 14-file `catalyx_web` scope at
target revision `5519c4da5768dfc27293367db9ef751c6b989666`. It reported one
medium-severity account lockout issue and two low-severity recovery issues:
recovery-token replacement before mail delivery, and unbounded per-subject
throttle state. It found no issue in the reviewed tenant/report/session/worker
and egress surfaces. The completed scan's generated report retains three stale
deferred-candidate follow-up rows from earlier checkpoints and marks coverage
partial; those rows duplicate or overlap the three validated findings. Treat
the final finding list as the validated result and do not treat those follow-up
rows as additional findings.

The repository advanced during the scan to
`eb9f262e231934a5c47b009c411c8e173edbd00c`. The only `catalyx_web` changes
since the scan target were the hosted account-mail default and explicit-send
guard in `app.py` and `mailer.py`. A source diff review confirmed hosted mail
now defaults to disabled, SMTP requires
`CATALYX_EXTERNAL_SEND_ALLOWED=true`, and the direct mailer enforces the same
flag. This lowers exposure to the token-delivery finding until an operator
explicitly enables SMTP; it does not remove that conditional failure path. The
login cap and recovery throttle behavior remain present. Current line anchors
are `app.py:1065-1072` for login throttling, `app.py:989-1005` for
resend-token replacement, `app.py:1122-1129` for reset throttling, and
`db.py:193-221,338-346` for persistent rate state. The sealed scan did not run
against the latest commit, so this delta review is recorded separately.

The verified code change and prior account-mail tests are local source
evidence only. Production SMTP/provider controls, hosted database behavior,
edge limits, worker isolation, and other deployment settings remain
unverified. No source was changed in this continuation. No soak test was run.

Phase A and the production no-go remain open. The owner must approve the login
and recovery limits, first-release scope, production host and data region/cost,
privacy and retention policy, and named operators before staging or cutover.
`.com` remains on the existing Grow OS site and `.shop` remains outside scope.

## 2026-09-28 continuation — live provider and public-route recheck

At approximately 07:22 NZDT, read-only Vercel inventory showed the latest
`website_auditor` deployment `dpl_GyQxF71pDYXLm6Bn6A1m2wgNoJPm` as READY for
the current branch commit `eb9f262e231934a5c47b009c411c8e173edbd00c`. Its
target is preview and its only alias is a Vercel hostname. The inspected
production-target `website_auditor` deployment remains READY on the older
`master` commit `773c9828d3884783c7345144b388bb1912d55f15`, with only Vercel
hostname aliases. The Vercel project-detail connector call remains unavailable
because its declared and backend parameter schemas disagree; deployment
metadata did not expose project environment values.

Cloudflare read-only inventory showed one Worker named
`nz-revenue-leak-snapshot` in one account and no Workers in the other; neither
account listed a D1 database. The available connector still did not expose DNS
zone records. Current public fetches of the `.com` apex and `www` homepage
render the Grow OS site. These observations do not establish DNS rollback
values, project environment settings, or any staging app-route health. No
provider setting, resource, deployment, DNS assignment, or `.shop` route was
changed.

The current preview is not the reviewed release: there is no isolated staging
rehearsal, approved production architecture, migration/restore proof, or
release record. Keep the production no-go and `.com` cutover gate closed.

The Phase B hosting assessment was refreshed against current official provider
documentation on 2026-09-28. Cloudflare Workers Free remains limited to 100,000
requests/day and 10 ms CPU/request; D1's 5 million rows read/day and 100,000
rows written/day limits are enforced and queries fail after quota exhaustion;
Queues Free retains messages for 24 hours and includes 10,000 operations/day.
The $5/month Workers Paid tier conflicts with the recorded NZ$0 ceiling.
Vercel Hobby still restricts use to personal/non-commercial projects. These
facts leave no approved production host under current constraints; see
`hosting-cost-and-terms-assessment.md` for source links and implementation
limits.

## 2026-09-28 continuation — recovery delivery and throttle write hardening

The current local worktree changes recovery-token replacement so older
verification/reset links remain stored until a replacement is saved to the
local mailbox or the SMTP send call returns successfully. Failed SMTP delivery leaves the
old link usable; successful verification clears all outstanding verification
tokens for that user. Successful reset already clears all outstanding reset
tokens. Both recovery routes now avoid account-bucket writes for requests
rejected by their IP cap, when mail is disabled, or when the normalized email
is invalid or longer than 254 characters.

These changes mitigate the token-loss finding for synchronous SMTP errors and
the recovery-bucket write on IP-denied or malformed requests. A successful SMTP
handoff does not prove inbox delivery; later bounce behavior remains unverified.
The rate-limit table still has no global row
cap, so varied valid email addresses across many source IPs remain an
operational resource risk until A10 quotas/edge limits are chosen. The
account-wide login lockout finding also remains open pending owner disposition
of the 12-per-hour login cap.

Finite verification on the current uncommitted worktree: full `toolkit_tests`
**249 passed, 5 opt-in browser tests skipped, 2 upstream deprecation warnings**
in 54.60 seconds; the dedicated Catalyx Chromium journey **1 passed** in 12.60
seconds; Ruff passed; `uv lock --check --offline` passed; `git diff --check`
passed. Tests use disposable local SQLite and synthetic accounts; PostgreSQL
and hosted provider behavior remain unverified. No soak test was run.

No source commit, deployment, DNS change, external email, or customer-data
transfer was made. The tracked worktree contains the local app/test/readiness
changes; untracked `experiments/` remains untouched.

## DNS observation refresh (2026-09-28 07:35 NZDT)

Read-only resolver queries for `catalyxlabs.com` and `www.catalyxlabs.com`
returned matching Cloudflare proxy A records (`172.67.211.245`,
`104.21.67.38`) and AAAA records (`2606:4700:3035::ac43:d3f5`,
`2606:4700:3031::6815:4326`). The apex NS answers were
`candy.ns.cloudflare.com` and `fonzie.ns.cloudflare.com`. These observations
do not expose authoritative DNS configuration, origin, TLS mode, or rollback
values. No `.shop` lookup or DNS/provider change was made. Public HTTP fetches
still render Grow OS on both `.com` routes. The provider quota and commercial
use review remains in `hosting-cost-and-terms-assessment.md`; under the
NZ$0 constraint it has not identified an approved production stack.

The local recovery improvements and finite verification documented above
remain uncommitted on top of `eb9f262e231934a5c47b009c411c8e173edbd00c`.
Login rate thresholds/production abuse policy and A1–A10 owner decisions
remain open.
No soak test was run; staging, deployment, and `.com` cutover remain no-go.

## Current security continuation (2026-09-28)

A further Codex Security Standard scan (`539d2990-1d7b-4d3f-ab92-40d9e6e4f2f8`)
reviewed the 14-file `catalyx_web` source snapshot with digest
`codex-security-snapshot/v1:sha256:038d5ae07ab56f77bfe866b52be1145fc523e34ec7d15676f5d826bfabd973b4`.
It confirmed two findings: **medium, accepted privileged TOTP codes can be
replayed within the verifier's ±1-step window**, and **low, unauthenticated
callers can exhaust the target email's five-per-hour password-reset or
verification quota before account lookup**. The latter remains open. Keep
hosted mail disabled until the owner approves the provider and a recovery flow
that does not let unauthenticated callers lock the account holder out.

The TOTP replay finding has since been mitigated in the current local source.
The verifier now returns its matched time-step counter; login atomically stores
and rejects already accepted counters per membership; SQLite and PostgreSQL
schema migration adds `totp_last_step` as schema version 6. This update is
uncommitted and postdates the scan, so it is not part of that sealed report and
has not received a new independent scan. PostgreSQL migration execution remains
unverified.

Finite verification after this change: full `toolkit_tests` **251 passed, 5
opt-in browser tests skipped, 2 upstream deprecation warnings** in 48.65
seconds; focused TOTP/schema tests **4 passed**; Catalyx Chromium journey **1
passed** in 10.67 seconds; Ruff, offline lock check, and `git diff --check`
passed. No soak test was run.

The scan report is available, but its formal coverage is marked **partial**:
the workbench rejected six supplemental receipt references because they were
outside the scan directory and changed those coverage surfaces to
`needs_follow_up`. The scan progress had all 14 files closed, and the source
inventory lists all 14, but the sealed coverage record should be treated as
partial. The repository HEAD also changed during the scan; results are bound
to the snapshot digest above and not asserted as a scan of the current modified
checkout.

Phase F remains open because the target-email recovery quotas need a safe
owner-approved delivery design and the current post-scan TOTP mitigation needs
independent review. A1–A10, deployed staging, operations rehearsal, and all
production/cutover gates remain unresolved. `.com` and `.shop` were not changed;
no production mail or customer data was used.

## Phase G continuation — semantic accessibility sweep (2026-09-28)

Extended the opt-in Chromium walkthrough with a rendered-DOM structural check
for page title and language, a single main landmark and H1, skipped heading
levels, accessible names on visible links/buttons/form controls, and missing
image alternatives. It covers the public registration/sign-in/recovery/sample
pages plus the synthetic customer request and administrator decision/status
pages. The same walkthrough checks tab order, skip-link behavior, text
contrast, and 320px reflow with doubled computed text; the updated pass was
**1 passed** in 13.80 seconds. Ruff and `git diff --check` also passed.

This is a project-local browser check, not a full WCAG audit or human
screen-reader session. No local axe-core or Lighthouse executable was
available. Actual browser zoom, assistive-technology operation, target-size
exceptions, and non-text contrast still need review. Do not claim WCAG 2.2 AA
conformance from this evidence. No soak test was run.

## Login lockout mitigation and current finite verification (2026-09-28)

The account-keyed login bucket now counts failed credential attempts after
password and required TOTP validation. A valid sign-in bypasses the bucket and
clears it, so an attacker cannot exhaust this per-account counter to reject
the account holder's correct credentials. Invalid attempts still receive a
429 after the provisional 12-per-hour cap. The existing IP bucket remains
8-per-minute. This mitigates the account-lockout behavior from the sealed
security scan in local source; the scan itself predates this uncommitted
change. Threshold approval, proxy/IP semantics, broader edge controls, and
independent current-revision security review remain open.

The source-derived `data-map.md` was corrected to describe both login
buckets. Customer and privileged-account regressions passed (**2 passed**);
the full `toolkit_tests` suite passed (**250 passed, 5 opt-in browser tests
skipped, 2 upstream deprecation warnings** in 53.50 seconds); and the
dedicated Catalyx browser journey passed (**1 passed** in 11.67 seconds).
`ruff check catalyx_web toolkit_tests`, offline lock validation, and
`git diff --check` passed after fixing three existing Ruff findings in two
test files. Tests used synthetic accounts and local SQLite; hosted PostgreSQL
and edge/provider behavior remain unverified. No soak test was run.

## Phase F continuation — refreshed source security scan (2026-09-28)

Codex Security Standard scan `0163e31e-d6e5-41bb-bf96-87589ed4e3c8` completed
against the scoped `catalyx_web` source snapshot
`codex-security-snapshot/v1:sha256:de7940b5d7132e59fdc33bbc469a162e61179983c091d699c16b8bdd015ef55d`.
All 14 in-scope files were reviewed. The scan recorded complete source coverage,
four high-confidence findings (three medium, one low), and explicit exclusions
for production runtime/provider configuration/customer data and soak testing.

Findings:

- **Medium — worker execution can exceed the audit deadline.** DNS answers are
  attempted serially with a fresh connection timeout; the overall profile
  deadline is checked between requests. The manual worker's lease is 60 seconds.
  The web app disables this worker, so production reachability was not established.
- **Medium — open registration has no shared verification-mail budget.** A
  per-address limit does not cap messages to distinct destinations. The path
  requires open registration and explicitly enabled SMTP; hosted email remains
  disabled by default.
- **Medium — distributed login traffic can cause repeated PBKDF2 work.** The
  per-account failure limit is applied after the password hash operation; the
  pre-hash limit is keyed by source address. Production edge controls were not
  reviewed.
- **Low — public recovery requests can temporarily exhaust a target email's
  request quota.** Reset and resend handlers consume the target-address bucket
  before account lookup. This delays recovery only and cannot change credentials.

The scan found no current TOTP replay issue: the committed source consumes the
matched counter atomically per membership. The source review also found no
tenant/report authorization issue in the reviewed paths. This is a static code
review; it does not close runtime, PostgreSQL, isolated-worker, legal/privacy,
mail-provider, or accessibility signoff gates. The repository HEAD advanced to
`5fd497f3` during the scan; its immutable source digest is retained in the
report, and the TOTP source change is included in that reviewed snapshot.

No soak test was run. No external email, paid resource, provider/domain change,
customer data import, deployment, or production cutover occurred. Keep hosted
mail disabled and release no-go until the owner decisions and mitigations listed
in the security report are resolved.

## Phase F continuation — egress deadline mitigation (2026-09-28)

After the scan, the local worker transport was changed to share the fixed
profile's absolute monotonic deadline across DNS, connect, TLS, and response
operations. DNS results are rejected when more than four public addresses are
returned, and an already-expired deadline prevents DNS/socket work. The browser
app still keeps the worker disabled; this source change does not authorize
worker execution or production scanning.

Focused regression coverage passed (**3 passed, 60 deselected**), including
answer-count rejection, expired-deadline rejection, and normal pinned transport
behavior. Ruff and `git diff --check` passed. The sealed scan predates this
local patch, so it continues to report the source finding against its immutable
snapshot. A current-source review remains required before any release.

No soak test, network target, production runtime, customer data, provider, or
domain configuration was accessed.

## Refreshed current-source review and deadline fix (2026-09-28)

Codex Security Standard scan `d85dfc47-f85a-4bc6-9e2c-1aa1d1a15569` reviewed
all 14 files in `catalyx_web` at immutable snapshot
`codex-security-snapshot/v1:sha256:690ac9d1ab6e1cb5a60b9f400fbeaf62881177346614d6fdb62bc74fab3445b5`.
It completed with five validated findings: two medium (distributed login
PBKDF2 work; unbounded verification-mail volume if registration and SMTP are
enabled) and three low (slow-drip response headers exceed the audit deadline;
registration response enumeration; recovery requests consume a target address
quota before account lookup). Hosted registration and mail remain closed or
disabled by default. Tenant/report authorization and atomic TOTP replay
prevention had no additional validated finding. The sealed report is
`/Users/dd/.codex/state/plugins/codex-security/scans/catalyx-auditor-rebuild/5fd497f3f78562d498d90af7a56b78dc56c6f681_20260927T194449Z_jq9s2b_4/report.md`.

The scan's formal coverage is **partial**: all 14 source files were reviewed
and all six surfaces were dispositioned, but one duplicate registration
enumeration candidate remained deferred and the hosted mail/login/recovery
policy question remains open. The findings apply to the recorded snapshot,
which was captured before the following parser change.

The pinned transport now parses response status and headers through a reader
that checks cancellation and the remaining monotonic deadline before every
socket read. It also enforces a 32 KiB aggregate status/header bound while
bytes arrive. This closes the slow-drip header gap in current local source;
the sealed report remains unchanged. Regression tests cover one-byte
slow-drip reads against a finite deadline and an oversized header rejected
during reading.

Current finite verification: focused transport checks **22 passed**; full
`toolkit_tests` **255 passed, 5 opt-in browser tests skipped, 2 upstream
deprecation warnings** in 46.88 seconds; Ruff and `git diff --check` passed.
The skipped browser checks were not soak tests. No soak test was run, per the
owner's instruction. This does not verify real socket behavior against a
deployed worker, PostgreSQL, provider settings, or production egress controls.

The login work budget, registration email quotas, recovery quota design, and
remaining A1–A10 decisions are still open. Production and `.com` cutover remain
no-go; worker execution and external mail remain disabled pending their gates.

## Egress diff review and final parser refinement (2026-09-28)

Codex Security diff scan `47a4e2f4-4709-4287-88b6-33c7bc480d7a` reviewed the
working-tree diff snapshot
`codex-security-snapshot/v1:sha256:c22ee604622143d4d570dba60aa390eddb020b37cd76e2cd78af2f7ea6248ffa`.
It found no new issue in the two changed `catalyx_web` source files and their
related regression test. Coverage is formally partial because the inventory
also contained 279 untracked user-owned files under `experiments/`; their
contents were not opened. The sealed report is
`/Users/dd/.codex/state/plugins/codex-security/scans/catalyx-auditor-rebuild/5fd497f3f78562d498d90af7a56b78dc56c6f681_20260927T200957Z_lht8yfzz/report.md`.

After that snapshot, the local reader was refined to continue enforcing the
header bound after interim `100 Continue` responses. A regression test covers
an oversized final header following an interim response. Final finite checks
passed: **22 focused transport tests** and **255 full toolkit tests**, with 5
opt-in browser checks skipped and 2 upstream deprecation warnings; Ruff and
`git diff --check` passed. The sealed diff scan does not include that small
post-snapshot refinement.

No soak test was run. The worker remains disabled in the web app and local-only
in the CLI. Production, provider/DNS, customer-data, and real worker-network
behavior remain outside the evidence. Production and `.com` cutover remain
no-go pending the remaining security findings and A1–A10 owner decisions.

## Registration response enumeration follow-up (2026-09-28)

The registration handler now returns the same generic page and HTTP 200 status
after either successful account creation or a duplicate-address conflict. A
regression test asserts byte-for-byte response-body equality, one verification
message for the first registration only, and successful verification using
that original link. The full toolkit suite passed (**256 passed, 5 opt-in
browser checks skipped, 2 deprecation warnings** in 48.85 seconds); the focused
regression passed. The dedicated local Chromium customer-to-admin walkthrough
also passed (**1 passed** in 10.46 seconds) after its registration-page
assertion was updated for the generic response. Ruff and `git diff --check`
passed.

An independent source review confirmed visible response parity and identified
a residual timing channel: the new-account path creates a token and saves or
sends mail before responding, while the duplicate path returns after the
database conflict. The change closes the response-content disclosure; it does
not establish timing indistinguishability. Registration and external mail
remain closed/disabled by default, and recipient/global mail quotas and
owner-approved abuse thresholds remain open. No soak test, external mail,
deployment, provider/domain change, worker run, or customer-data access
occurred.

The Chromium walkthrough checks keyboard traversal, labels, structure, text
contrast, and narrow/reflow layouts against disposable synthetic data. It is
not a screen-reader session or a human WCAG conformance sign-off; those
accessibility gates remain open.

## Login cost and local mailbox hardening (2026-09-28)

The refreshed baseline identified two source issues in its immutable snapshot:
login performed PBKDF2 before consuming the shared account bucket, and the
local mailbox followed a pre-existing symlink. The local working tree now
reserves the per-account login attempt before password verification, rejects
passwords over the existing 1,024-character account-creation limit before
PBKDF2, and uses no-follow file operations for the mailbox. Mailbox reads and
writes require a regular file owned by the current user; reads are capped at
1 MB and writes set mode `0600` before truncating or writing.

Targeted regression checks passed (**98 passed** across the Catalyx mail and
web suites): exhausted account throttling, rejection of an overlong password
before the verifier, preservation of a symlink target, and SMTP budget
partitioning. The first run used system Python and could not collect because
its dependencies were incomplete; the repository Python 3.11 environment
supplied the successful run.

The account bucket protects repeated attempts against one normalized address,
but a distributed attacker can vary addresses. Exhausting the bucket can
temporarily block its legitimate owner until expiry. Overall authentication
budget, thresholds, client-IP policy, and lockout behavior remain owner
decisions. These changes postdate the immutable security-scan snapshot and do
not alter its findings. Mailbox hardening does not establish safety for
untrusted parent-directory permissions on every host platform.

The current worktree adds persistent SMTP hourly budgets by purpose: 30
registrations, 30 verification resends, and 40 password resets. Separate
scopes reserve recovery capacity if signup traffic spikes; the combined maximum
is 100 SMTP attempts per hour. Each purpose can still be exhausted within its
own window, and final production thresholds remain a release configuration
decision. These limits apply only when SMTP and the explicit external-send flag
are both enabled; local mailbox and disabled-mail modes do not consume them.
The independent security review found no bypass or token-lifecycle regression.
It confirmed that a caller can still exhaust a single purpose budget and defer
that purpose's legitimate delivery until the next hour; this residual limit is
an explicit consequence of bounded delivery.

The complete finite `toolkit_tests` suite passed (**259 passed, 5 opt-in
browser skips, 3 upstream deprecation warnings**) on 2026-09-28. Scoped Ruff
and `git diff --check` passed. No soak test was run.

No soak test was run. No worker, live mail, customer data, provider, DNS, or
production environment was accessed.
