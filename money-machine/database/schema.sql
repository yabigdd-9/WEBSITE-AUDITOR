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

-- NEW TABLES FOR CAMPAIGN MANAGEMENT AND SOURCE QUALITY ACCOUNTING
CREATE TABLE campaign_configs (
  id INTEGER PRIMARY KEY,
  campaign_id TEXT NOT NULL UNIQUE,
  name TEXT,
  description TEXT,
  config TEXT NOT NULL,  -- JSON configuration
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE source_quality_metrics (
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  evidence_sources_count INTEGER DEFAULT 0,
  unique_evidence_sources INTEGER DEFAULT 0,
  duplicate_business_records INTEGER DEFAULT 0,
  pipeline_history_length INTEGER DEFAULT 0,
  total_research_time_seconds INTEGER DEFAULT 0,
  is_data_stale INTEGER DEFAULT 0,  -- boolean as integer
  quality_score REAL DEFAULT 0 CHECK (quality_score BETWEEN 0 AND 100),
  latest_update TEXT,
  measured_at TEXT NOT NULL
);

CREATE TABLE campaign_businesses (
  id INTEGER PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  assigned_at TEXT NOT NULL,
  last_researched TEXT,
  research_allocation INTEGER DEFAULT 180,  -- seconds per business
  FOREIGN KEY (campaign_id) REFERENCES campaign_configs(campaign_id),
  UNIQUE(campaign_id, business_id)
);

-- Indexes
CREATE INDEX idx_businesses_region ON businesses(region);
CREATE INDEX idx_businesses_industry_id ON businesses(industry_id);
CREATE INDEX idx_audits_business_id ON audits(business_id);
CREATE INDEX idx_mm_evidence_business_id ON mm_evidence(business_id);
CREATE INDEX idx_mm_messages_business_id ON mm_messages(business_id);
CREATE INDEX idx_offers_business_id ON offers(business_id);
CREATE INDEX idx_outreach_offer_id ON outreach(offer_id);
CREATE INDEX idx_contacts_business_id ON contacts(business_id);
CREATE INDEX idx_source_quality_business_id ON source_quality_metrics(business_id);
CREATE INDEX idx_campaign_businesses_campaign_id ON campaign_businesses(campaign_id);
CREATE INDEX idx_campaign_businesses_business_id ON campaign_businesses(business_id);
CREATE INDEX idx_campaign_configs_campaign_id ON campaign_configs(campaign_id);

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
-- OPPORTUNITY TRACKING TABLES
CREATE TABLE opportunity_tracking (
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  opportunity_type TEXT NOT NULL,
  discovery_angle TEXT NOT NULL,  -- problem_led, strength_led, change_led
  confidence_score REAL NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
  discovery_timestamp TEXT NOT NULL,
  pipeline_state TEXT NOT NULL,  -- current pipeline state
  campaign_id TEXT,
  recipe_id TEXT,
  supported_signals TEXT,  -- JSON array
  evidence_sources TEXT,   -- JSON array of evidence IDs
  shortlist_eligible INTEGER NOT NULL DEFAULT 0 CHECK (shortlist_eligible IN (0,1)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE opportunity_evidence (
  id INTEGER PRIMARY KEY,
  opportunity_id INTEGER NOT NULL REFERENCES opportunity_tracking(id),
  evidence_type TEXT NOT NULL,  -- problem_indicator, explicit_complaint, etc.
  evidence_data TEXT NOT NULL,  -- JSON with evidence details
  source_url TEXT,
  timestamp TEXT NOT NULL,
  relevance_score REAL NOT NULL CHECK (relevance_score BETWEEN 0 AND 1),
  created_at TEXT NOT NULL
);

CREATE TABLE pipeline_transitions (
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  from_state TEXT NOT NULL,
  to_state TEXT NOT NULL,
  transition_reason TEXT NOT NULL,
  transition_actor TEXT NOT NULL,  -- worker_id or system component
  evidence TEXT,  -- JSON evidence for transition
  timestamp TEXT NOT NULL,
  loop_transition INTEGER NOT NULL DEFAULT 0 CHECK (loop_transition IN (0,1))  -- 1 if transition between loops
);

-- Indexes for opportunity tracking
CREATE INDEX idx_opportunity_tracking_business_id ON opportunity_tracking(business_id);
CREATE INDEX idx_opportunity_tracking_pipeline_state ON opportunity_tracking(pipeline_state);
CREATE INDEX idx_opportunity_tracking_shortlist ON opportunity_tracking(shortlist_eligible);
CREATE INDEX idx_opportunity_evidence_opportunity_id ON opportunity_evidence(opportunity_id);
CREATE INDEX idx_pipeline_transitions_business_id ON pipeline_transitions(business_id);
CREATE INDEX idx_pipeline_transitions_timestamp ON pipeline_transitions(timestamp);
CREATE INDEX idx_pipeline_transitions_loop ON pipeline_transitions(loop_transition);
