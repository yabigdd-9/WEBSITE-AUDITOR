# Catalyx Phase 6 acceptance evidence

> Historical acceptance document. See the current-HEAD continuation at the
> end; the original header revision below is not the current source revision.

**Revision:** `b1bf406e113deee6239ef07e5ad44988ca3ffde3`  
**Run date:** 2026-09-28  
**Environment:** local Python 3.11.16, synthetic accounts and disposable SQLite
databases; no production data, outbound SMTP, model provider, or public site.

## Automated results

| Check | Command | Result |
| --- | --- | --- |
| Catalyx web and security integration suite | `.venv/bin/python -m pytest -q toolkit_tests/test_catalyx_web.py` | 68 passed; one upstream Starlette/httpx deprecation warning |
| Customer-to-admin browser journey and accessibility sweep | `WA_CATALYX_WEB_BROWSER_E2E=1 .venv/bin/python -m pytest -q toolkit_tests/test_catalyx_web_browser_e2e.py` | 1 passed in 15.79 seconds |
| Link crawl | `lychee --no-progress --verbose http://127.0.0.1:4174/` | 17 total links checked, 11 unique, zero errors |
| Lighthouse mobile lab runs | Lighthouse 13.5.0 with Chrome for Testing 153.0.8010.12; serial runs against the loopback preview | Eight routes scored 100 for accessibility, best practices, and SEO; performance scored 99–100. LCP was 0.92–1.06 s, CLS 0, TBT 0–104 ms. |

Pages measured: `/`, `/how-it-works`, `/what-we-check`, `/security-and-privacy`,
`/pricing`, `/sample-report`, `/privacy`, and `/terms`. The `/privacy` draft
scored 99 for performance because of render-blocking and unused shared CSS;
the other seven routes scored 100. Per-page lab metrics and fetch timestamps are
in the compact [Lighthouse page summary](/Users/dd/Documents/Codex/2026-09-27/i-ll-generate-the-master-execution/outputs/catalyx-phase6-lighthouse-pages.json)
(SHA-256 `09b7e241af761a01b36e22462f2abafef71a29dbf50a9ec998f2059a623f706c`).

The browser journey uses a temporary database and local mailbox. It exercises
synthetic registration, local email verification, site authorization, MFA
admin sign-in, and review queue approval. Its accessibility checks cover
document structure, accessible names, keyboard focus order, rendered text
contrast, small viewport reflow, and enlarged text on the pages in the test.

## Limits and remaining gates

These results establish the listed local automated behavior at the stated
revision only. They are not a human screen-reader session, complete WCAG 2.2 AA
conformance assessment, production-provider test, PostgreSQL concurrency test,
or staging/release approval. Lighthouse used mobile emulation with simulated
throttling; TBT is a lab metric, not field INP. Lychee and Lighthouse were
limited to the loopback preview. The full Lighthouse JSON report is saved at
`/Users/dd/Documents/Codex/2026-09-27/i-ll-generate-the-master-execution/outputs/catalyx-phase6-lighthouse.json`
(SHA-256 `b10f51cee2b977f195f24271da3ed9de6659f5240dfa28fa48dc2e027288e868`).
That full report contains the homepage run; the compact summary covers the
eight-route baseline before the focused CSS change. The full privacy-draft
baseline report, including its CSS audit details, is
saved at
`/Users/dd/Documents/Codex/2026-09-27/i-ll-generate-the-master-execution/outputs/catalyx-phase6-lighthouse-privacy.json`
(SHA-256 `62b363c87a744b168380cc7d0208a3ef35f0b7eace41c8a9daa107a0e504e04b`).

## Privacy and terms CSS follow-up (`a8f73a72`)

The legal draft routes now use a dedicated stylesheet while the other routes
continue to use the shared app stylesheet. The new bundle is **4,337 bytes**
versus **19,577 bytes** for `site.css` (77.8% smaller). On `/privacy`, Lighthouse
measured a render-blocking resource of 4,958 bytes and 159 ms, down from 20,199
bytes and 356 ms. It reports no unused or unminified CSS for the draft page.

The isolated mobile rerun scored performance 99, accessibility 100, best
practices 100, and SEO 100. LCP improved from 1.06 s to 0.8 s; CLS remained 0
and TBT was 100 ms. The performance category remains 99, so this change records
reduced CSS transfer and unused rules without claiming a perfect score. The
full post-change report is saved at
`/Users/dd/Documents/Codex/2026-09-27/i-ll-generate-the-master-execution/outputs/catalyx-phase6-lighthouse-privacy-compact-css.json`
(SHA-256 `e08bfaaccf747000a7a0e56332d4da6aa82537761ade76019c2e8e675ec72848`).

