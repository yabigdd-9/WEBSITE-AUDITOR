# Persistent pipeline storage

The existing local MoneyMachine DB, toolkit History and offline review ledger are
preserved. `scripts.pipeline_store.PipelineStore` adds a **separate private SQLite
DB** for the existing cloud queue. It is opt-in, not a hosted deployment.

Schema migrations 0 -> 2 and 1 -> 2 are transactional (`PRAGMA user_version=2`). Unknown
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
