-- MoneyMachine Database Schema
-- Source: ~/MoneyMachine/database/money_machine.db
-- Generated: 2026-09-07T19:05:23.122236+00:00

-- Tables
CREATE TABLE industries (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  region TEXT,
  market_notes TEXT,
  pain_score REAL DEFAULT 0 CHECK (pain_score BETWEEN 0 AND 100),
  ability_to_pay_score REAL DEFAULT 0 CHECK (ability_to_pay_score BETWEEN 0 AND 100),
  recurring_revenue_score REAL DEFAULT 0 CHECK (recurring_revenue_score BETWEEN 0 AND 100),
  total_score REAL DEFAULT 0 CHECK (total_score BETWEEN 0 AND 100),
  evidence TEXT,
  last_reviewed TEXT,
  frontend_weakness_score REAL DEFAULT 0,
  backend_pain_score REAL DEFAULT 0,
  competition_score REAL DEFAULT 0,
  build_ease_score REAL DEFAULT 0
);

CREATE TABLE businesses (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  industry_id INTEGER REFERENCES industries(id),
  region TEXT,
  public_website TEXT,
  source TEXT NOT NULL,
  discovered_at TEXT NOT NULL,
  current_status TEXT NOT NULL CHECK (current_status IN ('discovered','audited','scored','offer_drafted','human_review','approved','rejected')),
  is_dummy INTEGER NOT NULL DEFAULT 0 CHECK (is_dummy IN (0,1))
);

CREATE TABLE audits (
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  mobile_quality REAL,
  conversion_quality REAL,
  quote_flow REAL,
  booking_flow REAL,
  seo_basics REAL,
  trust_signals REAL,
  page_speed REAL,
  accessibility REAL,
  broken_paths TEXT,
  follow_up_quality REAL,
  crm_signal REAL,
  automation_opportunities TEXT,
  evidence TEXT NOT NULL,
  opportunity_score REAL CHECK (opportunity_score BETWEEN 0 AND 100),
  created_at TEXT NOT NULL
);

CREATE TABLE experiments (
  id INTEGER PRIMARY KEY,
  hypothesis TEXT NOT NULL,
  target_segment TEXT,
  variable TEXT,
  expected_result TEXT,
  actual_result TEXT,
  decision TEXT,
  lesson TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE projects (
  id INTEGER PRIMARY KEY,
  client_business_id INTEGER REFERENCES businesses(id),
  scope TEXT NOT NULL,
  repository TEXT,
  status TEXT NOT NULL,
  estimated_hours REAL,
  actual_hours REAL,
  delivery_date TEXT,
  qa_status TEXT,
  rollback_plan TEXT
);

CREATE TABLE revenue (
  id INTEGER PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  quoted_nzd REAL NOT NULL DEFAULT 0,
  invoiced_nzd REAL NOT NULL DEFAULT 0,
  collected_nzd REAL NOT NULL DEFAULT 0,
  recurring_mrr_nzd REAL NOT NULL DEFAULT 0,
  costs_nzd REAL NOT NULL DEFAULT 0,
  gross_margin_nzd REAL GENERATED ALWAYS AS (collected_nzd - costs_nzd) VIRTUAL
);

CREATE TABLE product_signals (
  id INTEGER PRIMARY KEY,
  repeated_problem TEXT NOT NULL,
  occurrence_count INTEGER NOT NULL DEFAULT 1,
  customers_affected INTEGER NOT NULL DEFAULT 0,
  willingness_to_pay_evidence TEXT,
  build_reusability REAL,
  productization_score REAL CHECK (productization_score BETWEEN 0 AND 100),
  next_test TEXT,
  last_updated TEXT NOT NULL
);

CREATE TABLE agent_runs (
  id INTEGER PRIMARY KEY,
  task TEXT NOT NULL,
  agent TEXT NOT NULL,
  model TEXT,
  cost_nzd REAL NOT NULL DEFAULT 0 CHECK (cost_nzd >= 0),
  duration_seconds REAL,
  output_quality REAL,
  outcome TEXT,
  failure_reason TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE approval_events (
  id INTEGER PRIMARY KEY,
  action_type TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id INTEGER,
  requested_at TEXT NOT NULL,
  approved INTEGER NOT NULL DEFAULT 0 CHECK (approved IN (0,1)),
  approved_by TEXT,
  approved_at TEXT,
  notes TEXT
);

CREATE TABLE pipeline_events (
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  stage TEXT NOT NULL,
  event_at TEXT NOT NULL,
  detail TEXT NOT NULL
);

CREATE TABLE offers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  business_id INTEGER,
  problem TEXT NOT NULL,
  proposed_outcome TEXT NOT NULL,
  implementation_scope TEXT NOT NULL,
  price_test REAL,
  estimated_delivery_effort REAL,
  expected_value REAL,
  offer_score REAL DEFAULT 0,
  draft TEXT NOT NULL DEFAULT '',
  external_send_approved INTEGER DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT '',
  FOREIGN KEY (business_id) REFERENCES businesses(id)
);

CREATE TABLE outreach (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  offer_id INTEGER,
  draft TEXT NOT NULL,
  approved_by_human INTEGER DEFAULT 0,
  sent_at TEXT,
  reply_status TEXT,
  reply_class TEXT,
  next_action TEXT,
  unsubscribe_status TEXT,
  FOREIGN KEY (offer_id) REFERENCES offers(id)
);

CREATE TABLE data_quality_flags (
  id INTEGER PRIMARY KEY,
  object_type TEXT NOT NULL,
  object_id INTEGER NOT NULL,
  flag TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  resolved INTEGER NOT NULL DEFAULT 0 CHECK (resolved IN (0,1)),
  UNIQUE(object_type, object_id, flag)
);

CREATE TABLE contacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  business_id INTEGER,
  contact_name TEXT,
  role TEXT,
  address_or_channel TEXT,
  source TEXT,
  contact_permission_basis TEXT,
  do_not_contact INTEGER DEFAULT 0,
  last_verified TEXT,
  FOREIGN KEY (business_id) REFERENCES businesses(id)
);