Fresh regression results against the changed source: Catalyx web suite **68
passed, one upstream deprecation warning**; synthetic Chromium journey **1
passed in 14.48 seconds**, now including privacy and terms in the accessibility
and reflow sweep; Ruff passed. The local CSS check asserts both draft routes
load the smaller bundle. No soak test was run.
The proposed Phase 6 scope remains pending owner ratification; phases 7–9
remain gated by provider, privacy/legal, hosting, and release decisions. No
soak test was run in this check.

### `/terms` post-change performance follow-up

The `/terms` mobile lab run with the compact bundle scored performance **94**, accessibility **100**, best practices **100**, and SEO **100**; LCP was 0.8 s, CLS 0, and TBT 290 ms. The CSS resource was 4,958 bytes with 160 ms estimated render-blocking savings and no unused CSS. The first run remains preserved at `/Users/dd/Documents/Codex/2026-09-27/i-ll-generate-the-master-execution/outputs/catalyx-phase6-lighthouse-terms-compact-css.json` (SHA-256 `3eaae80252c4a07fd501cf181b077241c11e83188ed7ea681168348e1da588c9`).

### `/terms` finite rerun — 28 September 2026, 11:43 NZDT

Using the pinned Chrome for Testing **153.0.8010.12** against the local
synthetic preview at `http://127.0.0.1:4174/terms`, with the recorded 412×823
mobile viewport and throttling settings, the rerun scored **100** for
Performance, Accessibility, Best Practices, and SEO. FCP/LCP/Speed Index were
0.92 s, CLS was 0, and TBT was 0 ms. The 94-point result's TBT was 294 ms;
the difference is consistent with run-sensitive lab TBT, but the two runs do
not establish a stable performance distribution. The current run is saved at
`/Users/dd/Documents/Codex/2026-09-27/files-pasted-by-the-user-catalyxlabs/outputs/2026-09-28-catalyxlabs-terms-lighthouse-rerun.json`
(SHA-256 `12daacd1c2f76f3891c6d5bd470f5d7b39e7fc3e332fff49707bcf5cae2c243d`).

### Narrow viewport reflow check — 28 September 2026

A temporary 600 CSS pixel layout viewport was used as a reflow proxy for a
1200 CSS pixel desktop view at 200% zoom. `/terms`, `/privacy`, and `/login`
had no document-level horizontal overflow; the closed `/register` route showed
its expected 404 response. The original 1200 CSS pixel viewport was restored
afterward. The browser zoom control itself did not change the browser zoom, so
actual 200% browser zoom remains unverified. No human screen-reader or WCAG
sign-off is implied by this proxy check.

### Bounded authentication cleanup regression verification — 28 September 2026

The current local diff bounds rate-limit cleanup to 100 rows per request and
adds a cross-scope sweep for stale rows. Its targeted regression verifies
that a dormant-scope backlog drains over three batches while a current
one-hour bucket remains. The full repository suite passed **264 tests**, with
5 opt-in browser tests skipped and 2 deprecation warnings. Ruff passed for
the changed Catalyx source/test files, and `git diff --check` passed. No soak
or load test was run. These local checks do not verify production PostgreSQL,
scheduled retention during idle periods, or provider staging.

### Finite accessibility refresh — 28 September 2026

On the synthetic local preview, keyboard Tab reached the visible skip link
first; Enter changed the URL fragment to `#main` and moved accessibility
focus to the main landmark. At a temporary 640 CSS pixel viewport, the sign-in,
sample report, check-scope, security/privacy, privacy and terms routes each
reported `scrollWidth == clientWidth`, one page-level H1, and one main
landmark. The document language was `en-NZ`. The sign-in email and password
fields were required, labeled, and used the username/current-password
autocomplete values. A synthetic malformed email triggered native browser
validation and left the page on the sign-in route; no credentials or account
data were submitted.

Anonymous navigation to `/app` and `/admin` returned a 401 page stating
"Sign in required" and displayed no customer or administrator content. This
checks only the no-session route guard; it does not replace tenant-isolation,
role-matrix, or authenticated journey coverage.

This was a finite keyboard and structure check. The browser zoom remained at
100% despite shortcut attempts, so the 640 CSS pixel viewport is only a
narrow-reflow proxy and does not close the actual 200% zoom requirement.
VoiceOver or another screen reader, authenticated customer/admin workflows,
and human WCAG sign-off remain pending. The temporary viewport was reset to
its default after the check. No soak or load test was run.

### Tenant-boundary regression extension — 28 September 2026

