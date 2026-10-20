# Automatic operator export candidate

Status: prepared source only. Not regression tested, installed, or promoted.
The approved 92 identity/contact/metadata/local-demo checks do not cover this change.

## Proposed behaviour

The existing supervisor invokes one presentation export after a worker cycle,
at most once every 60 seconds. It also invokes the export while the disk guard
pauses processing. No second supervisor or persistent exporter is introduced.
An export can delay the next worker cycle by up to 20 seconds. Its failure is
reported separately and does not intentionally terminate the worker loop.

The child is owned by its invoking parent. The supervisor kills and reaps that
child on shutdown or timeout. The child's independent deadline/parent check is
intended to cover abrupt parent loss. These paths need regression evidence.

The export performs these independently reported stages:

1. Maintain only root metrics.jsonl/errors.jsonl archives.
2. Maintain worker-logs JSONL archives.
3. Save health, metrics, changed error snapshots, dead-letter queue and worker
   heartbeat files using existing read-only database access.
4. Refresh the existing Obsidian presentation vault.

Automatic exports do not probe SearXNG: its probe submits a search. The manual
health/snapshot API retains its existing probe default. No model requests,
approvals, queue transitions, migrations, pricing decisions or outreach are
added by the exporter.

## Reporting accuracy

Failure counts use RETRYABLE_FAILURE and PERMANENT_FAILURE, the states stored by
the actual pipeline, rather than a nonexistent DEAD_LETTER state.
Dead-letter export filters failures before the row limit, reports total_count
and truncated, and therefore does not lose failures behind a large healthy queue.
The returned count still means the number of exported rows.

Unchanged error snapshots are deduplicated by a hash excluding generated_at.
The cursor is updated after appending. A crash between these steps may append
the same snapshot again on retry; exact-once logging is not claimed.

## Retention scope

Defaults: compress JSONL files larger than 50 MiB; remove matching gzip archives
older than 30 days. Compression streams in 64 KiB chunks. JSONL appenders and
rotation share a directory lock acquired before opening files. Source identity,
size and modification time are checked before replacement.

Only matching module or legacy archive names are eligible for expiry. Unknown
gzip files, symlinks and unrelated state journals are excluded. At the state
root an explicit allowlist selects metrics.jsonl and errors.jsonl. Soak samples,
soak control and acceptance evidence are not selected.

No retention operation has been run by this candidate.

## Presentation authority

The exported master plan comes from MASTER_PLAN.yaml, includes its source hash,
and is labelled as requirements rather than completion. Saved companion reports
include their source modification time and a historical-status warning.
The vault cannot authorize sends, change approvals or become database authority.
Existing saved daily/KPI prose remains historical; automatic export does not
recompute those reports or claim that they are current.

## Regression evidence required before promotion

- Isolated database fixture: actual failure states, pending retries, empty queue,
  failure entries beyond the first 1,000 healthy rows, total/truncated counts,
  and no database writes.
- Snapshot export: automatic probe suppression, explicit manual probe behaviour,
  fresh worker files, repeated-error deduplication, malformed cursor recovery.
- Supervisor child: success, nonzero exit, exception, 20-second timeout, orderly
  shutdown, abrupt parent loss, no duplicate owner, and continued worker cycles.
- Retention in disposable directories: content-preserving compression, expiry
  boundaries, allowed filenames, symlink exclusion, concurrent append/rotation,
  source change preservation and lock release after failure.
- Vault fixtures: all canonical YAML leaves retained, source hash and dates,
  malformed YAML failure, historical companion fallback and preserved authority.
- Existing supervisor/reporting/observability/Obsidian regression coverage.

All fixtures must use an isolated MM_ROOT and vault. Live runtime and soak files
remain outside the test scope. Static checks alone are not promotion evidence.
