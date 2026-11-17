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
    revision bigint NOT NULL CHECK (revision BETWEEN 1 AND 24),
    ciphertext bytea NOT NULL CHECK (octet_length(ciphertext) BETWEEN 100 AND 8000000),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    saved_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS mm_internal.encrypted_checkpoint_history (
    revision bigint PRIMARY KEY CHECK (revision BETWEEN 1 AND 24),
    ciphertext bytea NOT NULL CHECK (octet_length(ciphertext) BETWEEN 100 AND 8000000),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    saved_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- A NOLOGIN group role allows the owner to grant just these privileges to a
-- separately provisioned login, without putting any password in migrations.
-- Nothing runs automatically and no admin/service_role bypass is needed.
DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mm_checkpoint_writer') THEN
        CREATE ROLE mm_checkpoint_writer NOLOGIN;
    END IF;
END
$role$;
GRANT USAGE ON SCHEMA mm_internal TO mm_checkpoint_writer;
GRANT SELECT, INSERT, UPDATE
    ON mm_internal.encrypted_checkpoints TO mm_checkpoint_writer;
GRANT SELECT, INSERT
    ON mm_internal.encrypted_checkpoint_history TO mm_checkpoint_writer;

-- Defense in depth. API roles receive no USAGE on the private schema and no
-- table grants; only the dedicated writer group can access sealed checkpoints.
ALTER TABLE mm_internal.encrypted_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm_internal.encrypted_checkpoint_history ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA mm_internal FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA mm_internal FROM anon, authenticated, service_role;

CREATE POLICY mm_checkpoints_writer_policy
    ON mm_internal.encrypted_checkpoints FOR ALL TO mm_checkpoint_writer
    USING (true) WITH CHECK (true);
CREATE POLICY mm_checkpoint_history_writer_policy
    ON mm_internal.encrypted_checkpoint_history FOR ALL TO mm_checkpoint_writer
    USING (true) WITH CHECK (true);

COMMIT;
