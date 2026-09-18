-- Hunter.io enrichment — external corroboration source.
-- Additive migration. Legacy data untouched.
-- Apply via: python3 -m money_machine.hunter_cli migrate

CREATE TABLE IF NOT EXISTS hunter_schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, sql_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS hunter_enrichment(
  id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id),
  email TEXT NOT NULL, normalized_email TEXT NOT NULL,
  source_type TEXT NOT NULL DEFAULT 'hunter_enrichment',
  source_url TEXT, source_excerpt TEXT, observed_at TEXT NOT NULL,
  candidate_method TEXT NOT NULL DEFAULT 'hunter_domain_search',
  status TEXT NOT NULL CHECK(status IN ('OBSERVED','CANDIDATE','VERIFIED_HIGH','VERIFIED_MEDIUM','UNVERIFIED','REJECTED','SUPPRESSED')),
  hunter_confidence INTEGER NOT NULL DEFAULT 0 CHECK(hunter_confidence BETWEEN 0 AND 100),
  hunter_sources TEXT NOT NULL DEFAULT '[]',
  hunter_first_name TEXT, hunter_last_name TEXT,
  hunter_position TEXT, hunter_department TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(business_id, normalized_email)
);
CREATE INDEX IF NOT EXISTS hunter_enrichment_business ON hunter_enrichment(business_id);
CREATE INDEX IF NOT EXISTS hunter_enrichment_email ON hunter_enrichment(normalized_email);
CREATE INDEX IF NOT EXISTS hunter_enrichment_status ON hunter_enrichment(status);
