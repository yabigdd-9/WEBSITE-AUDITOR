# CatalyxLabs Website Auditor release readiness

- **Status date:** 2026-09-28
- **Implementation base:** `f9e0694582c4cada39a08c91f86a4adaf083feff`
- **Current repository revision:** `47a35243c4cd242f9361466487a3fbcb3469e9fc` on
  `codex/catalyx-rebuild-phase1-5` (checked 2026-09-28)
- **Original app implementation revision:** `ed182a76daab33622a27665596fc7654342b16ef`
- **Worktree follow-up:** atomic login and account-recovery email rate limits,
  cross-IP regression coverage, and threat-model/readiness updates are committed
  through `47a35243`; untracked `experiments/` is preserved.
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
  per-normalized-email bucket (12 attempts/hour), with successful sign-in
  clearing the bucket. Owner approval is still required for thresholds and
  lockout behavior. Schema version 4 adds the shared buckets;
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
(`dpl_EthVqWjyS2sHHAGt5UfeaSmEYQC5`) is built from current branch commit
`6d147eba` and has only Vercel hostnames. The deployment overview labels its
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
