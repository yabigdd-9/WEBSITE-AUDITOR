-- Separate from queue state: authentication never waits for an audit writer lock
-- or modifies prospect evidence, owner decisions, jobs or request reservations.
CREATE TABLE moneymachine.portal_sessions (
  token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  expires double precision NOT NULL CHECK (expires > 0 AND expires < 'Infinity'::double precision),
  csrf text NOT NULL CHECK (csrf ~ '^[A-Za-z0-9_-]{43}$'),
  auth_version text NOT NULL CHECK (auth_version ~ '^[0-9a-f]{64}$')
);
CREATE INDEX portal_session_expiry ON moneymachine.portal_sessions(expires);
CREATE TABLE moneymachine.portal_rate_limits (
  bucket text PRIMARY KEY CHECK (bucket ~ '^[0-9a-f]{64}$'),
  window_id bigint NOT NULL CHECK (window_id >= 0),
  attempts integer NOT NULL CHECK (attempts > 0 AND attempts <= 20)
);
CREATE INDEX portal_rate_window ON moneymachine.portal_rate_limits(window_id);

REVOKE ALL ON moneymachine.portal_sessions, moneymachine.portal_rate_limits
  FROM PUBLIC, anon, authenticated, service_role, moneymachine_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON moneymachine.portal_sessions,
  moneymachine.portal_rate_limits TO moneymachine_worker;
ALTER TABLE moneymachine.portal_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE moneymachine.portal_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE moneymachine.portal_rate_limits ENABLE ROW LEVEL SECURITY;
ALTER TABLE moneymachine.portal_rate_limits FORCE ROW LEVEL SECURITY;
CREATE POLICY private_session_access ON moneymachine.portal_sessions
  TO moneymachine_worker USING (true) WITH CHECK (true);
CREATE POLICY private_rate_access ON moneymachine.portal_rate_limits
  TO moneymachine_worker USING (true) WITH CHECK (true);
