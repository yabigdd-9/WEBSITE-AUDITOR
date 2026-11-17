# Shared pipeline and hosted owner dashboard

This change prepares a hosted Python dashboard against the existing private
Postgres adapter. It does not claim that production data has been imported or a
remote dashboard has been deployed. It depends on the Postgres integration in
PR #107. The selected hosted database currently has zero prospect rows; the
operational queue remains in encrypted GitHub checkpoints until a verified
cutover. Do not substitute sample records for the owner's saved queue.

## Runtime

Run `uvicorn auditor_toolkit.hosted_portal:create_hosted_app --factory` behind a
TLS ingress. The container in `deploy/owner-dashboard/Dockerfile` binds port
8000 as an unprivileged user. The host must support Python, direct/session
Postgres connections, runtime secrets, and TLS. Configure only the ingress's
actual trusted proxy addresses in `FORWARDED_ALLOW_IPS`; do not use `*` for an
internet-reachable process. Requests whose ASGI scheme is not HTTPS or whose
Host differs from the configured origin are rejected, including spoofed
forwarded-proto headers from an untrusted caller.

Required private runtime settings:

| Setting | Purpose |
| --- | --- |
| `WA_POSTGRES_DSN` | Existing adapter's dedicated runner identity, selected project, port 5432 and `sslmode=verify-full&sslrootcert=system`; never a superuser connection |
| `WA_PORTAL_ORIGIN` | One exact HTTPS origin, with no trailing slash, path or wildcard |
| `WA_PORTAL_PASSWORD_HASH` | Owner's Argon2id hash; generate on a trusted device and place in host secrets |
| `WA_PORTAL_AUTH_PEPPER_B64` | Base64 of a fresh random 32-byte value, stored as a host secret |
| `WA_PORTAL_SESSION_SECONDS` | Optional 300–86400 seconds; default 3600 |

Generate credentials on a trusted device and configure them through the provider's
secret manager. Do not paste passwords, DSNs, peppers or private report keys in
chat, source, image layers, environment examples, public logs or Actions inputs.
The dashboard never needs the report-decryption private key or checkpoint key.
Do not enable a paid plan or use a personal-only hosting allowance for this
commercial application without reviewing the provider's terms and owner cost
authorization. No plan has been upgraded by this change.

## Cutover order

1. Integrate and verify dependencies and this change on `master`. Retain the
   current successful encrypted checkpoint and the existing recovery key.
2. Review/apply the additional `hosted_portal_auth` migration to the selected
   private database. Its sessions/rate limits use RLS and server-role-only
   privileges. It grants no public or generic authenticated access.
3. Configure the dedicated `moneymachine_runner` login/session endpoint through
   a trusted secret channel. Set `WA_POSTGRES_DSN` in GitHub and the dashboard
   host. It must target this same database in both places.
4. Execute the existing two-independent-runner Postgres verification workflow.
   Review its actual job results; green offline tests are not hosted access.
5. Keep the dashboard offline during cutover. Dispatch **Import verified
   checkpoint into private Postgres** on `master` with the latest successful
   durable worker run ID. The shared workflow concurrency prevents another
   worker running during the import. The source must be the newest actual
   trusted worker; failed/running newer workers, expired archives, stale sources,
   occupied business state or existing request reservations block the import.
   Ciphertext is decrypted only in the trusted temporary runner directory.
6. Verify real prospect/audit/draft counts and suppression, then set repository
   variable `WA_PIPELINE_STORAGE=postgres`. Default remains `checkpoint`.
   This is an explicit authority switch: unknown backends, missing imports or
   unavailable Postgres fail without falling back to another store.
7. Run and inspect a bounded production continuation. Postgres is now the
   common authority for owner decisions and workers. It retains encrypted
   snapshot and paired state/job/reservation exports as Actions artifacts.
   Only after this passes should the owner dashboard be exposed through its
   HTTPS ingress. Verify login, real records, exact-version approval, restart
   persistence and logout as the owner on a mobile browser.

Do not silently merge two active business databases. The initial import permits
only an initialized destination with no business records or reservations. Setup
events are preserved ahead of source history. An identical source import is
idempotent; a different subsequent source requires explicit reviewed recovery.
Historical events, approvals, projects and suppression remain immutable under
the existing pipeline transition checks. Repeated approval of the same exact
version/reason by the same actor does not duplicate the decision.

## Authentication and recovery

Hosted login reuses the existing Argon2 owner password approach. Sessions and
write/login rate limits are stored separately from the queue so a long audit
writer does not block session reads. Raw session tokens and client IP addresses
are not stored. Cookies use the `__Host-` prefix, Secure, HttpOnly and SameSite
strict. Unsafe requests require the configured Origin and CSRF token. GETs do
not change business state or send anything. Credential/pepper rotation invalidates
old sessions. Logout is shared across replicas. Limits are fixed UTC-minute
buckets (5 login attempts/address, 20 globally, 20 writes/session), with bounded
row/session counts. Deploy ingress rate limits as appropriate for the host.

Postgres exports include business state, jobs and charged reservations from one
consistent locked snapshot. They intentionally exclude login sessions; restored
owners log in again. Preserve encrypted paired exports outside expiring Actions
storage under the existing retention/recovery policy before relying on them as
a long-term backup. Do not infer permanent archive retention from a 30-day file.
The snapshot carries `storage_authority=postgres`: checkpoint-mode execution
rejects it because a state-only snapshot cannot replace crash-durable quotas.
Use the paired Postgres restore path on an empty migrated destination; do not
flip storage flags or bootstrap to erase failed attempts or owner decisions.

## Verification boundary

Local shell database tests are blocked by this environment's socket policy.
The dedicated **Hosted owner dashboard and checkpoint cutover tests** workflow
runs disposable real PostgreSQL, imports synthetic five-prospect/four-audit/
one-proposal state, and checks application restart, approvals, project records,
shared logout/rate limits, denied public access, ciphertext recovery and paused
worker continuity with zero request reservations or external sends. These are
test fixtures, not evidence that the real saved queue is already in Supabase.

Production deployment remains blocked until runtime credentials and an eligible
Python host are configured. Existing Vercel team discovery reports Hobby; no
commercial hosting entitlement or paid activation was assumed.
