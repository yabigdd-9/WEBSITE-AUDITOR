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
