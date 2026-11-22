-- MoneyMachine Schema v1 (Core Tables Only)
-- Email system tables are managed by separate migrations (003_email_finder_v2.sql etc.)

-- Core business tables
CREATE TABLE IF NOT EXISTS businesses(id INTEGER PRIMARY KEY, name TEXT NOT NULL, public_website TEXT, region TEXT, source TEXT, discovered_at TEXT NOT NULL, current_status TEXT NOT NULL, is_dummy INTEGER DEFAULT 0);

-- Demo QA table (referenced by triggers)
CREATE TABLE IF NOT EXISTS mm_demo_qa(business_id INTEGER PRIMARY KEY REFERENCES businesses(id), path TEXT NOT NULL, file_hash TEXT NOT NULL, score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100), checks_json TEXT NOT NULL, passed INTEGER NOT NULL CHECK(passed IN (0,1)), checked_at TEXT NOT NULL);

-- Experiments table (referenced by triggers and intelligence module)
CREATE TABLE IF NOT EXISTS mm_experiments(id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id), message_id INTEGER NOT NULL UNIQUE REFERENCES mm_messages(id), industry TEXT NOT NULL, problem TEXT NOT NULL, offer TEXT NOT NULL, price_band TEXT NOT NULL, style TEXT NOT NULL, demo_type TEXT NOT NULL, variant TEXT NOT NULL, created_at TEXT NOT NULL);

-- Model invocations table (referenced by intelligence module)
CREATE TABLE IF NOT EXISTS mm_model_invocations(id INTEGER PRIMARY KEY, run_key TEXT NOT NULL UNIQUE, model TEXT NOT NULL, provider TEXT NOT NULL, purpose_hash TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('blocked','started','failed','completed')), model_calls INTEGER NOT NULL DEFAULT 0 CHECK(model_calls>=0), input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL NOT NULL DEFAULT 0 CHECK(cost_usd=0), created_at TEXT NOT NULL, finished_at TEXT, error TEXT);

-- Jobs table (referenced by intelligence module)
CREATE TABLE IF NOT EXISTS mm_jobs(job_key TEXT PRIMARY KEY, kind TEXT NOT NULL, business_id INTEGER REFERENCES businesses(id), state TEXT NOT NULL CHECK(state IN ('pending','running','failed','completed')), checkpoint TEXT NOT NULL DEFAULT '{}', attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3), lease_until TEXT, updated_at TEXT NOT NULL, error TEXT);

-- Events table (referenced by triggers and core module)
CREATE TABLE IF NOT EXISTS mm_events(id INTEGER PRIMARY KEY, event_at TEXT NOT NULL, action TEXT NOT NULL, business_id INTEGER NOT NULL REFERENCES businesses(id), detail TEXT NOT NULL);

-- Outreach table (referenced by triggers and email migration)
CREATE TABLE IF NOT EXISTS outreach(id INTEGER PRIMARY KEY AUTOINCREMENT, offer_id INTEGER, draft TEXT NOT NULL, approved_by_human INTEGER DEFAULT 0, sent_at TEXT, reply_status TEXT, reply_class TEXT, next_action TEXT, unsubscribe_status TEXT);

-- Revenue table (referenced by legacy triggers)
CREATE TABLE IF NOT EXISTS revenue(id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id), quoted_nzd REAL NOT NULL DEFAULT 0, invoiced_nzd REAL NOT NULL DEFAULT 0, collected_nzd REAL NOT NULL DEFAULT 0, recurring_mrr_nzd REAL NOT NULL DEFAULT 0, costs_nzd REAL NOT NULL DEFAULT 0);

-- Projects table (referenced by revenue table)
CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY, client_business_id INTEGER REFERENCES businesses(id), scope TEXT NOT NULL, repository TEXT, status TEXT NOT NULL, estimated_hours REAL, actual_hours REAL, delivery_date TEXT, qa_status TEXT, rollback_plan TEXT);

CREATE TABLE IF NOT EXISTS mm_deals(business_id INTEGER PRIMARY KEY REFERENCES businesses(id), stage TEXT NOT NULL DEFAULT 'DISCOVERED', next_action TEXT, last_contact TEXT, due TEXT, updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS mm_evidence(id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id), url TEXT NOT NULL, observation TEXT NOT NULL, limitation TEXT NOT NULL, checked_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS mm_evidence_meta(evidence_id INTEGER PRIMARY KEY REFERENCES mm_evidence(id), status TEXT NOT NULL CHECK(status IN ('verified','refuted','partial','unverified')), method TEXT NOT NULL, confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1), claim_type TEXT NOT NULL, commercial_relevance TEXT NOT NULL, expires_at TEXT NOT NULL, capture_path TEXT NOT NULL, capture_hash TEXT NOT NULL, verified_by TEXT NOT NULL, verification_count INTEGER NOT NULL CHECK(verification_count>0));

