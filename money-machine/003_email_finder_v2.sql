-- Additive migration. Legacy contacts, commercial evidence, CRM and send history
-- are untouched. Apply via mm_email_store.migrate_email with a verified backup.
CREATE TABLE email_schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, backup_path TEXT NOT NULL, sql_hash TEXT NOT NULL);
CREATE TABLE email_policy(id INTEGER PRIMARY KEY CHECK(id=1), mode TEXT NOT NULL CHECK(mode IN ('shadow','v2','v1_hold')), changed_at TEXT NOT NULL, acceptance_hash TEXT, CHECK(mode!='v2' OR length(acceptance_hash)=64));
INSERT INTO email_policy VALUES(1,'shadow',strftime('%Y-%m-%dT%H:%M:%fZ','now'),NULL);
CREATE TABLE email_candidates(
 id INTEGER PRIMARY KEY, prospect_id INTEGER REFERENCES businesses(id), email TEXT NOT NULL,
 normalized_email TEXT NOT NULL, source_type TEXT NOT NULL, source_url TEXT,
 source_excerpt TEXT, observed_at TEXT, candidate_method TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('OBSERVED','CANDIDATE','VERIFIED_HIGH','VERIFIED_MEDIUM','UNVERIFIED','REJECTED','SUPPRESSED')),
 legacy_ref TEXT UNIQUE, created_at TEXT NOT NULL
);
CREATE INDEX email_candidate_lookup ON email_candidates(prospect_id,normalized_email);
CREATE TABLE email_identity_checks(id INTEGER PRIMARY KEY, prospect_id INTEGER NOT NULL REFERENCES businesses(id), checked_at TEXT NOT NULL, entity_key TEXT NOT NULL, result_json TEXT NOT NULL, evidence_hash TEXT NOT NULL);
CREATE INDEX email_identity_business ON email_identity_checks(prospect_id,id DESC);
CREATE TABLE email_evidence(
 id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL REFERENCES email_candidates(id),
 evidence_type TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL, excerpt TEXT NOT NULL,
 observed_email TEXT NOT NULL, captured_at TEXT NOT NULL, evidence_hash TEXT NOT NULL,
 capture_path TEXT NOT NULL, role TEXT NOT NULL,
 UNIQUE(candidate_id,url,evidence_type,evidence_hash,observed_email)
);
CREATE TABLE email_verifications(
 id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL REFERENCES email_candidates(id),
 identity_id INTEGER REFERENCES email_identity_checks(id), checked_at TEXT NOT NULL,
 syntax_valid INTEGER NOT NULL CHECK(syntax_valid IN(0,1)), mx_valid INTEGER NOT NULL CHECK(mx_valid IN(0,1)),
 smtp_status TEXT NOT NULL, catch_all_status TEXT NOT NULL,
 disposable INTEGER NOT NULL CHECK(disposable IN(0,1)), business_match INTEGER NOT NULL CHECK(business_match IN(0,1)),
 person_match TEXT NOT NULL, first_party_observed INTEGER NOT NULL CHECK(first_party_observed IN(0,1)),
 confidence_score INTEGER NOT NULL CHECK(confidence_score BETWEEN 0 AND 100),
 confidence_label TEXT NOT NULL CHECK(confidence_label IN ('OBSERVED','CANDIDATE','VERIFIED_HIGH','VERIFIED_MEDIUM','UNVERIFIED','REJECTED','SUPPRESSED')),
 rejection_reason TEXT NOT NULL, verifier_version TEXT NOT NULL, result_json TEXT NOT NULL,
 CHECK(confidence_label!='VERIFIED_HIGH' OR (confidence_score>=90 AND syntax_valid=1 AND mx_valid=1 AND business_match=1 AND first_party_observed=1 AND disposable=0 AND smtp_status!='rejected'))
);
CREATE INDEX email_verification_current ON email_verifications(candidate_id,id DESC);
CREATE TABLE prospect_email_state(
 prospect_id INTEGER PRIMARY KEY REFERENCES businesses(id), best_email_id INTEGER REFERENCES email_candidates(id),
 best_verification_id INTEGER REFERENCES email_verifications(id), best_email_confidence INTEGER,
 email_review_required INTEGER NOT NULL DEFAULT 1 CHECK(email_review_required=1),
 contact_form_urls TEXT NOT NULL DEFAULT '[]', selection_status TEXT NOT NULL,
 last_checked TEXT NOT NULL, identity_id INTEGER REFERENCES email_identity_checks(id)
);
CREATE TABLE email_shadow_runs(id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, verifier_version TEXT NOT NULL, result_hash TEXT NOT NULL, result_json TEXT NOT NULL);
CREATE TRIGGER email_evidence_no_update BEFORE UPDATE ON email_evidence BEGIN SELECT RAISE(ABORT,'email evidence is append-only'); END;
CREATE TRIGGER email_evidence_no_delete BEFORE DELETE ON email_evidence BEGIN SELECT RAISE(ABORT,'email evidence is append-only'); END;
CREATE TRIGGER email_verification_no_update BEFORE UPDATE ON email_verifications BEGIN SELECT RAISE(ABORT,'email verification is append-only'); END;
CREATE TRIGGER email_verification_no_delete BEFORE DELETE ON email_verifications BEGIN SELECT RAISE(ABORT,'email verification is append-only'); END;
CREATE TRIGGER email_identity_no_update BEFORE UPDATE ON email_identity_checks BEGIN SELECT RAISE(ABORT,'email identity is append-only'); END;
CREATE TRIGGER email_identity_no_delete BEFORE DELETE ON email_identity_checks BEGIN SELECT RAISE(ABORT,'email identity is append-only'); END;
CREATE TRIGGER email_candidate_no_update BEFORE UPDATE ON email_candidates BEGIN SELECT RAISE(ABORT,'raw email candidates are historical; append evidence/checks'); END;
CREATE TRIGGER email_candidate_no_delete BEFORE DELETE ON email_candidates BEGIN SELECT RAISE(ABORT,'raw email candidates are historical'); END;

