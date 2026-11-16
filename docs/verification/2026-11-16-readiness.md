# Cloud auditor verification — 16 November 2026

This record distinguishes working components from unfinished deployment. Base
revision: `e8da967379e38508fe3fee43ac6b49f202e35bbd`.

## Confirmed live finding and corrected proposal scope

Independent HTTPS source checks used Python's standard-library HTML parser,
separate from the auditor's BeautifulSoup implementation. Robots permitted the
checked paths. Each response was HTTP 200 and below the 2 MB cap. Response
hashes, byte counts and UTC observation times are in
[`2026-11-16-meta-description.json`](2026-11-16-meta-description.json).

| David Robertson Decorators page | Standard description tags | Open Graph description tags |
| --- | ---: | ---: |
| `/` | 0 | 1 |
| `/interior-painting/` | 1 usable | 1 |
| `/exterior-painting/` | 1 usable | 1 |
| `/commercial-painting/` | 1 usable | 1 |
| `/roof-painting/` | 1 usable | 1 |

The homepage finding is independently confirmed for the fetched HTML. This
does not establish a ranking, traffic or conversion loss. An Open Graph
description is separate from `meta[name="description"]`. The other four pages
do not need a missing-description fix on this evidence. Descriptions changing
after this observation require a new check.

Internal proposal: add one relevant homepage description through the site's
existing CMS/SEO settings after owner and client authorization. Suggested copy:

> Christchurch painters since 1991. David Robertson Decorators offers interior,
> exterior, roof and commercial painting. Request a free estimate.

Verify the resulting homepage HTML contains the approved standard description.
Pricing is unset; no implementation, client contact or commercial commitment
has occurred. This is a one-page scope, not a five-page metadata replacement.

## Four active websites, five intake records

`clients.txt` contains four active websites. `config/cloud-prospects.json`
contains those four plus a suppressed JC Construction record. Its
`audit_authorized=false`, `suppressed=true` and
`review_basis=commercial_content_permission_required` explain the difference
from the older five-site archive. Do not restore that site merely to match the
old count. The durable queue intentionally counts suppressed intake records
within `prospects_found`; that metric is not an active-site count.

## GitHub execution evidence

On the base revision, CI, security, CodeQL and the canonical cloud audit passed.
The canonical worker actually executed and uploaded the encrypted review:
[run 43817004022](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/43817004022).

The durable workflow's
[manual run 43817027390](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/43817027390)
passed offline tests but skipped `draft-pipeline`. Its activation condition
requires `WA_PIPELINE_ENABLED=true` on master. This is not proof of a working
durable checkpoint in GitHub. The new configuration job prevents a manual
dispatch from appearing successful when activation is disabled or its state
key is missing. It does not enable the worker or change any secret.

## Remaining administrative blockers

1. Configure/verify `WA_PIPELINE_STATE_KEY` privately and set
   `WA_PIPELINE_ENABLED=true`. Dispatch on master with `bootstrap=true` only
   when no earlier worker checkpoint exists. Verify a real worker and artifact,
   then dispatch with `bootstrap=false` and verify restore and deduplication.
   The connected repository tools expose no secret/variable mutation or new
   workflow-dispatch operation; the separate browser is signed out of GitHub.
   Secret presence has not been established from that browser.
2. SonarCloud run
   [43817004014](https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/43817004014)
   failed server-side processing: 33,750 existing organization LOC plus 17,327
   LOC in this analysis would total 51,077 against a 50,000 allowance. This is
   not a passing quality gate. Inspect project usage with organization-admin
   access, then remove verified obsolete/duplicate usage or choose an eligible
   plan. Do not exclude production source or suppress the failure to make CI
   green. Public unauthenticated API requests returned 403; no administrator
   session is available in this workspace.

## Local validation and limits

- Canonical/upgrade regression: 763 passed, 5 optional tests initially skipped,
  14 subtests passed. The one DNS-dependent handler test was made deterministic;
  a separate test verifies unresolved targets are rejected before an audit.
- Portable MoneyMachine regression: 113 passed, 45 subtests passed.
- Workflow configuration branches: disabled manual dispatch fails; disabled
  schedule reports disabled; enabled worker with missing key fails; configured
  worker can proceed. Dependency/YAML and whitespace checks passed.
- An attempted live durable-queue run from this shell did not complete: direct
  DNS/HTTP access required by the canonical fetcher is unavailable here. All
  four active entries remained retryable. Encryption round-trip and no-repeat
  attempt checks succeeded, but this attempt is not a successful live audit or
  a deployed checkpoint. Production network guards were kept intact.
- Browser/PDF checks attempted with system Chromium were blocked by the local
  operating system: Chromium could not create its process-singleton socket.
  The proof adapter also leaked its Playwright runtime after failed setup;
  cleanup and successful retry are now covered for both launch and context
  failures. The new CI browser job runs the real local-fixture audit, portal
  login/logout, PDF downloads and proof-browser checks on an Ubuntu runner.
- Actual GitHub bootstrap/restore and the post-fix SonarCloud gate remain
  unverified. The earlier completed soak test was not repeated.

The transport remains disabled with cap zero. Paid/model/send flags remain
zero. No sending or payment adapter was enabled, no private recovery key was
committed, and no client website was modified. Deployment is not complete until
the administrative blockers and actual worker executions above are resolved.
