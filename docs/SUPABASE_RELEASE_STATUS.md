# Supabase integration release status — 18 November 2026

The integration branch reconciles PR #107 and the locked connector preflight
from PR #110 with master `3bf061a`. It preserves the current activation gates,
escaped owner forms, crash-durable limits, schedule monitoring and checkpoint
restoration. The pinned psycopg dependency is declared once; both database
features use the same reviewed driver.

## Two explicit persistence modes

| Feature | Private schema | Restricted identity | GitHub Actions secret |
| --- | --- | --- | --- |
| Structured pipeline state, jobs and request reservations | `moneymachine` | `moneymachine_runner`, member of `moneymachine_worker` | `WA_POSTGRES_DSN` |
| Optional encrypted checkpoint mirror | `mm_internal` | `mm_pipeline_connector`, member of `mm_checkpoint_writer` | `WA_PG_DATABASE_URL` |

The mirror retains authenticated Fernet ciphertext. The structured store keeps
application records in private tables protected by database grants and forced
RLS; those records are not additionally encrypted by the application. The mirror
alone does not preserve the structured operational reservation ledger and must
not be substituted for a complete operational backup.

The live worker continues using its existing Actions checkpoint until a reviewed
cutover. Never point both implementations at a secret intended for the other,
bootstrap over existing state, delete failed reservations, or treat a successful
management-API query as an unattended worker connection.

## Hosted database observations

The selected `moneymachine` project (`srymerkhraklwuttzexi`) is ACTIVE_HEALTHY.
Read-only management queries confirmed:

- Twelve structured tables have RLS enabled and forced.
- Two encrypted-mirror tables have RLS enabled.
- `moneymachine_worker`, `moneymachine_reader`, `mm_checkpoint_writer` and
  `mm_pipeline_connector` have no login, superuser, create-database,
  create-role or bypass-RLS privileges.
- The connector belongs only to the checkpoint-writer group among the inspected
  application roles. `moneymachine_runner` has not yet been provisioned.
- The structured store contains one state, one event and one job, with zero
  prospects and zero request reservations. Existing records were left intact.
- The hosted security advisor returned no findings.

These observations establish schema and access preparation. No runtime DSN or
checkpoint key is present in this shell, and the GitHub connection has no tool
for creating repository Actions secrets or initiating a new workflow dispatch.
The required credential setup and hosted two-runner drill remain release gates.

## Validation

The combined local canonical suite, excluding the real Postgres module, passed
1,002 tests and 46 subtests, with seven optional browser/rendering skips. The
targeted offline/portal/access tests passed 61 tests and 22 subtests. Twelve
real-Postgres fixtures could not start because this shell disallows the required
socket creation; no test was changed to hide that limitation. The existing
GitHub `postgres-tests` job runs those tests on its supported Ubuntu runner,
including process crash, writer-lock recovery, reservation survival, duplicate
work prevention and private paired export/restore. Its result must be verified
on the integrated revision before merging.

## Remaining activation sequence

1. Configure a dedicated runner login and `WA_POSTGRES_DSN` through trusted
   administrator and GitHub secret settings. Preserve TLS `verify-full`, the
   selected project, port 5432 and the restricted worker group. Do not expose
   database passwords or the owner's report-decryption key in chat or logs.
2. Run **Private Postgres persistence verification** manually on the reviewed
   master revision. The first and second jobs use separate runners, preserve
   request-reservation counts and add only pause/control events. The selected
   database is already initialized; do not pass `--bootstrap`.
3. If using the optional mirror, separately activate its existing locked login,
   configure `WA_PG_DATABASE_URL`, and run **Supabase Connector Read-Only
   Preflight**. A known-good encrypted checkpoint and a full operational backup
   must be retained before any mirror import or authority change.
4. Verify backups, restored quota accounting and actual hosted connectivity
   before choosing one authoritative production store. Keep existing schedules
   working until a deliberate cutover is verified.
5. Configure independent monitoring after establishing a successful hosted-run
   baseline. The existing GitHub schedule-health job is useful but shares
   GitHub's scheduling dependency; it is not independent monitoring.

No production cutover, new database login, secret write, client outreach, paid
API call, paid upgrade or client website edit is included in this release.
