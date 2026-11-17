-- Private normalized store for the existing bounded single-owner pipeline.
-- No public RPC, public tables, passwords, buckets or runtime activation.
CREATE SCHEMA moneymachine;
REVOKE ALL ON SCHEMA moneymachine FROM PUBLIC, anon, authenticated, service_role;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('moneymachine_worker','moneymachine_reader')) THEN
    RAISE EXCEPTION 'Reserved application roles already exist; review before migration';
  END IF;
  CREATE ROLE moneymachine_worker NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  CREATE ROLE moneymachine_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
END $$;
GRANT moneymachine_worker, moneymachine_reader TO postgres;
GRANT USAGE ON SCHEMA moneymachine TO moneymachine_worker, moneymachine_reader;

CREATE TABLE moneymachine.schema_version (
  singleton integer PRIMARY KEY CHECK(singleton=1), version integer NOT NULL CHECK(version=1)
);
INSERT INTO moneymachine.schema_version VALUES(1,1);
CREATE TABLE moneymachine.metadata (
  singleton integer PRIMARY KEY CHECK(singleton=1), body jsonb NOT NULL,
  last_committed_job text
);
CREATE TABLE moneymachine.prospects (
  id text PRIMARY KEY CHECK(id ~ '^[0-9a-f]{64}$'), domain text NOT NULL UNIQUE,
  body jsonb NOT NULL CHECK(body->>'domain'=domain)
);
CREATE TABLE moneymachine.audit_runs (
  audit_id text PRIMARY KEY, prospect_id text NOT NULL REFERENCES moneymachine.prospects(id),
  sequence integer NOT NULL UNIQUE CHECK(sequence >= 0), body jsonb NOT NULL
);
CREATE INDEX audit_prospect ON moneymachine.audit_runs(prospect_id);
CREATE TABLE moneymachine.events (sequence integer PRIMARY KEY CHECK(sequence >= 0), body jsonb NOT NULL);
CREATE TABLE moneymachine.business_events (
  sequence integer PRIMARY KEY CHECK(sequence >= 0), event_id text NOT NULL UNIQUE,
  prospect_id text NOT NULL REFERENCES moneymachine.prospects(id), body jsonb NOT NULL
);
CREATE INDEX business_event_prospect ON moneymachine.business_events(prospect_id);
CREATE TABLE moneymachine.discovery_candidates (
  id text PRIMARY KEY, domain text NOT NULL UNIQUE,
  prospect_id text REFERENCES moneymachine.prospects(id), body jsonb NOT NULL
);
CREATE INDEX discovery_prospect ON moneymachine.discovery_candidates(prospect_id);
CREATE TABLE moneymachine.discovery_events (
  sequence integer PRIMARY KEY CHECK(sequence >= 0),
  candidate_id text NOT NULL REFERENCES moneymachine.discovery_candidates(id), body jsonb NOT NULL
);
CREATE INDEX discovery_event_candidate ON moneymachine.discovery_events(candidate_id);
CREATE TABLE moneymachine.report_artifacts (
  id text PRIMARY KEY, ciphertext_sha256 text NOT NULL UNIQUE CHECK(id=ciphertext_sha256), body jsonb NOT NULL
);
CREATE TABLE moneymachine.audit_artifact_links (
  sequence integer PRIMARY KEY CHECK(sequence >= 0), artifact_id text NOT NULL REFERENCES moneymachine.report_artifacts(id),
  audit_id text NOT NULL REFERENCES moneymachine.audit_runs(audit_id), body jsonb NOT NULL,
  UNIQUE(artifact_id,audit_id)
);
CREATE INDEX artifact_link_audit ON moneymachine.audit_artifact_links(audit_id);
CREATE TABLE moneymachine.jobs (
  id text PRIMARY KEY, started double precision NOT NULL, finished double precision,
  status text NOT NULL CHECK(status IN ('running','succeeded','failed','interrupted'))
);
CREATE INDEX job_started ON moneymachine.jobs(started DESC);
-- Reservations deliberately do not reference transactional prospects/audits:
-- their charge must survive when the main queue transaction rolls back.
CREATE TABLE moneymachine.reservations (
  job_id text NOT NULL REFERENCES moneymachine.jobs(id), audit_id text NOT NULL,
  prospect_id text NOT NULL, day text NOT NULL CHECK(day ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
  PRIMARY KEY(job_id,audit_id)
);
CREATE INDEX reservation_day ON moneymachine.reservations(day);
CREATE INDEX reservation_prospect ON moneymachine.reservations(prospect_id);

REVOKE ALL ON ALL TABLES IN SCHEMA moneymachine FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON ALL TABLES IN SCHEMA moneymachine TO moneymachine_worker, moneymachine_reader;
GRANT INSERT, UPDATE ON moneymachine.metadata, moneymachine.prospects,
  moneymachine.discovery_candidates, moneymachine.jobs TO moneymachine_worker;
GRANT INSERT ON moneymachine.audit_runs, moneymachine.events, moneymachine.business_events,
  moneymachine.discovery_events, moneymachine.report_artifacts,
  moneymachine.audit_artifact_links, moneymachine.reservations TO moneymachine_worker;

DO $$
DECLARE tab text;
BEGIN
  FOR tab IN SELECT tablename FROM pg_tables WHERE schemaname='moneymachine'
  LOOP
    EXECUTE format('ALTER TABLE moneymachine.%I ENABLE ROW LEVEL SECURITY',tab);
    EXECUTE format('ALTER TABLE moneymachine.%I FORCE ROW LEVEL SECURITY',tab);
    EXECUTE format('CREATE POLICY worker_access ON moneymachine.%I TO moneymachine_worker USING (true) WITH CHECK (true)',tab);
    EXECUTE format('CREATE POLICY owner_read ON moneymachine.%I FOR SELECT TO moneymachine_reader USING (true)',tab);
  END LOOP;
END $$;
ALTER DEFAULT PRIVILEGES IN SCHEMA moneymachine REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA moneymachine REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated, service_role;

