# Persistent pipeline storage

The existing local MoneyMachine DB, toolkit History and offline review ledger are
preserved. `scripts.pipeline_store.PipelineStore` adds a **separate private SQLite
DB** for the existing cloud queue. It is opt-in, not a hosted deployment.

Schema migrations 0/1/2 -> 3 are transactional (`PRAGMA user_version=3`). Unknown
versions and existing unrelated schemas are refused rather than overwritten.

| Table | Identity / purpose |
| --- | --- |
| metadata | singleton; queue schema version and non-row metadata |
| prospects | hashed canonical domain PK, unique domain, bounded JSON record |
| audit_runs | audit ID PK, prospect FK, attempt status/version/retries/evidence references |
| system_events | ordered append-only operational event JSON |
| business_events | sequence PK, unique event ID, prospect FK, owner-attested outcome JSON |
| discovery_candidates | canonical domain PK/hash, unique domain, optional reviewed-prospect FK, metadata/provenance JSON |
| discovery_events | ordered append-only source-content hash, candidate FK, import timestamp/run/status |

Detailed current audit findings/draft text remain within the prospect JSON as
produced by the existing queue. This is deliberately an incremental schema:
separate findings, opportunities, proposal_versions, artifacts and projects are
still backlog items, not implemented SQL tables. Audit metadata includes an
explicit null encrypted artifact reference until a real archive is registered.
No report private encryption key is stored. SQLite is plaintext at rest; it must
live on a trusted owner-controlled encrypted filesystem, never public artifacts.

All state changes are one `BEGIN IMMEDIATE` transaction spanning queue selection
and processing. Other writers time out before requests. The last commit survives
exceptions/process crashes. A crash during an HTTP request can cause that audit
to be repeated after restart; exactly-once network fetching is not guaranteed.
Audit/system/business history cannot be rewritten or truncated by the adapter.
Prospect removal uses lifecycle status; a worker cannot clear suppression.
Foreign keys and unique constraints fail atomically. JSON state is capped at
5 MB, 100 prospects plus 100 discovery candidates, and 10,000 events/attempts/outcomes/discovery events each. Pagination is bounded
to 100 records; query text is bound, not interpolated.

Database paths reuse review_ledger's existing private-location controls:
`.sqlite3`, outside the checkout, no symlink leaf, 0600, existing private parent.
There is no multi-user DB role model or RLS in SQLite; only the trusted owner OS
account may open it. Do not expose SQLite directly to remote users.

Tests cover independent-process persistence, transaction/FK rollback, process
crash, concurrent writers, schema mismatch, paths/permissions, idempotent retries,
daily quotas, immutable history, pagination and backup restore. These tests do
not verify a persistent cloud volume or hosted database.

Discovery is a separate pending-review pool. Source imports never create audit
queue rows. The existing curated/NZBN/OSM normalization is reused; cloud intake
adds HTTPS/domain guards before URL normalization. Existing www alias identity
merges discovery duplicates, while reviewed audit URLs and prior queue IDs stay
unchanged. A candidate links only to an independently reviewed allowlist prospect;
ambiguous links fail. Sources/first-seen and history cannot be discarded.

Structured opportunities, proposal_versions, current proposal_version and
recommendation_reviews now persist within each prospect's JSON record, in the
same transaction as the audit state. Old proposal bodies and review decisions
are append-only. Separate normalized tables for those records remain backlog
work; do not confuse the logical records with already-migrated SQL tables.

Version-bound proposal/message approvals, outreach_drafts/outreach_events and
suppression_events persist as append-only prospect JSON histories. Message
permission checks are owner-attested inputs; no report private key or raw
recipient address is needed by the sandbox. SQL-normalized approval/outreach
tables remain a possible migration, not a claim about the current schema.

Client projects and their immutable acceptance/frozen proposal, tasks, milestones
and append-only project_events also persist in prospect JSON. Completed evidence
and accepted task scope cannot be changed by the adapter. No invoices, payments
or client credentials are created by project tracking. Separate client_projects
SQL normalization remains a future migration.

## Operational ledger and schema v3

The main DB now requires its adjacent `<stem>.operations.sqlite3` ledger. Its
separate schema v1 contains `jobs` (running/succeeded/failed/interrupted) and
`reservations` (job/audit/prospect hash, UTC day, unique job+audit). Reservations
commit before HTTP and survive a queue rollback or process death. No domains,
contacts, draft text, credentials or encryption keys are copied into that ledger.

The main metadata records that the ledger is required before first bootstrap
requests, and records the last committed job. Missing ledger files block reads/
processing rather than recreating a zero budget. A subsequent writer, after
acquiring the existing main writer lock, classifies prior running jobs using the
committed-job marker. Readers still see the last committed queue state. Job
completion interrupted after commit is repaired as succeeded rather than falsely
reported as a lost queue commit.

Caps include legacy committed attempts plus reservations, without double counting
committed audit IDs: <=3 per job, <=6 per UTC day and <=3 per prospect in this
queue generation. Failed/interrupted reservations are not refunded. Both jobs
and reservations have 10,000-row caps requiring owner archival. Lower budgets
are supported; a run paused via CLI records only the control event.

The backup API now creates a pair with matching stems. Keep/restore both files.
Older binaries refuse schema v3; do not roll back the schema or delete the quota
ledger to resume work. Private parent directories must not be group/other
writable, preventing replacement of private files by another account.

## Schema v4: encrypted report references

`report_artifacts` stores a unique ciphertext SHA-256, bounded byte count, existing
vault format, recorded GitHub run/artifact IDs, creation/source expiry/local
retention timestamps and envelope-only verification status. `audit_artifact_links`
uses a composite primary key with foreign keys to reports and audit runs. Links
preserve the audit's original status/canonical run ID and owner review record.
Existing immutable audit snapshots are not rewritten. Index metadata and links
are append-only through the store. Migrations from v1-v3 preserve earlier records.
No key or decrypted report is stored. Ciphertext remains outside the database.

## Private PostgreSQL schema v1

The opt-in Postgres adapter uses the same validated business document and
immutable transition rules as SQLite v4. Schema `moneymachine` contains
`schema_version`, `metadata`, `prospects`, `audit_runs`, `events`, `business_events`,
`discovery_candidates`, `discovery_events`, `report_artifacts`,
`audit_artifact_links`, `jobs`, and `reservations`. Canonical domains/checksums
are unique; relational records retain foreign keys; explicit audit sequence
preserves append order. Bodies remain JSONB to reuse canonical evidence,
proposal, approval and project records without competing implementations.

A session advisory lock covers selection through state commit. Operational jobs
and request reservations commit on a separate connection, so interrupted work
cannot refund request limits. Reservations intentionally do not reference the
uncommitted prospect/audit rows; job references remain enforced. Committed-job
markers repair interrupted job finalization. Limits remain 3 requests/run,
6/day, 3/prospect and 10,000 operational/history records.

RLS is enabled and forced on every table, with policies for explicit private
worker/reader groups. These groups are NOLOGIN. No public Data API schema or RPC
was added. Runtime login provisioning is a separate secure configuration step.