CREATE TABLE IF NOT EXISTS mm_messages(id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id), evidence_id INTEGER NOT NULL REFERENCES mm_evidence(id), recipient TEXT NOT NULL, body TEXT NOT NULL, digest TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('initial','followup')), parent_id INTEGER REFERENCES mm_messages(id), created_at TEXT NOT NULL, approved_hash TEXT, approved_by TEXT, approval_ref TEXT, permission_basis TEXT, sent_at TEXT, send_receipt TEXT, invalidated_reason TEXT, reply TEXT);

CREATE TABLE IF NOT EXISTS mm_proposals(id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id), evidence_id INTEGER NOT NULL REFERENCES mm_evidence(id), recipient TEXT NOT NULL, body TEXT NOT NULL, price_cents INTEGER NOT NULL CHECK(price_cents>0), digest TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, approved_hash TEXT, approved_by TEXT, approval_ref TEXT, permission_basis TEXT, sent_at TEXT, send_receipt TEXT, invalidated_reason TEXT);

CREATE TABLE IF NOT EXISTS mm_receipts(id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('send','proposal_send','payment','refund','reply','approval')), business_id INTEGER NOT NULL REFERENCES businesses(id), object_id INTEGER, source_system TEXT NOT NULL, external_id TEXT NOT NULL, artifact_path TEXT NOT NULL, artifact_hash TEXT NOT NULL, content_hash TEXT, amount_cents INTEGER, currency TEXT NOT NULL DEFAULT 'NZD', verified_by TEXT NOT NULL, verified_at TEXT NOT NULL, occurred_at TEXT NOT NULL, UNIQUE(source_system,external_id), UNIQUE(artifact_hash,kind));

CREATE TABLE IF NOT EXISTS mm_cash(id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id), amount_cents INTEGER NOT NULL, receipt TEXT NOT NULL UNIQUE, received_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS mm_refunds(id INTEGER PRIMARY KEY, payment_id INTEGER NOT NULL REFERENCES mm_cash(id), amount_cents INTEGER NOT NULL CHECK(amount_cents>0), receipt TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS mm_holds(business_id INTEGER PRIMARY KEY REFERENCES businesses(id), reason TEXT NOT NULL, created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS mm_suppression(id INTEGER PRIMARY KEY, address TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(address));

-- Pipeline tables
CREATE TABLE IF NOT EXISTS pipeline_items(id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id), state TEXT NOT NULL CHECK(state IN ('DISCOVERED','VERIFIED','AUDITED','QUALIFIED','DRAFT_READY','AWAITING_APPROVAL','APPROVED_TO_SEND','SENT','REPLIED','CALL_OR_DISCOVERY','PROPOSAL_READY','PROPOSAL_SENT','WON','LOST','SUPPRESSED')), next_retry_at TEXT, lease_owner TEXT, lease_until TEXT, last_error TEXT, updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS pipeline_events(id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id), from_state TEXT, to_state TEXT, actor TEXT NOT NULL, reason TEXT, evidence TEXT, event_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS mm_scores(business_id INTEGER PRIMARY KEY REFERENCES businesses(id), evidence_id INTEGER NOT NULL REFERENCES mm_evidence(id), inputs_json TEXT NOT NULL, computed_json TEXT NOT NULL, calculated_at TEXT NOT NULL);

-- Contact evidence tables
CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER, contact_name TEXT, role TEXT, address_or_channel TEXT, source TEXT, contact_permission_basis TEXT, do_not_contact INTEGER DEFAULT 0, last_verified TEXT, FOREIGN KEY (business_id) REFERENCES businesses(id));

CREATE TABLE IF NOT EXISTS mm_contact_evidence(id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id), recipient TEXT NOT NULL, source_url TEXT NOT NULL, checked_at TEXT NOT NULL, relevance TEXT NOT NULL, permission_basis TEXT NOT NULL, permission_verified_by TEXT, unsubscribe_state TEXT NOT NULL CHECK(unsubscribe_state IN ('none_recorded','unsubscribed','unknown')), confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1), capture_path TEXT NOT NULL, capture_hash TEXT NOT NULL, UNIQUE(business_id,recipient));

-- Migration tracking
CREATE TABLE IF NOT EXISTS mm_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, backup_path TEXT NOT NULL);

-- Indexes
CREATE INDEX IF NOT EXISTS mm_evidence_business_date ON mm_evidence(business_id,checked_at DESC);
CREATE INDEX IF NOT EXISTS mm_message_business ON mm_messages(business_id,kind,sent_at);
CREATE INDEX IF NOT EXISTS mm_event_business_time ON mm_events(business_id,event_at);
CREATE INDEX IF NOT EXISTS mm_receipt_object ON mm_receipts(kind,business_id,object_id);
CREATE INDEX IF NOT EXISTS mm_deal_queue ON mm_deals(stage,due);
CREATE UNIQUE INDEX IF NOT EXISTS mm_one_initial ON mm_messages(business_id) WHERE kind='initial';
CREATE UNIQUE INDEX IF NOT EXISTS mm_unique_send_receipt ON mm_messages(send_receipt) WHERE send_receipt IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS mm_unique_proposal_receipt ON mm_proposals(send_receipt) WHERE send_receipt IS NOT NULL;