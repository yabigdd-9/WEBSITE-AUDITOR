# Staging API contract

This contract describes the local staging API implemented under `/api/v1`. It
uses the same opaque, HTTP-only session cookie as the HTML application. The
browser receives the current CSRF token from `GET /api/v1/me`; every state
changing API request must send it as `X-CSRF-Token`. Same-origin requests are
required when an `Origin` header is present. There are no bearer tokens,
public job endpoints, general-purpose fetch endpoint, or customer scan options.

The unversioned health endpoints are `GET /api/health/live` for process
liveness and `GET /api/health/ready` for the local database and request-queue
readiness check. The older `GET /api/health` remains as a staging summary.

## Customer endpoints

| Method and path | Access | Purpose |
| --- | --- | --- |
| `GET /api/v1/me` | Verified signed-in account | Current user, role, workspace, and CSRF token |
| `GET /api/v1/sites` | Customer | Sites in the caller's workspace |
| `POST /api/v1/sites` | Customer + CSRF | Add a normalized public HTTP(S) site origin. JSON: `{ "url": "https://example.nz", "label": "Example" }` |
| `GET /api/v1/sites/{site_id}` | Owning customer | Site and its request summaries |
| `POST /api/v1/sites/{site_id}/audits` | Owning customer + CSRF | Record the fixed-profile authorization statement. JSON: `{ "authorized": true }`; also requires `Idempotency-Key` (or JSON `idempotency_key`). The result enters `authorization_review`; it does not start a scan. |
| `GET /api/v1/audits` | Customer | Requests in the caller's workspace |
| `GET /api/v1/audits/{audit_id}` | Owning customer | State and report, with `report: null` until an administrator releases it |
| `POST /api/v1/audits/{audit_id}/cancel` | Owning customer + CSRF | Cancel a request awaiting authorization review, queued, or running. A running worker's claim is invalidated and its transport checks cancellation cooperatively. |

## Administrator endpoints

| Method and path | Access | Purpose |
| --- | --- | --- |
| `GET /api/v1/admin/overview` | Owner, admin, or reviewer + MFA-authenticated session | State counts and worker status |
| `GET /api/v1/admin/audits` | Owner, admin, or reviewer + MFA-authenticated session | Review queue; optional `state` filter |
| `POST /api/v1/admin/audits/{audit_id}/decision` | Owner, admin, or reviewer + CSRF | Approve or deny a request with a reason. Approval only queues it for the manual staging worker. JSON: `{ "decision": "approve", "reason": "..." }` |
| `POST /api/v1/admin/audits/{audit_id}/report-decision` | Owner, admin, or reviewer + CSRF | Release or withhold a quality-reviewed report with a reason. JSON: `{ "decision": "release", "reason": "..." }` |

Support accounts have no access to review endpoints. Cross-workspace IDs
return `404`; role violations return `403`; missing sessions return `401`;
invalid request bodies return `400` or `415`; policy and rate limits return
`429`. Responses do not include internal paths, stack traces, secrets, or
unreleased report data.

The API is an early staging contract, not a production compatibility promise.
Authentication uses the local staging implementation. Production provider,
database, OpenAPI publication, rate-limit storage, and worker queue remain
release decisions.
