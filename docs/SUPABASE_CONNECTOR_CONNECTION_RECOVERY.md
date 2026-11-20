# Supabase connector DATABASE_CONNECTION recovery (owner-only)

## Evidence
Read-only preflight run 44529140021 on master (84d314c1) emitted
`SUPABASE_PREFLIGHT_BLOCKED: DATABASE_CONNECTION`. This is a network/connection
class, **not** proof of a bad password or bad role grant. Previous management
queries verified connector LOGIN, expected table privileges, and zero mirrored
checkpoints. Those queries do not prove GitHub runner connectivity.

## Likely IPv4 incompatibility
Supabase documents that the direct `db.<project-ref>.supabase.co:5432` endpoint
typically uses IPv6; GitHub-hosted Actions runners are among platforms that
may not support that path. Supavisor **session pooler** supports IPv4 and
port **5432**. Source:
https://supabase.com/docs/guides/platform/ipv4-address

## Owner-only remediation (never paste DSN/password into PR, issue or chat)
1. In the project's Supabase **Connect** dialog, select **Session pooler**.
   Copy the actual project-specific hostname, username suffix and port.
   Do not invent the pooler region or endpoint.
2. Ensure the database user is the restricted `mm_pipeline_connector`, not
   `postgres`. For the pooler the username must be
   `mm_pipeline_connector.srymerkhraklwuttzexi`; the host must be the
   project's genuine `*.pooler.supabase.com` hostname and port 5432.
3. Keep `sslmode=verify-full` and configure a trusted certificate chain as
   needed for the actual pooler endpoint. Do **not** weaken to `require`,
   `prefer`, `disable` or `verify-ca` just to get a green check.
4. Update only GitHub Actions secret `WA_PG_DATABASE_URL` through GitHub's
   protected Secrets UI. Preserve `WA_PIPELINE_STATE_KEY` and the production
   Actions checkpoint. Never repurpose `WA_POSTGRES_DSN` (structured store).
5. Manually run **Supabase Connector Read-Only Preflight** on `master`.
   A successful result must show `read_only_preflight: PASS` and
   `writes_performed: 0`, `worker_switched: false`.
6. If still blocked, inspect only the fixed diagnostic category and determine
   DNS/TCP/TLS/authentication via a separately reviewed redacted probe.
   Do not enable production mirror writes or switch the authoritative store.

## Release gates
No paid IPv4 add-on, database password rotation, RLS relaxation, new database
role, outreach, external paid model, checkpoint overwrite, or production cutover
is authorized by this document. Full two-runner recovery and rollback tests
remain required before PR #107 or any state-authority change.
