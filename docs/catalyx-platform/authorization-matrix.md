# CatalyxLabs Website Auditor authorization matrix

- **Status:** Source-derived local review; route-role tests cover the listed
  routes, but this is not an independent security review.
- **Reviewed:** 2026-09-28

## Role groups in the current source

| Role | Customer workspace | Review queue and audit decisions | Customer account support | Operations, privacy review, activity |
|---|---|---|---|---|
| `customer` | Own workspace only | None | None | None |
| `support` | None | None | Read customer list and detail; cannot disable accounts | None |
| `reviewer` | None | Read queue, sites, jobs, request details; approve/deny requests; release/withhold reports; retry eligible failed requests | None | No operations, privacy-request, or activity access |
| `admin` | None | Same review permissions | Read customer list/detail; disable customer accounts | Operations, privacy-request review, and activity access |
| `owner` | None | Same review permissions | Read customer list/detail; disable customer accounts | Operations, privacy-request review, and activity access |

Owner and admin are equivalent in the current route checks. There is no
customer-facing role-change or administrator-promotion endpoint. Initial
administrator creation is a local CLI/database operation and still needs a
production provisioning and recovery procedure.

## Guarded route families

| Route family | Allowed role(s) | Source behavior |
|---|---|---|
| `/app/**`, `/api/v1/sites/**`, `/api/v1/audits/**` | `customer` | Signed-in membership and customer role required; customer queries filter by workspace. |
| `/admin`, `/admin/audits/**`, `/admin/sites`, `/admin/jobs`, `/api/v1/admin/**` | `owner`, `admin`, `reviewer` | Review queue and report actions; mutations also require CSRF and a reason. |
| `/admin/customers`, `/admin/customers/{id}` | `owner`, `admin`, `support` | Read account status, site list, and audit history. |
| `POST /admin/customers/{id}/disable` | `owner`, `admin` | Disable a customer, revoke sessions, and record an activity reason. |
| `/admin/operations`, `/admin/privacy-requests/**`, `/admin/activity` | `owner`, `admin` | Read operational state and privacy/admin records; identity review, export approval, and decline are role-gated, reason-recorded actions. Deletion completion is not available. |
| `POST /app/settings/privacy-requests/{id}/export` | Owning `customer` | Requires an approved access/export request and CSRF; returns only the customer's account records and already-released reports, records the download, and closes the request. Other users receive `404`. |
| `/register`, `/login`, `/verify`, `/resend-verification`, `/forgot-password`, `/reset-password` | Public before authentication | Verification and recovery tokens are one-time and hashed at rest; resend and recovery responses avoid disclosing whether an account exists. SMTP is only used after explicit configuration. |

## Evidence and limits

`toolkit_tests/test_catalyx_web.py::test_admin_route_role_matrix` exercises
positive and negative role outcomes for the listed review, customer-support,
operations, privacy, activity, and mutation routes using synthetic accounts.
Existing tests cover tenant isolation, report-release visibility, successful
owner workflows, and reviewer access boundaries. A permitted role reaching a
missing record returns `404`; this proves the role guard passed, but it is not
proof of a successful state transition. Live PostgreSQL behavior, deployed
identity/session revocation, workspace data lifecycle, and an independent role
review remain open release gates.
