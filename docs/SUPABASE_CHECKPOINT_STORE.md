# Optional encrypted PostgreSQL checkpoints for MoneyMachine

## Current state

The owner-approved Supabase free project `moneymachine` (project reference
`srymerkhraklwuttzexi`, Sydney region) is confirmed ACTIVE_HEALTHY but **has
no application tables**. The existing GitHub Actions worker already restores and
uploads an encrypted 30-day `pipeline-state` artifact on successful runs.

This module is a **separate, opt-in durable mirror prototype**. Merely merging
the code does **not** configure the Supabase schema, create a database login,
send customer messages, store live data, or replace the existing Actions worker.
The PostgreSQL store has no mail, billing, deployment or prospect discovery
functions.

## Security design

- Only authenticated, sealed Fernet checkpoint bytes go into PostgreSQL.
  Before a write, the existing state key decrypts locally in memory and the
  bounded pipeline state validator runs. **The key and plaintext never enter
  the database or logs.**
- The migration `deploy/postgres/001_encrypted_checkpoints.sql` creates a
  private `mm_internal` schema, not a Supabase public/PostgREST schema.
  `anon`, `authenticated`, `service_role` and `PUBLIC` receive no schema
  or table grants. Both tables use row-level security.
- An `mm_checkpoint_writer` **NOLOGIN** group role receives the minimum
  SELECT/INSERT/UPDATE rights and narrowly scoped RLS policies. A separate
  owner-provisioned login must be created later and granted that role. Do not
  use `postgres` or `supabase_admin` as the application login.
- Connections require `sslmode=verify-full`, correct project hostname (or
  pooler username suffix) and a dedicated login. Host override, Unix sockets,
  plaintext TLS and mismatched projects fail closed.
- Revision **0** is the initial, explicit import. Each subsequent write
  requires the exact observed revision. A transaction-level advisory lock,
  compare-and-swap check and version history prevent silent lost updates.
- Up to 24 revisions and 8 MB sealed state per revision (worst-case ~192 MB
  of ciphertext before database overhead, pending actual free-tier limits). No automatic
  deletion/pruning. Exhaustion blocks writes pending an owner-approved
  retention/backup plan.
- A read verifies the SHA-256 digest and authenticates the encrypted token
  before creating a new private `0600` output file. Existing files are not
  overwritten.

## How to prepare an initial deployment

1. Keep the currently working GitHub Actions encrypted checkpoint process
   enabled. Obtain and secure a current, known-good checkpoint and verify its
   existing restore path **before** attempting any migration.
2. Review the migration and project mapping, including the `mm_internal`
   schema and grants. Apply the SQL only to `srymerkhraklwuttzexi` **after
   independent owner approval**. Do not apply to unrelated projects.
3. Set up a dedicated database login on a trusted admin channel; grant it
   membership in `mm_checkpoint_writer`. Grant nothing to public API roles.
   The login secret must be stored as a GitHub Actions secret or another
   approved secret store; never commit it, include it in workflow output or
   paste it into ChatGPT.
4. Install optional dependencies locally: `pip install -e '.[vault,postgres]'`.
   Provide `WA_PG_DATABASE_URL` (dedicated login with TLS `verify-full`),
   `WA_SUPABASE_PROJECT_REF`, and the existing checkpoint key
   `WA_PIPELINE_STATE_KEY` in the trusted process environment.
5. With a verified **encrypted** input file, use:

       python -m scripts.supabase_checkpoint_store put \
         --sealed-file /path/to/pipeline-state.enc \
         --expected-revision 0

   It returns a revision number, no domain names or plaintext. For later
   writes read the current revision and use that as `--expected-revision`.
6. Independently restore and validate the same token:

       python -m scripts.supabase_checkpoint_store get \
         --output /private/location/recovered-state.enc

   Decrypt and validate it using the existing trusted worker recovery procedure
   **outside public CI output**. Compare content hashes and test a stale
   revision: the write must be refused without losing earlier history.

## Important limitations / release gates

**This is not production deployment**. The GitHub worker has NOT been switched
to this Postgres mirror. Both mechanisms must not independently claim authority;
switching over requires explicit owner selection of a **single** checkpoint
source and a tested recovery/rollback plan. The operational quota ledger from
the staged platform must also be preserved before HTTP work to avoid resets
after crashes. Do not bolt this simple checkpoint store into the live queue
without those stronger protections.

The Supabase free project can pause or run into storage, egress and database
limits. A green unit test does not prove network access, private-role RLS,
durability across independent runners, backups, actual cost, or remote dashboard
availability. These gates require a controlled database smoke test and an
owner-approved migration/credential setup. **No fees, card charges, paid model
calls, customer outreach, or real business records are required for offline
verification.**