CREATE TABLE mm_holds (
  business_id INTEGER PRIMARY KEY REFERENCES businesses(id),
  reason TEXT NOT NULL
);

CREATE TABLE mm_evidence (
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  url TEXT NOT NULL,
  observation TEXT NOT NULL,
  limitation TEXT NOT NULL,
  checked_at TEXT NOT NULL
);

CREATE TABLE mm_messages (
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  evidence_id INTEGER NOT NULL REFERENCES mm_evidence(id),
  recipient TEXT NOT NULL,
  body TEXT NOT NULL,
  digest TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL CHECK(kind IN ('initial','followup')),
  parent_id INTEGER REFERENCES mm_messages(id),
  created_at TEXT NOT NULL,
  approved_hash TEXT,
  approved_by TEXT,
  approval_ref TEXT,
  permission_basis TEXT,
  sent_at TEXT,
  send_receipt TEXT,
  reply TEXT,
  UNIQUE(parent_id)
);

CREATE TABLE mm_suppression (
  address TEXT PRIMARY KEY,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE mm_cash (
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
  receipt TEXT NOT NULL UNIQUE,
  received_at TEXT NOT NULL
);

CREATE TABLE mm_events (
  id INTEGER PRIMARY KEY,
  event_at TEXT NOT NULL,
  action TEXT NOT NULL,
  business_id INTEGER,
  detail TEXT NOT NULL
);

CREATE TABLE mm_deals (
  business_id INTEGER PRIMARY KEY REFERENCES businesses(id),
  stage TEXT NOT NULL DEFAULT 'DISCOVERED' CHECK(stage IN ('DISCOVERED','VERIFIED','AUDITED','QUALIFIED','DRAFT_READY','AWAITING_APPROVAL','APPROVED_TO_SEND','SENT','REPLIED','CALL_OR_DISCOVERY','PROPOSAL_READY','PROPOSAL_SENT','WON','LOST','SUPPRESSED')),
  next_action TEXT NOT NULL DEFAULT 'Verify website and contact permission',
  due TEXT,
  updated_at TEXT NOT NULL
);

-- Indexes (none explicitly defined beyond PRIMARY KEY and UNIQUE constraints)

-- Triggers
CREATE TRIGGER prevent_unapproved_outreach_insert
BEFORE INSERT ON outreach
WHEN NEW.sent_at IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'external send blocked: create draft first and obtain per-message human approval');
END;

CREATE TRIGGER prevent_unapproved_outreach_send
BEFORE UPDATE OF sent_at, approved_by_human ON outreach
WHEN NEW.sent_at IS NOT NULL AND (
  COALESCE(NEW.approved_by_human, 0) != 1 OR
  NOT EXISTS (
    SELECT 1 FROM approval_events
    WHERE action_type = 'external_send'
      AND object_type = 'outreach'
      AND object_id = NEW.id
      AND approved = 1
  )
)
BEGIN
  SELECT RAISE(ABORT, 'external send blocked: per-message human approval event required');
END;

CREATE TRIGGER prevent_unapproved_mm_messages_send
BEFORE UPDATE OF sent_at ON mm_messages
WHEN NEW.sent_at IS NOT NULL AND (
  OLD.approved_hash IS NULL OR
  OLD.approved_hash != OLD.digest OR
  OLD.approval_ref IS NULL
)
BEGIN
  SELECT RAISE(ABORT, 'external send blocked: exact-message approval required');
END;

CREATE TRIGGER prevent_unapproved_mm_messages_insert
BEFORE INSERT ON mm_messages
WHEN NEW.sent_at IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'external send blocked: create draft first, then review and record approval');
END;

-- Views (none defined)
