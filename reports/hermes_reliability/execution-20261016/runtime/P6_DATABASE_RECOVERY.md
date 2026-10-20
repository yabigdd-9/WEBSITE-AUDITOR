# P6 Database recovery — 16 October 2026

Status: **PASS** for fresh backup, isolated restore, rollback probe and scoped permissions; **BLOCKED** for production migration/promotion acceptance.

Machine-readable evidence: `database_recovery_receipt.json`, `database_permissions_receipt.json`, `runtime_inventory.json`. Reports contain aggregate counts, schemas by digest and paths, not customer rows, messages, credentials or vault note contents.

Eight distinct SQLite sources were identified and inspected before backup:

| Purpose | Source |
| --- | --- |
| Active MoneyMachine | `/Users/dd/WEBSITE-AUDITOR/database/money_machine.db` |
| Hermes staging copy | `/Users/dd/WEBSITE-AUDITOR/state/hermes_zero_token/staging/money_machine_staging.db` |
| Preserved legacy nested DB | `/Users/dd/WEBSITE-AUDITOR/money-machine/database/money_machine.db` |
| Hermes scheduler execution ledger | `/Users/dd/.hermes/cron/executions.db` |
| Hermes shared state | `/Users/dd/.hermes/shared-state.db` |
| Hermes kanban | `/Users/dd/.hermes/kanban.db` |
| Hermes projects | `/Users/dd/.hermes/projects.db` |
| Hermes sessions | `/Users/dd/.hermes/state.db` |

All eight: source connection `mode=ro`, `query_only=ON`, consistent read transaction, SQLite online backup API, independent restore through the same API, 45-second per-copy deadline and bounded inspection. Source, backup and restored schema digests/table counts match. Every integrity check returned `ok`; every FK violation count is zero. Every isolated restore passed a synthetic create/insert/rollback test. SHA-256 hashes for backup and restore are recorded; no raw copying of a live SQLite file was used. The active primary DB was open by PID 66896 during baseline collection. These are per-database consistent snapshots, not an atomic distributed transaction across eight databases.

Private artifacts: `/Users/dd/WEBSITE-AUDITOR/state/hermes_recovery/20261016/`, mode 0700; backup/restore files and private manifest mode 0600. Keep these out of Git, Obsidian and public artifacts. No expiry deletion was installed; retain this recovery set until replacement is independently accepted and retention is agreed. Free-space and retention automation remain operational requirements.

The source databases initially had broad 0644 access except Hermes sessions. After successful backups, live supervisor ownership was independently checked as PID 66896 / UID 501 (`dd`). Exactly 19 source paths were restricted: eight DBs, existing source sidecars and their direct directories. DBs/sidecars are 0600 and direct DB directories 0700; the full path list is in `database_permissions_receipt.json`. Original UID/GID/inode/modes were saved BEFORE chmod in private `permission_rollback_manifest.json`, mode 0600. This is a reversible access-control change; no business SQL writes, source restore, recursion, restart or migration occurred. A fresh post-repair read-only check confirmed primary/staging quick_check=ok, zero FK violations and mode0600 (`post_permissions_db_checks.json`).

Primary snapshot: 400 businesses, 7 audits, 46 evidence rows, 38 evidence metadata rows, 370 pipeline items, 378 mm_deals, 6 contact-evidence rows, 6 suppressions, 0 model-invocation rows, 0 send-ledger rows, 0 messages with sent_at, 0 payment/revenue rows in inspected ledgers. Aggregates are point-in-time, not proof that every evidence item is current or every contact is eligible.

State reconciliation: root `HERMES_EXECUTION_STATE.yaml` is absent in the inspected checkout and two direct .claude worktrees. `outputs/TOP_20_MONEY_ENGINES.md` exists and hashes identically in all three. Current `approval/APPROVAL_QUEUE.yaml` differs from both older worktree versions; the current file was preserved and no older queue was copied over it. The execution parent's new master state is a separate artifact.

Production restore procedure remains gated: stop/hold only the affected writer, verify the chosen private hash/integrity and target identity, preserve the current source, restore into an isolated candidate with the online API, validate intended migration and rollback, obtain worker-specific release acceptance, then perform a controlled promotion and verify integrity/FKs/counts. This run exercised only the isolated restore and rollback portion; it did not replace production data or validate an as-yet-unspecified production migration.
