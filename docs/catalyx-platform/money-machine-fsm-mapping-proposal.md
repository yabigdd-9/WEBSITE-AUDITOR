# Catalyx / Money Machine workflow mapping proposal

Status: **proposal for owner review**. No FSM integration or customer-data
transfer is implemented by this document.

## Authority and boundaries

- Catalyx remains authoritative for customer identity, site ownership,
  authorization receipts, customer-visible audit state, report release, and
  deletion requests.
- Money Machine remains authoritative for its own prospect pipeline, leases,
  retries, operational evidence, and outreach approval state.
- The two applications use separate databases. Do not add a shared database or
  let either application's state update the other application's tables.
- A Catalyx audit event must never advance a Money Machine item to
  `QUALIFIED`, `APPROVED`, `READY_TO_SEND`, or `SENT`.
- Keep the bridge disabled by default. The first integration run must use a
  synthetic fixture and dry-run output.

## Proposed event mapping

| Catalyx `audit_requests.state` | Proposed Money Machine handling | Gate |
| --- | --- | --- |
| `authorization_review` | No event that creates work. Keep the request in Catalyx only. | Admin must approve the recorded customer authorization first. |
| `queued` | Emit one idempotent `audit_authorized` event; proposed MM entry state is `AUDIT_PENDING`. | Require the authorization receipt ID and current consent version. |
| `running` | Emit `audit_started` against the same external request ID; retain MM `AUDIT_PENDING`. | Lease token remains private to Catalyx. |
| `quality_review` | Emit `audit_completed`; advance the matching MM audit work to `AUDITED`. | A completed audit is not customer report release. |
| `released` | Emit `report_released` for traceability; keep MM at `AUDITED`. | Catalyx alone controls customer report visibility. No commercial qualification follows. |
| `failed` | Emit a failure event; use MM `RETRYABLE_FAILURE` only when the Catalyx retry policy permits another attempt, otherwise `NEEDS_REVIEW`. | Do not create a second request or exceed either system's retry ceiling. |
| `denied`, `cancelled`, `expired`, `withheld`, `deletion_pending`, `deleted` | Do not create new work. If an MM item already exists, suppress it or mark it for review; honor deletion and retention policy before retaining an event. | No requeue, report release, or outreach transition. |

This mapping separates a technical audit request from a commercial prospect.
Any later commercial qualification must be a separate, explicit owner-approved
workflow with independently sourced identity and contact provenance.

## Proposed bridge contract

1. Add a Catalyx transactional outbox written in the same transaction as each
   approved state change. Give every event an immutable event ID and the
   Catalyx request UUID as an idempotency key.
2. Consume events through an allowlisted local command or authenticated
   loopback bridge. Persist the last accepted event ID and payload digest in
   Money Machine so retries cannot duplicate work.
3. Include only the opaque request ID, event type, UTC timestamp, consent
   receipt ID/version, normalized site origin when needed for the audit, and a
   report digest. Never include account email, password, session/token, raw
   report, local path, or mail content.
4. Record bridge failures in a visible retry/dead-letter state. Reconciliation
   must be read-only by default and must not requeue customer work
   automatically.
5. Keep outbound customer actions, hosted model calls, and outreach transport
   disabled. A state event grants no authority to send, purchase, deploy, or
   release a report.

## Owner decisions before implementation

- Approve or revise the authority split, state table, and minimum event fields.
- Approve the retention/deletion behavior for event IDs and report digests.
- Select the local bridge execution identity and database ownership model.
- Decide whether `quality_review` should create an MM `AUDITED` item before
  Catalyx release, or whether integration should wait until `released`.

After approval, implementation needs migration backup, idempotency/replay
tests, cancellation/deletion tests, a synthetic end-to-end dry run, and a
separate security review. No production customer state should be copied during
that work.
