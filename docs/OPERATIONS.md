# Operations

Existing controls: [RUNBOOK](RUNBOOK.md), [cloud queue](cloud-prospect-pipeline.md).
Scheduled/manual jobs remain bounded; no continuous service is introduced.

The optional SQLite store serializes writers. The queue enforces <=3 attempts per
run, <=6 attempts per UTC day across committed state, and <=3 attempts per prospect
with one/two-hour backoff. `process(..., limit=..., daily_limit=...)` permits lower
budgets, including daily zero. Existing checkpoint audit events count toward the
daily budget, so switching formats does not reset committed usage. Interrupted,
uncommitted HTTP attempts cannot be counted reliably: use the existing single
workflow concurrency group and avoid manual restart loops. Budgets are per queue;
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
