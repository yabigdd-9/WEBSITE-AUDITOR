# Canonical audit Evidence Bridge

Stage-signal completeness (`evidence_completeness`) still measures which signals
exist for the current pipeline decision. An `AUDITED` event can supply that
signal even when its saved report is missing. The separate `audit_evidence`
field measures the saved canonical report; it does not change scoring,
qualification, next-best-evidence recommendations, or pipeline state.

## Status and reporting

`./mm evidence-status ID` inspects one business. Without an ID it summarizes all
real businesses. These reads do not initialize or migrate databases/history.
Prospect intelligence, intelligence summaries, operator metrics/dashboard and
daily reports include canonical status separately from legacy observations.
Legacy counter names remain compatible; new explicit names identify legacy
observations and eligible prospects without current canonical captures.

| Status | Meaning |
| --- | --- |
| CURRENT | Complete, fresh static report with an immutable local hash anchor. |
| RECOVERABLE | Saved report validates but has no local bridge anchor yet. |
| MISSING | No canonical capture or saved report is missing. |
| STALE | Run or underlying fetch observation is older than seven days. |
| PARTIAL | Required static checks did not all complete successfully. |
| INVALID | Identity, schema, coverage, timestamp, path or hash validation failed. |
| EXCLUDED | Dummy, rejected, suppressed, unsubscribed contact or unresolved hold. |

`complete=true` applies only to CURRENT. Every canonical capture retains
`independently_verified=false` and `claim_status=unverified`: it cannot grant
consent, approve an outreach message or certify a commercial claim.

Validation requires the current report schema, static profile, exact normalized
website host/path/query, canonical run ID and JSON path, successful required
static checks, and all declared non-JSON artifact manifest hashes and sizes.
Report JSON receives its own SHA-256 anchor because the toolkit manifest does
not hash its own JSON. Both run and original fetch observation must be within
seven days, without future dates. A fresh run cannot renew stale cached source
observations. Newer history or audit-event captures supersede older reports,
including when the newer capture is partial, stale or missing. Replaying a
delayed event cannot renew its older capture time. Selection examines all
canonical audit events and exact-site history, so unrelated history volume or
event arrival order cannot hide a newer failed capture. Incompatible evidence
schemas and unorderable history capture timestamps return INVALID.

## Deterministic saved-report recovery

Recovery makes no network requests, scans or model calls. Preview first:

```text
./mm evidence-recover --ids 123 456
```

It inspects the latest saved canonical event, local bridge anchor and read-only
toolkit history using exact website matching. Review the statuses and paths.
MISSING, STALE, PARTIAL and INVALID results require a new audit or artifact
repair; recovery never guesses a finding or bypasses a failed check.

Apply the reviewed explicit IDs:

```text
./mm evidence-recover --ids 123 456 --apply
```

To validate an explicitly identified existing report for one business:

```text
./mm evidence-recover --ids 123 --report /absolute/toolkit/RUN_ID/report.json
./mm evidence-recover --ids 123 --report /absolute/toolkit/RUN_ID/report.json --apply
```

`--apply` requires explicit IDs. Each report is revalidated before writing; the
original capture timestamp is retained. Repeating the same run is a no-op.
Changed bytes for an already anchored run require a new audit run; preview
checks the same existing anchor before reporting that a run is recoverable.
Selecting an unchanged older anchor remains a no-op and preserves the latest
capture's status. Recovery
does not insert legacy `mm_evidence`, alter deal/pipeline stages, clear holds,
rescore prospects, invalidate approvals, modify messages or contact records.

## Schema and worker integration

The first successful registration adds only the `mm_audit_evidence` table and
append-only triggers inside a savepoint. It stores business/run identity,
report path/hash, original capture time, registration time and rule version.
The unique business/run key and insert/update/delete guards prevent replacement.
Existing schemas, records and stage events are preserved. Reads work before the
table exists; schema initialization runs only on successful eligible writes.
Registration rechecks exclusions inside the write savepoint, including changes
that arrived while validating report files.

The audit worker, status and recovery share the selected `MM_ROOT` toolkit
directory. The worker validates fresh saved reports before reuse, registers valid
ones, and adds the report hash to its existing stage-event projection. Invalid
cached captures trigger the existing deterministic static audit with AI,
browser rendering and external tools disabled. Exclusions are checked before
history initialization, network or database writes. Legacy audit-backfill and
contact discovery now use the same early exclusion guard while retaining their
honest unverified-observation behavior. They also recheck exclusions after
fetching, inside a savepoint and before saving capture files or database rows.

## Regression validation

The bridge tests use disposable SQLite databases and saved synthetic reports,
including a real toolkit report built with an injected offline fetcher. Coverage
includes unchanged stage completeness; current, missing, stale, partial,
tampered and wrong-site reports; latest-run supersession; cached observation
age; delayed event replay; high-volume unrelated history; malformed schemas and
timestamps; read-only preview; idempotent recovery; preserved timestamps, stages and
approvals; append-only replacement; concurrent exclusion changes; selected data
roots; and every rejection/suppression source.
Legacy evidence tests no longer require a copy of the live database or public
unreachable-site probes. CI includes the bridge, reporting and evidence suites.
