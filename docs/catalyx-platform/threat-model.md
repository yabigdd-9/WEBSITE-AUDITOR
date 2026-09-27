# Local staging threat model

- **Date:** 2026-09-28
- **Scope:** The new `catalyx_web` public pages, account/session flow, tenant
  data, admin review, versioned API, and manual single-page audit adapter. This
  is a design and source review, not an independent penetration test.

## Assets

- Customer email addresses, password hashes, site origins, authorization
  receipts, audit states, and released reports.
- Administrator credentials, TOTP seeds, session cookies, CSRF tokens, and
  the review/activity history.
- The availability and integrity of the application database and local report
  queue.
- Internal network services and cloud metadata reachable from a future audit
  worker.

## Trust boundaries and abuse cases

| Boundary and attacker-controlled values | Abuse case | Staging controls | Remaining release gate |
| --- | --- | --- | --- |
| Browser to HTML/API: forms, JSON, identifiers, Origin, Host | CSRF, injection, oversized input, account probing, cross-tenant ID guessing | Request body cap; URL/form validation; parameterized SQLite; escaped output; CSP and security headers; same-site HTTP-only sessions; CSRF and optional Origin checks on ordinary mutations; one-time bearer tokens for verification/reset POSTs; neutral responses; tenant ID in customer queries; database-backed rate limits by client address and hashed normalized login address | Owner must approve thresholds and lockout behavior; verification/reset mail still has only per-IP rate limits and needs account-level delivery controls before hosted SMTP is enabled; verify client-IP handling behind selected host; external auth review, fixed public base URL, dependency/security review |
| Customer site submission to database | Register an internal/private target or leak paths/query credentials | Standard-port HTTP(S) only; userinfo and scoped IPv6 rejected; alternate numeric IP forms, malformed DNS labels, and non-global/reserved/multicast literals rejected; only normalized origin stored | Domain ownership/authorization proof and abuse operations remain product decisions |
| Admin browser to review state | Unauthorized approval, report release, customer lockout, or repudiation | Named role; admin sign-in requires TOTP; seeds use versioned AES-GCM encryption bound to workspace and user; role check on each route; CSRF; reasoned decisions; transactional activity record; synthetic SQLite key-rotation command | Production key delivery and coordinated rotation/backup rehearsal; lost-key recovery; admin recovery process, role provisioning lifecycle, alerts and tamper-evident log storage |
| Approved request to manual worker | DNS rebinding, private redirect, oversized response, crawling beyond scope, or stale worker publishing after reclaim/cancellation | Worker is opt-in manual only; fixed single-page profile; bounded A/AAAA resolution and public-unicast validation at connection time; vetted IP pinned to TCP; bounded method/ports/headers/body/time/request count; redirects rechecked; robots policy; sanitized report; schema v5 claim fencing; cooperative customer cancellation checked between response chunks; no automatic browser path | Separate process/container, independently enforced egress policy, quotas, concurrency control, durable queue and dead-letter operations, restore and abuse rehearsal. Customer web worker remains disabled. |
| Local staging mailbox and SQLite files | Read bearer links, customer account data, or reports from shared filesystem | Local files ignored by Git; database and mailbox mode `0600`; MFA seeds encrypted with a separate owner-only `*.totp-key` sidecar; reset/verification tokens are hashed in SQLite; links carry bearer token in URL fragment and JS submits it in request body | Production provider, database/report encryption and secret handling, backup lifecycle, data region, retention and deletion policy |
| Deployment configuration to app | Start an unsafe worker or enable unsupported production behavior | App startup fails closed for detected deployed environments; worker requires explicit local-only flag; customer submissions only enter review | Rework deployment-mode policy for a chosen staging and production provider; validate secrets/config at deploy time |

## STRIDE summary

- **Spoofing:** password sign-in, verified-email gate, TOTP for privileged
  accounts, opaque sessions. Hosted public registration is closed until an
  owner-approved mode is set. No external identity provider has been selected.
- **Tampering:** parameterized SQL, normalized inputs, transaction-scoped admin
  state changes, and a SHA-256 report hash computed when a worker stores the
  report. Release records copy that hash but do not recompute it; treat it as a
  recorded identifier, not tamper evidence. Local SQLite is not protected
  against a privileged filesystem attacker.
- **Repudiation:** high-impact admin decisions record account, role, reason,
  target and time in the same transaction. Local administrators can still
  modify SQLite directly; production needs protected log storage.
- **Information disclosure:** customer queries include workspace ownership;
  report JSON is omitted until release; error responses hide stack traces;
  scanner evidence is reduced to a small report shape. An account export is
  available after an approved privacy request. The service has no approved
  retention or deletion execution policy yet.
- **Denial of service:** form bytes, fetch time, response bytes, redirects,
  request count and per-workspace site/audit counts are bounded. Authentication
  rate limits are stored in the database for sharing across instances. Each
  login attempt now reserves the account bucket atomically before credential
  verification; a successful login clears it. The account threshold remains a
  provisional 12 attempts per normalized address per hour, alongside the
  8-per-minute client-address threshold. Distributed failures can still
  temporarily block a legitimate customer; owner-approved thresholds, live
  PostgreSQL behavior, and hosted client-IP handling remain unverified.
- **Elevation of privilege:** customer, support, reviewer, admin and owner
  permissions are checked server-side. Role changes are not exposed in the
  customer application; initial admin creation is a local CLI operation.

## Explicit non-goals for this slice

No customer scan starts from the public app. The manual scanner is not a safe
production worker until OS-level isolation and independent egress restrictions
are operating and tested. Billing, model calls, customer site changes,
deployment actions, hard deletion, scheduled retention, and backups are not
enabled. The app can send verification and password-reset messages when hosted
SMTP is configured; no runtime provider configuration was reviewed. The app
also implements customer export after an administrator-approved privacy
request, so export is available in source even though production policy and
data lifecycle approval remain open. Privacy requests are recorded and
reviewed; the UI does not claim they are complete.
