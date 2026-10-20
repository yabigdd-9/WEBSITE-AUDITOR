# Worker root cause report

Current zero processing is explained by zero eligible jobs, not a demonstrated lease/registration failure. There are 27 human-review items, 327 rejected and 12 suppressed; no queue item is in a registered worker's input states. No automatic reactivation of these held decisions was performed.

Independent issues reproduced in disposable staging:

| Priority | Problem | Before | Repair |
|---|---|---|---|
| P0 | A leased oldest item consumes SELECT LIMIT, hiding the next eligible item | second worker claims zero despite eligible work | Apply lease predicate before LIMIT and recheck state/retry eligibility in conditional UPDATE |
| P0 | Rejected completion releases the lease and increments success before validation | APPROVED boundary rejected but success metric exists | Validate/advance, release and count inside one savepoint; roll back rejected outcomes |
| P0 | Late worker outcomes overwrite a newer owner's state/retry budget | stale complete and fail both mutate the item | Obtain write lock and require current unexpired ownership; stale worker loop logs lease loss without claiming success |

Four before regressions failed; after evidence is in `evidence/queue-after.txt` and `evidence/worker-supervisor.*`. Existing exponential backoff, max_attempts, dead-letter states and stale lease draining retained. Synthetic acceptance separately tests actual abandoned durable leases, restart and retry exhaustion.

The Hermes runner has separate problems: historical audit timeout outcomes, testing errors, and timeout returning exit 0 (source `ops/hermes_zero_token/runner.py`, primary lines 392–397). Its site-auditor dispatch uses unbounded `audit-backfill --no-delay` against its inherited root, despite a separate staging helper. These are owner-bound findings, not candidate repairs. The worker log labels cost as zero by construction; that is not independent host accounting.

SQLite writes remain serialized during handler execution; long handlers can hold locks and exceed the 300-second lease. Completion fencing prevents a stale state write, but cannot guarantee exactly-once external side effects or roll back every handler's filesystem output. Existing handlers must remain idempotent. No automatic live recovery attempted.