Against the current local working tree, three focused tests passed: the
versioned API tenancy and review test, the customer ownership and admin MFA
journey, and the administrator role matrix (**3 passed**, one upstream
Starlette/httpx deprecation warning per pytest invocation; the ownership test
was rerun after its final assertion was added). The additional
negative cases verify that a second customer cannot list or read another
workspace's site/audit, create an audit against its site, or cancel its audit
through the API. The customer pages also return 404 for a foreign site/audit
and reject a cross-workspace cancellation; the original customer's pending
audit remains in authorization review. The role matrix test passed unchanged.
After report release, the owning customer's API returns the report while the
second customer's API receives 404 for the same audit ID.

These checks use synthetic users and local SQLite. They strengthen route-level
negative coverage but do not prove PostgreSQL behavior, authenticated provider
staging, object-storage authorization, or full human role walkthroughs. No
soak or load test was run.

### Fresh full-suite and browser journey verification — 28 September 2026

After the tenant-boundary assertions were added, the full repository command
`.venv/bin/python -m pytest toolkit_tests -q` passed **264 tests**, skipped 5
opt-in browser tests, and reported 2 upstream deprecation warnings in 98.06
seconds. The dedicated Catalyx browser test was then enabled explicitly with
`WA_CATALYX_WEB_BROWSER_E2E=1` and passed **1 test in 24.96 seconds**. The
remaining four opt-in browser tests were not run. Ruff passed for
`toolkit_tests/test_catalyx_web.py` and `git diff --check` passed. No soak or
load test was run.

These remain local synthetic checks. They do not demonstrate provider staging,
production PostgreSQL, isolated worker egress, backup/restore, or production
accessibility sign-off.

### Python 3.12.14 compatibility check — 28 September 2026

Using the repository's pinned `requirements-catalyx-web.lock` and locked
development/browser extras in an isolated CPython 3.12.14 environment,
`toolkit_tests/test_catalyx_web.py` passed **73 tests** with one upstream
Starlette/httpx deprecation warning. The dedicated Catalyx customer/admin
browser journey passed **1 test**. Ruff passed on both changed Catalyx test
modules. This is local test evidence only: it does not verify a Vercel build,
deployment bundle, hosted runtime, or staging environment. No soak or load
test was run.

### Current-HEAD verification — 28 September 2026

At `7891c9aeee022fb025afa20d1f14f8dca62eb7f9`, the full repository suite
passed **265 tests** with **5 opt-in browser tests skipped** and two upstream
Starlette/httpx deprecation warnings (68.85 seconds). The dedicated Catalyx
customer/admin browser journey passed **1 test** (17.83 seconds). Ruff passed
for `catalyx_web` and `toolkit_tests/test_catalyx_web.py`; `uv lock --check
--offline` and `git diff --check` passed.

An offline wheel build at the same source revision succeeded. Inspection of
the resulting 324.8 KB monorepo wheel confirmed all five Catalyx static assets
are packaged; SHA-256:
`93b3dba1824b8ba071570ece668f6da869dcf56f17989705c0e349960a8ee78f`. This
does not validate Vercel function discovery, deployment bundling, hosted
startup, or provider routing.

The separate current-source security scan reviewed all 15 tracked
`catalyx_web` files with complete static coverage and reported five findings
(two medium, three low); see the [current source security report](../../../../../files-pasted-by-the-user-catalyxlabs/outputs/2026-09-28-catalyxlabs-current-source-security-scan.md).
These checks use the local synthetic environment. They do not verify provider
staging, live PostgreSQL, production configuration, or isolated worker egress.
No soak or load test was run.

### Current browser accessibility-tree and reflow observation — 28 September 2026

On current HEAD `7891c9aeee022fb025afa20d1f14f8dca62eb7f9`, an isolated browser
review of `/`, `/how-it-works`, `/what-we-check`, `/security-and-privacy`,
`/sample-report`, `/privacy`, `/terms`, `/login`, and `/forgot-password` found
one main landmark and one H1 on each route. Login and password-reset fields
have accessible names; the visible buttons have text names. At 640×900 and
320×900 CSS pixel layout viewports, `scrollWidth == clientWidth` on every
route. These are reflow proxies. Browser zoom stayed at 100%, so actual 200%
zoom was not verified.

Keyboard review on `/login` found Tab focused the skip link first; Enter moved
focus to `main` and set `#main`; subsequent Tab order was Email, Password,
Sign in, then Forgot your password. This is not an assistive-technology
session or human WCAG 2.2 AA sign-off. Screen-reader testing, actual 200% zoom,
non-text contrast, and authenticated customer/admin human review remain open.

### Current-HEAD continuation — 28 September 2026

