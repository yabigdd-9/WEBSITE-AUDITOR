# Hosting cost and terms assessment

**Checked:** 2026-09-28
**Scope:** Existing Vercel account and $0 alternatives for the CatalyxLabs
Website Auditor, including Cloudflare Workers, Render, Fly.io, and Oracle Cloud
Infrastructure. This is a read-only assessment; no project, database, or DNS
settings were changed.

## Current Vercel account

- The signed-in Vercel dashboard labels the current `yabigdd-1427` workspace as
  **Hobby**. The `website_auditor` project exists in that workspace. A fresh
  custom-domain assignment could not be read from the project settings view in
  this check, so the `.com` binding remains unverified.
- Vercel's current [Terms of Service](https://vercel.com/legal/terms) say Hobby
  use is limited to personal or non-commercial purposes. Their [Hobby plan
  guide](https://vercel.com/docs/plans/hobby) repeats that restriction. The
  Website Auditor is intended as a CatalyxLabs customer service, so its
  commercial production use cannot be placed on this Hobby account.
- The same terms say that content submitted by Hobby or trial-Pro users may be
  used to train Vercel models and shared with third parties for model
  improvement. Do not put customer site reports or account records on this
  account under the Hobby terms.
- This conflicts with the pasted plan's $0 ceiling and its historic direction
  to reuse Vercel for hosting. Do not treat the existing account as an approved
  production host. A paid Vercel plan would require changing that budget, which
  has not been authorized.

## $0 alternative under investigation: Cloudflare Workers

Cloudflare's official [Python Worker FastAPI guide](https://developers.cloudflare.com/workers/languages/python/packages/fastapi/)
shows FastAPI running behind its ASGI entry point. The current [Python Worker
overview](https://developers.cloudflare.com/workers/languages/python/) exposes
bindings for D1 and Queues. The Free plan advertises 100,000 Worker requests per
day and 10 ms CPU per request in its [limits page](https://developers.cloudflare.com/workers/platform/limits/).
Its [D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/)
includes up to 5 million rows read per day, 100,000 rows written per day, and
5 GB total storage. [Queues pricing](https://developers.cloudflare.com/queues/platform/pricing/)
includes 10,000 operations per day, with 24-hour message retention on Free.

These limits do not prove production fit or zero cost for the business. A
local-only Python Worker probe served FastAPI's `/` and a D1 binding query.
`hashlib.pbkdf2_hmac` is missing from the Python Worker runtime, and direct use
of the app's current `cryptography` AES-GCM dependency crashed Pyodide during
module loading with an entropy (`getRandomValues`) failure. A separate
prototype bridge through Worker WebCrypto now completes an AES-GCM round trip
and derives a 310,000-iteration PBKDF2 key matching a CPython reference. Local
wall-time samples ranged from 0.4 to 2.2 seconds across runs (388 ms on the
latest check, 2026-09-28). The probe is not integrated with the app's auth code,
and wall time does not establish Cloudflare's measured
CPU time or fit within the Free CPU limit. These results identify both a
possible port and the integration/performance work still required.

The current app also depends on a synchronous SQLite/PostgreSQL interface,
PostgreSQL `psycopg`, and a raw-socket DNS-pinned audit transport. Cloudflare
Workers would need a D1-aware async persistence layer, authenticated encryption
and password hashing integrated with the WebCrypto bridge and existing account
flows, and an egress design
that satisfies the audit SSRF controls. The 10 ms Free CPU limit remains a
serious risk for Python request handling and authentication. No deployment or
production Cloudflare runtime test has been run.

Before selecting this path, build a local Worker-runtime proof for:

1. Public routes and static assets through FastAPI ASGI.
2. Registration, verification, sign-in, reset, TOTP, rate limits, and tenant
   authorization using D1 transactions and bindings.
3. WebCrypto MFA encryption and password verification, including existing
   password-hash compatibility and Free CPU measurements.
4. A durable queue/reconciliation flow that remains recoverable after a message
   expires at 24 hours.
5. A scan egress design that cannot reach private, link-local, metadata, or
   unapproved hosts, even when DNS changes between validation and connection.
6. Backups, export/deletion, logging, provider terms, data location, restore,
   cost-limit behavior, and rollback without exceeding $0.

Do not deploy customer data until each item has passing evidence and the
provider's applicable product terms have been reviewed for this commercial use.

## Other apparent $0 hosting paths reviewed — 2026-09-28

**Render Free is not a production path.** Render's own guide says free
instances are for testing, hobby projects, and platform previews, and explicitly
advises against production use. Free web services have ephemeral local storage;
their free PostgreSQL instances expire after 30 days. Free web instances also
sleep after 15 idle minutes, can restart at any time, and excessive outbound
bandwidth can generate a supplementary bill. The service supports Python and
custom domains, but these limitations conflict with durable customer data,
continuous operation, and the NZ$0 ceiling. [Render free services](https://render.com/docs/free)

**Fly.io is a trial, not continuing $0 hosting.** Its current free trial is
seven days with two total VM hours, after which apps stop unless billing is
configured. Ongoing shared compute starts at about US$2.02 per month for a
small VM; persistent volumes and some network transfer also cost extra. It
does not meet a recurring NZ$0 limit. [Fly.io free trial](https://fly.io/docs/about/free-trial/) ·
[Fly.io pricing](https://fly.io/docs/about/pricing/)

**Oracle Cloud Infrastructure Always Free is the only new raw-compute candidate
found that merits an owner review, but it is not approved for this release.**
The documented Always Free allowance includes up to 2 OCPUs and 12 GB of Arm
memory, plus up to 200 GB of combined block storage, which could host a small
FastAPI app and self-managed PostgreSQL VM at $0 if all usage stays within the
home-region allowances. It would put app and data operations on an owner-managed
VM and would require a separate, constrained worker boundary, patching,
monitoring, backups, and recovery. Oracle documents no SLA, support, or service
continuity policy for Always Free resources. It may reclaim an instance after a
seven-day period if its CPU, network, and (for A1) memory usage all remain
below the stated 20% thresholds. Its current commercial region list includes
Sydney and Melbourne, but no New Zealand region; using those regions would
require review of Australian data processing and cross-border obligations.
Capacity can also be unavailable in a selected home region. These conditions
make it a fragile option for a public customer service even though it is
technically capable of running Python and PostgreSQL. [Always Free resource limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) ·
[Free Tier terms and limits](https://docs.oracle.com/iaas/Content/FreeTier/freetier.htm) ·
[OCI commercial regions](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm) ·
[Oracle policy for Always Free services](https://www.oracle.com/webfolder/dms/prod/docs/Oracle-PaaS-and-IaaS-400379759.pdf)

Australian hosting does not by itself decide whether New Zealand Privacy Act
IPP 12 applies. The Office of the Privacy Commissioner says sending information
to an overseas cloud provider solely as an agent for storage or processing is
not treated as a disclosure under IPP 12 if that provider does not use or
disclose it for its own purposes. The legal review still needs to confirm the
actual provider role and contract, onward access/use, data location, and the
other applicable Privacy Act duties. [IPP 12 guidance](https://www.privacy.org.nz/privacy-principles/12/) ·
[IPP 12 decision tree](https://www.privacy.org.nz/responsibilities/disclosing-personal-information-outside-new-zealand/decision-tree-page/)

These alternatives do not establish an approved zero-cost commercial
production path. The owner must decide whether to accept OCI's reclaim,
availability, support, operational, and Australian data-location limits for a
small invitation-only beta; retain the Vercel/Cloudflare direction and complete
the substantial Worker port; or revise the NZ$0 constraint. No provider account,
resource, region, project, or DNS change was made during this review.

## Decision

Production hosting is blocked pending a verified $0 commercial deployment path
or a user-approved budget change. The current code remains in local staging.
Keep `.com` DNS, its existing Vercel project assignment, customer data, and
`.shop` unchanged while the Worker compatibility proof is built.

## Official documentation refresh — 2026-09-28

The current Cloudflare documentation still lists Workers Free at 100,000
requests/day and 10 ms CPU per invocation, with 128 MB memory. HTTP wall time
has no fixed request-duration cap while the client remains connected, but this
does not remove the 10 ms CPU ceiling. Cloudflare says typical heavier
authentication and server-rendering workloads can use 10–20 ms, so the current
310,000-iteration password hash and app request path need measured runtime
evidence before this tier can be treated as viable. The existing local
WebCrypto timing is wall-clock timing and does not establish platform CPU use.
[Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
· [Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/)

The latest D1 Free table lists 5 million rows read/day, 100,000 rows written/day,
and 5 GB total storage. When a daily read/write limit is reached, D1 rejects
queries until reset. Queues Free includes 10,000 operations/day and
non-configurable 24-hour message retention. A $0 architecture would therefore
need D1 (or another durable approved store) to remain the source of truth for
job recovery after queue expiry and must fail closed on quota exhaustion. It
also cannot claim continuous availability from these quotas alone.
[D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/) ·
[Queues pricing](https://developers.cloudflare.com/queues/platform/pricing/)

Cloudflare's Workers security model describes outbound HTTP as passing through
a proxy that permits public Internet services and the Worker's own zone origin,
while preventing access to internal services. This could add a host-level
private-network boundary for a separate scan Worker. It does not verify this
app's authorized-host/redirect policy, queue permissions, report access, or
production deployment configuration; those still need integration and security
evidence. [Workers security model](https://developers.cloudflare.com/workers/reference/security-model/)

## Fresh signed-in Vercel dashboard review — 2026-09-28

The current `yabigdd-1427` workspace remains on **Hobby**. Its deployment
storage usage page, set to the preceding 30 days and updated during this check,
reported **10.66 GB / 10 GB**. The `website_auditor` project accounted for
**9.37 GB**; `catalyx-labs-grow-os` used **606.49 MB**, `work` used
**308.96 MB**, and `catalyx-labs-grow-os-recovery` used **378.3 MB**. Vercel's
16 September 2026 [Hobby retention update](https://vercel.com/changelog/hobby-projects-now-retain-fewer-deployments-to-free-up-storage)
says usage above the 10 GB limit can block new deployments until storage is
freed. The dashboard did not show that the existing `.com` deployment is
paused. Do not remove deployments without an owner-approved retention decision;
the overage is an additional risk to producing a staging or release artifact.

The current `catalyx-labs-grow-os` Domains page lists the `.com` apex and `www`
as Production domains marked **Proxy Detected**. It lists `.shop` apex as a
308 redirect to `www` and `www.catalyxlabs.shop` as a Production domain. The
`website_auditor` project lists only `websiteauditor-drab.vercel.app`; it has
no `.com` assignment. The team overview also associates `www.catalyxlabs.shop`
with a separate `work` project, but the detailed `work` Domains page lists only
`work-omega-inky.vercel.app`, and has no `.shop` assignment. The team-level
Domains page lists `.com` and `.shop` registrations, and the detailed Grow OS
page confirms the active assignments above. Treat the `work` summary link as a
listing inconsistency rather than a second `.shop` assignment. No setting or
deployment was changed.

Commercial suitability remains unresolved. Cloudflare's general plan page
describes its Free plan for personal or hobby projects that are not
business-critical, while the current self-serve agreement says Cloudflare may
end a Free Service at its discretion and disclaims liability for harm arising
from Free Services. The Workers-specific Free tier is separately documented,
so this wording alone does not establish that a commercial Auditor workload is
prohibited or permitted. Obtain owner/privacy/legal review of the applicable
plan and agreement, the intended business-critical use, NZ personal-data
processing, regional controls, support and continuity obligations before
customer data use. The Workers Paid plan starts at US$5/month, so it violates
the recorded NZ$0 ceiling and is not a fallback under the current decision.
[Cloudflare plans](https://www.cloudflare.com/plans/) ·
[Self-Serve Subscription Agreement](https://www.cloudflare.com/terms/) ·
[Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/)

Latest finite local compatibility run on 2026-09-28 used a cleared inherited
environment and Wrangler 4.142.0. The public, runtime, crypto, and D1 probe
routes returned HTTP 200. Native `hashlib.pbkdf2_hmac` remained unavailable;
the standalone WebCrypto bridge passed AES-GCM and 310,000-iteration PBKDF2
reference checks at 388 ms local wall time, and the local D1 `SELECT 1` passed.
The initial Python runtime request took about 51.9 seconds locally and the
bundle was 31.59 MiB across 2,090 modules. These are not Cloudflare CPU,
production cold-start, quota, egress, or app-integration results. App
authentication and the D1 persistence adapter remain unimplemented in this
probe. The local server was stopped after the finite requests; no cloud
account, resource, DNS record, customer data, or external service was touched,
and no soak test was run.

## Official sources checked

- [Vercel Terms of Service](https://vercel.com/legal/terms)
- [Vercel Hobby plan](https://vercel.com/docs/plans/hobby)
- [Cloudflare FastAPI on Python Workers](https://developers.cloudflare.com/workers/languages/python/packages/fastapi/)
- [Cloudflare Workers Free limits](https://developers.cloudflare.com/workers/platform/limits/)
- [Cloudflare D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/)
- [Cloudflare Queues pricing](https://developers.cloudflare.com/queues/platform/pricing/)
- [How Python Workers Work](https://developers.cloudflare.com/workers/languages/python/how-python-workers-work/)
- [Workers security model](https://developers.cloudflare.com/workers/reference/security-model/)
- [Cloudflare Self-Serve Subscription Agreement](https://www.cloudflare.com/terms/)
- [Render free services](https://render.com/docs/free)
- [Fly.io free trial](https://fly.io/docs/about/free-trial/)
- [Fly.io pricing](https://fly.io/docs/about/pricing/)
- [Oracle Always Free resource limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [Oracle Cloud Free Tier](https://docs.oracle.com/iaas/Content/FreeTier/freetier.htm)
- [OCI regions](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm)
- [Oracle policy for Always Free services](https://www.oracle.com/webfolder/dms/prod/docs/Oracle-PaaS-and-IaaS-400379759.pdf)
- [New Zealand Privacy Commissioner: IPP 12](https://www.privacy.org.nz/privacy-principles/12/)
- [New Zealand Privacy Commissioner: IPP 12 decision tree](https://www.privacy.org.nz/responsibilities/disclosing-personal-information-outside-new-zealand/decision-tree-page/)

## Current quota and commercial-use recheck (2026-09-28)

The latest official [Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
and [pricing](https://developers.cloudflare.com/workers/platform/pricing/)
still list Workers Free at 100,000 requests per account per day and 10 ms CPU
per HTTP request; the Workers Paid plan starts at US$5/month. The free CPU
ceiling is a material risk for this Python authentication workload: the local
WebCrypto timing in this document is wall time, does not measure Worker CPU,
and is not integrated with application authentication.

Cloudflare's [D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/)
lists 5 million rows read per day, 100,000 rows written per day, and 5 GB total
storage for Free. Its [1 September 2026 changelog](https://developers.cloudflare.com/changelog/post/2026-09-01-d1-free-tier-limit-enforcement/)
confirms those daily row caps are enforced: further D1 queries fail until
midnight UTC after an account exceeds either limit. D1 data remains stored,
but the app would lose database availability until reset or plan change.

The [Queues Free limits](https://developers.cloudflare.com/queues/platform/limits/)
and [pricing](https://developers.cloudflare.com/queues/platform/pricing/)
confirm 10,000 operations/day and non-configurable 24-hour message retention.
Typical message delivery consumes a write, read, and delete operation; retries
and dead-letter handling use additional operations. A queue alone therefore
cannot be the durable source of truth for audit jobs; persistent job state,
expiry recovery, and replay behavior need an approved design and rehearsal.

This refresh leaves Vercel Hobby unsuitable for the intended commercial
service under the documented [fair-use rule](https://vercel.com/docs/limits/fair-use-guidelines).
Cloudflare Free remains a technical candidate, not an approved production
choice. Its strict CPU and daily row/operation caps, 24-hour queue retention,
local-only compatibility results, data-processing terms, service continuity,
and business-critical suitability still require owner and privacy/legal review.
No account, resource, plan, or project setting was changed.

## Historical preliminary Vercel runtime assessment — superseded below (2026-09-28)

Vercel's current [Python runtime documentation](https://vercel.com/docs/functions/runtimes/python),
last updated 30 January 2026, confirms the Python runtime supports FastAPI and
ASGI applications. It currently labels Python runtime support **Beta** and
lists Python 3.12 as the default, with 3.13 and 3.14 also available. The
[FastAPI guide](https://vercel.com/docs/frameworks/backend/fastapi) says a
FastAPI application is deployed as one Vercel Function and uses Fluid Compute
by default. This establishes framework compatibility in the provider's
documented model; it does not establish that this checkout has a working Vercel
build or environment.

This first pass incorrectly concluded that the repository needed a thin
`api/` function entrypoint. The later entrypoint refresh below corrects that:
Vercel documents a custom module entrypoint, and this checkout exports
`catalyx_web.app:app`. Deployment-root selection, bundle include/exclude rules,
runtime compatibility, and binary dependencies still need a build assessment.

The first pass recorded the standard Python bundle cap as 500 MB. The later
refresh below adds the 5 GB public beta qualification. Request and response
payloads remain capped at 4.5 MB. With Fluid Compute, the documented Hobby
maximum duration is 300 seconds; without it, the Hobby maximum is 60 seconds.
Function duration is not a durable queue or worker guarantee.
Production data still needs separately selected durable services; the web
function must not run customer scans.

The [Terms of Service](https://vercel.com/legal/terms), last updated
1 June 2026, limit Hobby use to personal or non-commercial use. The terms also
allow Vercel to use Hobby and trial-Pro submitted content for model training
and share it with third parties for product/model improvement. A commercial
customer service with site reports is therefore not approved for the current
Hobby workspace. Vercel Python support does not change that terms or budget
blocker. A paid plan would require an explicit change to the NZ$0 constraint;
no such approval is recorded.

**Decision status:** Vercel is a technically documented FastAPI host, but is
not an approved production choice under the current account and budget. A
Vercel implementation would still require owner approval of terms/spend,
entrypoint/build proof, persistent data services, and an isolated worker
architecture. This preliminary runtime assessment is superseded by the
entrypoint and package-limit refresh below. No deployment or provider setting
was changed.

## Fresh Cloudflare zone and TLS review — 2026-09-28 11:18–11:23 NZDT

Read the signed-in Cloudflare dashboard for `catalyxlabs.com` in the existing
account, without changing settings. The zone is on the Free plan, DNS setup is
Full, and the Records view contains 10 of 200 records. The website records are
apex `A 76.76.21.21` and `www CNAME cname.vercel-dns-0.com`; both are proxied
with automatic TTL. `_domainconnect` points to
`_domainconnect.gd.domaincontrol.com` and is also proxied. The remaining apex
TXT rows are Vercel nameserver and domain verification records; verification
values are intentionally omitted from this assessment. `_dmarc` has
`p=quarantine`, relaxed DKIM/SPF alignment, and a reporting destination at
`onsecureserver.net`. The current zone list contains no MX record and no SPF
policy. Preserve all verification and mail-related records during any later
`.com` change; the detailed dashboard snapshot is in the user-facing provider
record.

Cloudflare currently reports SSL/TLS mode **Full**, not Full (strict), and a
Universal certificate for the apex and wildcard that is Active through
2026-12-07; the backup certificate is Issued through 2026-12-09. Minimum TLS
Version is set to the `TLS 1.0 (default)` option. The `Always Use HTTPS`
setting is off, although fresh HEAD requests to both HTTP `.com` hostnames
returned 308 redirects to HTTPS and HTTPS responses include
`Strict-Transport-Security: max-age=63072000; includeSubDomains`. TLS 1.3 and
Automatic HTTPS Rewrites are enabled. Certificate Transparency Monitoring is
off. These are observed settings, not changes or launch approval; review the
Full (strict) origin validation and TLS 1.2 minimum before a production
cutover. The current Vercel Hobby host remains commercially ineligible and
the production architecture is still unapproved.

## Vercel FastAPI entrypoint and package-limit refresh — 2026-09-28

The current Vercel FastAPI guide (15 June 2026) and Python runtime
documentation now describe automatic FastAPI detection with a supported
entrypoint. Vercel supports a custom module through
`[tool.vercel] entrypoint = "catalyx_web.app:app"` in `pyproject.toml`.
This checkout exports `app` at that module path, so a new `api/index.py`
shim or `vercel.json` is not inherently required just to make FastAPI
detection work. This corrects the earlier statement that a thin entrypoint was
necessarily required. The project root still needs a deployment/build
assessment: it is a large monorepo, and Python functions do not tree-shake the
repository automatically. Vercel supports function file inclusion/exclusion
rules, but a clean build, package inventory and asset lookup have not been
verified for this application.

The documented standard Python function bundle limit is 500 MB. Vercel's
29 June 2026 public beta raises Node.js/Python Fluid Compute functions to 5 GB;
existing projects require `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` or a prompted
opt-in. The beta is not enabled in this workspace and is incompatible with
Secure Compute and Static IP features. It does not make the app's manual scan
worker safe or isolated. Request and response payloads remain limited to
4.5 MB. These changes correct and qualify the earlier 500 MB-only package
statement; no Vercel setting was changed.

The official runtime defaults to Python 3.12, while the local locked worktree
currently runs Python 3.11.16 and declares `requires-python >=3.11`. No Python
3.12 deployment build or native-dependency check has been run. Vercel
FastAPI/runtime compatibility is now documented, but this checkout is still
not a verified deployable artifact. Vercel Hobby's personal/non-commercial
restriction, the NZ$0 cap, customer-content terms, durable data/queue choices,
and worker isolation remain separate launch blockers.

Official sources checked in this refresh:
[FastAPI on Vercel](https://vercel.com/kb/guide/ship-a-fastapi-app-on-vercel)
(15 June 2026),
[Python runtime and entrypoints](https://vercel.com/docs/functions/runtimes/python),
[Function limits](https://vercel.com/docs/functions/limitations), and
[5 GB Large Functions public beta](https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size)
(29 June 2026). No project, deployment, account, environment, or domain
setting was changed.

## Cloudflare Workers Free terms and hard-limit refresh — 2026-09-28

Reviewed Cloudflare's current [Self-Serve Subscription Agreement](https://www.cloudflare.com/terms/)
and [Developer Platform Service-Specific Terms](https://www.cloudflare.com/service-specific-terms-developer-platform/)
alongside the [general plans page](https://www.cloudflare.com/plans/) and current
Workers/D1/Queues documentation. The general Free plan is positioned for
personal or hobby projects that are not business-critical. The account and
Developer Platform terms reviewed do not state an express general ban on
commercial Developer Platform use; that observation is not legal approval for
this product or a conclusion about whether its beta would be business-critical.
The agreement calls free offerings revocable at Cloudflare's discretion and
disclaims liability for harm connected with Free Services. The Developer
Platform terms allow Cloudflare to limit storage or requests, place support and
end-user obligations on the customer, and suspend access. They state that
Cloudflare does not use Developer Platform Customer Content except as needed to
provide the Services and that source-code IP remains with the customer.

Current free-tier ceilings are material to service continuity: Workers allow
100,000 inbound requests per day and 10 ms CPU per request; D1 includes 5
million rows read/day, 100,000 rows written/day, and 5 GB total storage; and
Queues include 10,000 operations/day with non-configurable 24-hour message
retention. Since 1 September 2026, exceeding D1 daily read/write limits causes
queries to fail until the reset at midnight UTC. The Workers Paid plan starts
at US$5/month, which is outside the NZ$0 constraint.

**Decision status:** Cloudflare Workers Free remains an unapproved candidate,
not a confirmed commercial host. Its current public terms do not establish a
commercial-use prohibition, but Cloudflare's stated non-business-critical
positioning, revocable/no-liability free-service terms, finite quotas and hard
D1 failure behavior require owner and privacy/legal review before customer
data. No account, project, resource, deployment, or domain setting changed.

Sources checked: [Cloudflare plans](https://www.cloudflare.com/plans/),
[Self-Serve Subscription Agreement](https://www.cloudflare.com/terms/),
[Developer Platform terms](https://www.cloudflare.com/service-specific-terms-developer-platform/),
[Workers limits](https://developers.cloudflare.com/workers/platform/limits/),
[D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/),
[D1 limit enforcement notice](https://developers.cloudflare.com/changelog/post/2026-09-01-d1-free-tier-limit-enforcement/),
[Queues pricing](https://developers.cloudflare.com/queues/platform/pricing/), and
[Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/).
