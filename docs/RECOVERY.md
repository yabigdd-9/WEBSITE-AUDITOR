# Recovery

Existing encrypted artifact recovery remains documented in
[cloud-prospect-pipeline.md](cloud-prospect-pipeline.md) and
[ENCRYPTED_REPORT_VAULT.md](ENCRYPTED_REPORT_VAULT.md). Owner private report keys
remain only on trusted owner devices. State checkpoint keys are a separate design.

For SQLite, stop competing writers and use the online backup API on a trusted host:

```python
from pathlib import Path
from scripts.pipeline_store import PipelineStore
store = PipelineStore(Path('/private/durable/pipeline.sqlite3'))
store.backup(Path('/private/backup/pipeline-2026-11-16.sqlite3'))
restored = PipelineStore(Path('/private/backup/pipeline-2026-11-16.sqlite3')).read()
```

Destination must be a new 0600 file outside the checkout. Backup creates both
the main file and matching .operations.sqlite3 file and runs integrity checks. A restore test reopens the backup and compares state; automated
synthetic tests perform this exercise. No hosted restore has been verified.

To migrate an existing encrypted checkpoint, decrypt on a trusted device with its
existing symmetric key using `cloud_prospect_pipeline.unseal`, then bootstrap a
new PipelineStore transaction and update that state with the restored document.
Do not migrate the report-vault private key. Preserve the original ciphertext.
Stop the old scheduler before switching so two stores do not process the same queue.
Verify prospective counts, attempt history and suppression before resuming.

Never bootstrap over an existing database, silently reset history, or automatically
fall back to an older checkpoint. Recover by selecting an intact private backup,
recording the source and known lost interval, and reconciling attempts/decisions.
Rotation, deletion and archive retention need explicit owner policy; automatic
purging is not implemented. Action artifacts expire after 30 days and are not the
indefinite archive. Additional archive storage remains unactivated.

## Interrupted jobs and quota recovery

State remains transactional, while the private operational ledger reserves
requests before HTTP. Interrupted work can repeat only within the remaining
reserved limits; it does not refund consumed capacity. A writer automatically
classifies an orphan running job once it owns the main SQLite lock. A committed
job marker distinguishes a successful queue commit from an interrupted commit.
No continuously running supervisor or remote service is required for this logic.

Preserve/restore the **pair** `pipeline.sqlite3` + `pipeline.operations.sqlite3`.
`PipelineStore.backup` writes `backup.sqlite3` + `backup.operations.sqlite3`.
A backup taken during work may conservatively include newer reservations than
queue state; it must never grant extra capacity. For exact operational snapshots,
stop writers before backup. Validate counts, suppression, proposal/project hashes
and both integrity checks after restore. Synthetic tests exercise restoration
and quota preservation, including failed first bootstrap and killed workers.

A missing required ledger, corrupt database, schema mismatch or capacity limit
blocks processing. Restore an intact pair; do not silently recreate the ledger,
bootstrap over lost records, trim history or reset quotas. If no intact recovery
copy exists, reconcile the loss privately and obtain a deliberate recovery plan.
Failed/interrupted attempts may have incomplete audit results; their reserved
capacity is not evidence of a website defect.

Pause a private-host invocation using `--paused`, or reduce audit budgets using
`--max-audits 1 --daily-limit 2`. Resume by removing pause/reducing flags as
appropriate. Paused runs cannot import outcome changes. To stop an already
running job, stop/cancel its process; changing a future schedule does not cancel
current execution. The Actions emergency switch/cancellation procedure remains
unchanged. No new scheduler has been installed.

## Indexed encrypted reports

Schema v4 database backups preserve the report index and immutable audit links,
not ciphertext files. Back up the dedicated private archive directory separately
with its 0700 directory and 0600 file permissions. Preserve the existing paired
pipeline/operations database backup procedure. Test restored ciphertext checksums
and owner-side authenticated decryption on the trusted device before relying on
a backup. Synthetic tests verify index restore and a real vault round trip; no
owner archive recovery has been production-verified.

A failed database commit after ciphertext publication can leave an unindexed
file. Repeating the same import safely reuses its checksum; inspect unmatched
files privately before any owner-directed cleanup. Missing/altered files block
download. Expiry does not erase data: follow the owner's retention decision for
secure deletion and backup removal; there is no automatic deletion or retention
extension service. Lost private keys cannot be recovered from this index; use
the owner's separate trusted key backup. Do not upload keys to recover service.