CREATE VIEW email_current_high AS
 SELECT c.prospect_id,c.normalized_email,c.id AS candidate_id,v.id AS verification_id
 FROM email_candidates c JOIN email_verifications v ON v.candidate_id=c.id
 JOIN email_identity_checks i ON i.id=v.identity_id AND i.prospect_id=c.prospect_id
 JOIN prospect_email_state s ON s.prospect_id=c.prospect_id AND s.best_email_id=c.id AND s.best_verification_id=v.id
 WHERE v.id=(SELECT max(v2.id) FROM email_verifications v2 WHERE v2.candidate_id=c.id)
 AND v.confidence_label='VERIFIED_HIGH' AND v.verifier_version='email-v2.0.0'
 AND v.identity_id=(SELECT max(i.id) FROM email_identity_checks i WHERE i.prospect_id=c.prospect_id)
 AND julianday(v.checked_at) BETWEEN julianday('now','-1 day') AND julianday('now')
 AND julianday(json_extract(v.result_json,'$.dns_checked_at')) BETWEEN julianday('now','-1 day') AND julianday('now')
 AND json_array_length(json_extract(v.result_json,'$.rejection_reasons'))=0
 AND json_array_length(json_extract(i.result_json,'$.page_evidence'))>0
 AND NOT EXISTS(SELECT 1 FROM json_each(i.result_json,'$.page_evidence') p
   WHERE mm_artifact_valid(json_extract(p.value,'$.capture_path'),json_extract(p.value,'$.capture_hash'))!=1
   OR julianday(json_extract(p.value,'$.captured_at')) NOT BETWEEN julianday('now','-7 days') AND julianday('now'))
 AND json_array_length(json_extract(v.result_json,'$.evidence'))>0
 AND NOT EXISTS(SELECT 1 FROM json_each(v.result_json,'$.evidence') p
   WHERE mm_artifact_valid(json_extract(p.value,'$.capture_path'),json_extract(p.value,'$.capture_hash'))!=1)
 AND EXISTS(SELECT 1 FROM email_evidence e WHERE e.candidate_id=c.id
   AND julianday(e.captured_at) BETWEEN julianday('now','-7 days') AND julianday('now')
   AND e.evidence_type IN('mailto','visible_text','obfuscated_text','cloudflare_obfuscation','structured_data','pdf_text')
   AND mm_artifact_valid(e.capture_path,e.evidence_hash)=1)
 AND NOT EXISTS(SELECT 1 FROM mm_holds WHERE business_id=c.prospect_id)
 AND NOT EXISTS(SELECT 1 FROM mm_deals WHERE business_id=c.prospect_id AND stage='SUPPRESSED')
 AND NOT EXISTS(SELECT 1 FROM mm_suppression WHERE lower(trim(address))=lower(c.normalized_email))
 AND NOT EXISTS(SELECT 1 FROM contacts WHERE lower(trim(address_or_channel))=lower(c.normalized_email) AND do_not_contact=1)
 AND NOT EXISTS(SELECT 1 FROM mm_contact_evidence WHERE business_id=c.prospect_id AND lower(trim(recipient))=lower(c.normalized_email) AND unsubscribe_state='unsubscribed');