Current source is commit `f3e0448269c449615b177693d75a9ba21a4903a5` on
`codex/catalyx-rebuild-phase1-5`. The full local suite passed **267 tests**,
with **5 opt-in browser tests skipped** and two upstream deprecation warnings.
The dedicated Catalyx customer/admin browser journey passed **1 test**;
Ruff, `uv lock --check --offline`, and `git diff --check` passed. These checks
use synthetic local data and do not establish provider staging or production
readiness. Soak/load testing was skipped at the owner's direction.

The exact diff from `7891c9aeee022fb025afa20d1f14f8dca62eb7f9` to current HEAD
was reviewed by Codex Security across all three changed files. Coverage is
complete and the scan reported **zero reportable findings**. Its report is
`/Users/dd/.codex/state/plugins/codex-security/scans/catalyx-auditor-rebuild/f3e0448269c449615b177693d75a9ba21a4903a5_20260928T044029Z_bi9p4s1g/report.md`.
The review is a local source diff assessment; it did not inspect live provider
configuration or exercise PostgreSQL concurrency.

The committed source now enforces one audit request per workspace per UTC day
and five globally pending requests; recognizes hosted startup restrictions for
registration and SMTP; and corrects the public description of the single-page
profile. The customer-facing worker remains disabled. Production and `.com`
remain no-go while provider/data/identity decisions, secure onboarding,
privacy/legal approval, named owners, production limits, worker isolation,
database recovery, accessibility sign-off, staging, alerts, and rollback
evidence remain incomplete. `.shop` is untouched.

### Owner-directed admission caps — 28 September 2026

The local build now enforces one audit request per workspace per UTC day and a
global cap of five pending requests. The SQLite and PostgreSQL admission lock
paths are present, but only SQLite was exercised by this run; provider
PostgreSQL concurrency remains unverified. The planned five-workspace customer
cap and single active worker are not implemented. The updated full repository
suite passed **267 tests**, skipped 5 opt-in browser tests, and reported two
upstream deprecation warnings. The dedicated Catalyx browser journey passed
**1 test**; Ruff and `git diff --check` passed. No soak or load test was run.

### Hosted onboarding and mail guard — 28 September 2026

The app refuses public registration in execution modes recognized as hosted
and refuses hosted SMTP/external account email. Local synthetic registration
and mocked SMTP route tests remain available. Eight focused configuration and
compatibility tests passed; the full suite passed **267**, with 5 opt-in
browser checks skipped and two upstream deprecation warnings. The dedicated
Catalyx customer/admin browser journey passed **1 test**. The selected
provider's production marker must be confirmed in staging. No provider
staging or live email was exercised, and no soak/load test was run.

### Beta customer and worker caps — 28 September 2026

The local database now atomically limits customer workspaces to five across
concurrent registration attempts. Schema version 7 creates a shared worker
lease row; the manual worker acquires that lease before claiming work and
returns `busy` if another worker holds it. The lease expires after 90 seconds
to recover from a crashed process; the customer scan profile has a 35-second
total request deadline. PostgreSQL migration/locking behavior has not been
exercised against a live database, and the customer-facing worker remains
disabled until independent OS/network isolation is built.

The full repository suite passed **269 tests**, with **5 opt-in browser tests
skipped** and two upstream deprecation warnings. The dedicated Catalyx browser
journey passed **1 test**. Six focused workspace-cap, admission, worker-lease,
fencing, cancellation, and schema-migration tests passed; Ruff and
`git diff --check` passed. These local checks are not soak/load tests, which
remain skipped as directed.

### Previous worker-cap diff snapshot (committed in `0f8397c3`) — 28 September 2026

The tracked worker-cap change set was committed and pushed as `0f8397c3`. Full
local verification at that revision passed **269 tests**, with **5 opt-in
browser tests skipped**; Ruff and `git diff --check` passed. Codex Security
scan `09604840-2df3-4a0c-9ce9-a9359b052fee` reported zero confirmed reportable
findings and partial coverage, deferring the long process-pause worker-overlap
scenario. PostgreSQL behavior, hosted worker isolation, and provider staging
remain unverified. Production stays no-go while A7 named operations contacts
and A8 legal identity and approved copy are outstanding. No soak/load test was
run.

### Worker lease expiry recovery check — 28 September 2026

A new deterministic synthetic regression pauses a worker beyond its 90-second
global lease and 60-second request lease, then verifies that a replacement
worker completes the request and the stale worker cannot continue the audit or
persist another result. The full repository suite passed **270 tests**, with
**5 opt-in browser tests skipped** and two upstream deprecation warnings. The
three focused global-lease, expiry-recovery, and result-fencing tests passed;
Ruff and `git diff --check` passed. PostgreSQL migration/concurrency and hosted
worker isolation remain unverified. A7/A8 owner gates remain open; no soak or
load test was run.
