-- Additive hardening. Historical email, CRM, events and scores are retained.
-- No production promotion is performed by this migration.
CREATE TABLE email_release_policy(
 id INTEGER PRIMARY KEY CHECK(id=1),
 mode TEXT NOT NULL CHECK(mode IN ('POST_DEPLOYMENT_OBSERVATION','PRODUCTION')),
 verifier_version TEXT NOT NULL,
 precision_receipt TEXT,
 CHECK(mode!='PRODUCTION' OR (precision_receipt IS NOT NULL AND length(precision_receipt)=64))
);
INSERT INTO email_release_policy VALUES(1,'POST_DEPLOYMENT_OBSERVATION','email-v2.0.1',NULL);
DROP VIEW email_current_high;
CREATE VIEW email_current_high AS
 SELECT c.prospect_id,c.normalized_email,c.id AS candidate_id,v.id AS verification_id
 FROM email_candidates c JOIN email_verifications v ON v.candidate_id=c.id
 JOIN email_identity_checks i ON i.id=v.identity_id AND i.prospect_id=c.prospect_id
 JOIN prospect_email_state s ON s.prospect_id=c.prospect_id AND s.best_email_id=c.id AND s.best_verification_id=v.id
 WHERE v.id=(SELECT max(v2.id) FROM email_verifications v2 WHERE v2.candidate_id=c.id)
 AND v.confidence_label='VERIFIED_HIGH' AND v.verifier_version=(SELECT verifier_version FROM email_release_policy WHERE id=1 AND mode='PRODUCTION')
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
CREATE TRIGGER mm_event_shape_insert BEFORE INSERT ON mm_events BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM mm_events WHERE id=NEW.id)
 THEN RAISE(ABORT,'event replacement blocked; append a correction') END;
 SELECT CASE WHEN julianday(NEW.event_at) IS NULL OR typeof(NEW.action)!='text'
  OR NEW.action NOT GLOB '[A-Za-z]*' OR trim(NEW.action)=''
  OR (NEW.business_id IS NOT NULL AND (typeof(NEW.business_id)!='integer' OR NOT EXISTS(SELECT 1 FROM businesses WHERE id=NEW.business_id)))
 THEN RAISE(ABORT,'invalid event fields; use explicit event_at,action,business_id,detail columns') END;
END;
CREATE TRIGGER mm_event_history_update BEFORE UPDATE ON mm_events BEGIN SELECT RAISE(ABORT,'event history is immutable; append a correction'); END;
CREATE TRIGGER mm_event_history_delete BEFORE DELETE ON mm_events BEGIN SELECT RAISE(ABORT,'event history is immutable'); END;
CREATE TABLE mm_score_history(
 id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL, evidence_id INTEGER NOT NULL,
 inputs_json TEXT NOT NULL,computed_json TEXT NOT NULL,calculated_at TEXT NOT NULL,
 archived_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 UNIQUE(business_id,evidence_id,inputs_json,computed_json,calculated_at)
);
INSERT INTO mm_score_history(business_id,evidence_id,inputs_json,computed_json,calculated_at)
 SELECT business_id,evidence_id,inputs_json,computed_json,calculated_at FROM mm_scores;
CREATE TRIGGER mm_score_preimage_insert BEFORE INSERT ON mm_scores BEGIN
 INSERT OR IGNORE INTO mm_score_history(business_id,evidence_id,inputs_json,computed_json,calculated_at)
 SELECT business_id,evidence_id,inputs_json,computed_json,calculated_at FROM mm_scores WHERE business_id=NEW.business_id;
END;
CREATE TRIGGER mm_score_preimage_update BEFORE UPDATE ON mm_scores BEGIN
 INSERT OR IGNORE INTO mm_score_history(business_id,evidence_id,inputs_json,computed_json,calculated_at)
 VALUES(OLD.business_id,OLD.evidence_id,OLD.inputs_json,OLD.computed_json,OLD.calculated_at);
END;
CREATE TRIGGER mm_score_delete_guard BEFORE DELETE ON mm_scores BEGIN SELECT RAISE(ABORT,'score deletion blocked; update through supported scoring with history'); END;
CREATE TRIGGER mm_score_history_update BEFORE UPDATE ON mm_score_history BEGIN SELECT RAISE(ABORT,'score history is immutable'); END;
CREATE TRIGGER mm_score_history_delete BEFORE DELETE ON mm_score_history BEGIN SELECT RAISE(ABORT,'score history is immutable'); END;
CREATE TRIGGER mm_score_history_replace BEFORE INSERT ON mm_score_history
 WHEN EXISTS(SELECT 1 FROM mm_score_history WHERE id=NEW.id)
 BEGIN SELECT RAISE(ABORT,'score history replacement blocked'); END;