-- No existing guard is removed. Shadow never changes existing readiness behavior.
-- v1_hold is a safe rollback: legacy views remain available, new approvals held.
CREATE TRIGGER email_v2_message_gate BEFORE UPDATE OF approved_hash,sent_at ON mm_messages
 WHEN (NEW.approved_hash IS NOT NULL OR (NEW.sent_at IS NOT OLD.sent_at AND NEW.sent_at IS NOT NULL)) AND (SELECT mode FROM email_policy WHERE id=1)!='shadow' BEGIN
 SELECT CASE WHEN (SELECT mode FROM email_policy WHERE id=1)!='v2' OR NOT EXISTS(SELECT 1 FROM email_current_high WHERE prospect_id=NEW.business_id AND normalized_email=trim(NEW.recipient)) THEN RAISE(ABORT,'current VERIFIED_HIGH email provenance required; rollback mode holds approvals') END;
END;
CREATE TRIGGER email_v2_proposal_gate BEFORE UPDATE OF approved_hash,sent_at ON mm_proposals
 WHEN (NEW.approved_hash IS NOT NULL OR (NEW.sent_at IS NOT OLD.sent_at AND NEW.sent_at IS NOT NULL)) AND (SELECT mode FROM email_policy WHERE id=1)!='shadow' BEGIN
 SELECT CASE WHEN (SELECT mode FROM email_policy WHERE id=1)!='v2' OR NOT EXISTS(SELECT 1 FROM email_current_high WHERE prospect_id=NEW.business_id AND normalized_email=trim(NEW.recipient)) THEN RAISE(ABORT,'current VERIFIED_HIGH email provenance required; rollback mode holds approvals') END;
END;
CREATE TRIGGER email_v2_stage_gate BEFORE UPDATE OF stage ON mm_deals
 WHEN NEW.stage IN('DRAFT_READY','AWAITING_APPROVAL','APPROVED_TO_SEND','PROPOSAL_READY') AND (SELECT mode FROM email_policy WHERE id=1)!='shadow' BEGIN
 SELECT CASE WHEN (SELECT mode FROM email_policy WHERE id=1)!='v2' OR NOT EXISTS(
  SELECT 1 FROM email_current_high h JOIN (
   SELECT business_id,recipient,'message' AS kind FROM mm_messages WHERE invalidated_reason IS NULL
   UNION ALL SELECT business_id,recipient,'proposal' AS kind FROM mm_proposals WHERE invalidated_reason IS NULL
  ) p ON p.business_id=h.prospect_id AND trim(p.recipient)=h.normalized_email
  WHERE h.prospect_id=NEW.business_id AND ((NEW.stage='PROPOSAL_READY' AND p.kind='proposal') OR (NEW.stage!='PROPOSAL_READY' AND p.kind='message'))
 ) THEN RAISE(ABORT,'outreach-ready stage requires current VERIFIED_HIGH email') END;
END;
CREATE TRIGGER email_v2_message_draft_gate BEFORE INSERT ON mm_messages WHEN (SELECT mode FROM email_policy WHERE id=1)!='shadow' BEGIN
 SELECT CASE WHEN (SELECT mode FROM email_policy WHERE id=1)!='v2' OR NOT EXISTS(SELECT 1 FROM email_current_high WHERE prospect_id=NEW.business_id AND normalized_email=trim(NEW.recipient)) THEN RAISE(ABORT,'draft recipient requires VERIFIED_HIGH email') END;
END;
CREATE TRIGGER email_v2_proposal_draft_gate BEFORE INSERT ON mm_proposals WHEN (SELECT mode FROM email_policy WHERE id=1)!='shadow' BEGIN
 SELECT CASE WHEN (SELECT mode FROM email_policy WHERE id=1)!='v2' OR NOT EXISTS(SELECT 1 FROM email_current_high WHERE prospect_id=NEW.business_id AND normalized_email=trim(NEW.recipient)) THEN RAISE(ABORT,'proposal recipient requires VERIFIED_HIGH email') END;
END;
CREATE TRIGGER email_policy_no_delete BEFORE DELETE ON email_policy BEGIN SELECT RAISE(ABORT,'email policy cannot be removed'); END;
CREATE TRIGGER email_policy_no_shadow_reopen BEFORE UPDATE OF mode ON email_policy WHEN OLD.mode!='shadow' AND NEW.mode='shadow' BEGIN SELECT RAISE(ABORT,'use v1_hold for rollback; shadow cannot reopen readiness'); END;
