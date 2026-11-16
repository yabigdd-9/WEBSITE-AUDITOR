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

Destination must be a new 0600 file outside the checkout. Backup runs SQLite's
integrity check. A restore test reopens the backup and compares state; automated
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
