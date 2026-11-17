-- Explicit opt-in owner migration. Not applied by GitHub CI or deployment.
-- Run only in the dedicated, reviewed Supabase "moneymachine" project.
-- This is a PRIVATE DATABASE schema: it is not in Supabase's exposed API schemas.
-- Secrets, customer data, and plaintext audit reports must never be inserted.

BEGIN;

CREATE SCHEMA IF NOT EXISTS mm_internal;
REVOKE ALL ON SCHEMA mm_internal FROM PUBLIC;
REVOKE ALL ON SCHEMA mm_internal FROM anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS mm_internal.encrypted_checkpoints (
    id text PRIMARY KEY CHECK (id = 'money_machine'),
    revision bigint NOT NULL CHECK (revision BETWEEN 1 AND 200),
    ciphertext bytea NOT NULL CHECK (octet_length(ciphertext) BETWEEN 100 AND 10000000),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    saved_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS mm_internal.encrypted_checkpoint_history (
    revision bigint PRIMARY KEY CHECK (revision BETWEEN 1 AND 200),
    ciphertext bytea NOT NULL CHECK (octet_length(ciphertext) BETWEEN 100 AND 10000000),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    saved_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- Defense in depth. API roles receive no USAGE on the private schema, no
-- table grants and no RLS policies. A future private database login must be
-- separately reviewed and granted only the minimum required privileges.
ALTER TABLE mm_internal.encrypted_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm_internal.encrypted_checkpoint_history ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA mm_internal FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA mm_internal FROM anon, authenticated, service_role;

COMMIT;
