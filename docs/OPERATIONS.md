# Operations

Existing controls: [RUNBOOK](RUNBOOK.md), [cloud queue](cloud-prospect-pipeline.md).
Scheduled/manual jobs remain bounded; no continuous service is introduced.

The optional SQLite store serializes writers. The SQLite queue enforces <=3 attempts per
run, <=6 attempts per UTC day including durable reservations, and <=3 attempts per prospect
with one/two-hour backoff. `process(..., limit=..., daily_limit=...)` permits lower
budgets, including daily zero. Existing checkpoint audit events count toward the
daily budget, so switching formats does not reset committed usage. SQLite-mode interrupted attempts remain charged in its paired operational
ledger. Checkpoint-only mode retains the existing fail-closed artifact recovery
and committed-event limits; use its single workflow concurrency group and avoid
manual restart loops. Budgets are per queue;
the separate scheduled allowlist workflow retains its own pre-existing limits.

Failures/partial audits retain status/version/time/retry/failure category in
`audit_runs`; incomplete scans never produce a draft. Provenance fields from
reviewed intake are retained; missing identity/category/location stay unknown.
Logs contain aggregate counts only. Raw exceptions and detailed findings remain
private. Review recent error codes and retry counts rather than assuming a green
workflow means every audit completed.

Emergency stop: disable WA_PIPELINE_ENABLED and cancel active Actions jobs.
For a private host, stop its scheduler/process; no new host scheduler is installed.
Suppression stays sticky and clears drafts. Reaching a history/size cap blocks
processing; preserve a backup and perform an owner-reviewed retention migration.

System health now includes recent private job states and charged daily capacity
from the operational ledger. These are bounded scheduled/transactional jobs,
not an always-on process. Use CLI --paused, --max-audits (1-3), --daily-limit
(0-6) for explicit controls; invalid budgets fail before work. Existing Actions
activation is unchanged, and no DB-backed workflow is enabled by this code.

## Encrypted report index operations

Use the explicit trusted-device import in ENCRYPTED_REPORT_VAULT.md. The portal's
Audit reports view distinguishes available, expired, missing, corrupt and
unconfigured local custody; its source link does not check GitHub availability.
No import runs on page load. Health identifies local custody separately from
unverified hosted storage. Database backups require a separate ciphertext
directory backup. Monitor the 50 MB/1,000-file local cap and act before GitHub's
30-day expiry; no automated source download or hosted archive is activated.
