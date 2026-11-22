-- MoneyMachine Triggers v1
-- Auto-generated from mm_core.py TRIGGERS constant
-- This file contains all CREATE TRIGGER statements

-- Message send guard: exact current approval + verified receipt required
DROP TRIGGER IF EXISTS prevent_unapproved_mm_messages_send;
CREATE TRIGGER prevent_unapproved_mm_messages_send BEFORE UPDATE OF sent_at,send_receipt ON mm_messages
WHEN NEW.sent_at IS NOT NULL BEGIN
 SELECT CASE WHEN OLD.sent_at IS NOT NULL OR OLD.approved_hash IS NULL OR OLD.approved_hash IS NOT mm_digest(NEW.recipient,NEW.body) OR OLD.approval_ref IS NULL OR NEW.invalidated_reason IS NOT NULL THEN RAISE(ABORT,'send blocked: exact current approval required') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_receipts r WHERE cast(r.id AS TEXT)=NEW.send_receipt AND r.kind='send' AND r.business_id=NEW.business_id AND r.object_id=NEW.id AND r.content_hash=OLD.approved_hash) THEN RAISE(ABORT,'send blocked: verified external receipt required') END;
 SELECT CASE WHEN EXISTS(SELECT 1 FROM mm_holds WHERE business_id=NEW.business_id) OR EXISTS(SELECT 1 FROM mm_deals WHERE business_id=NEW.business_id AND stage='SUPPRESSED') OR EXISTS(SELECT 1 FROM mm_suppression WHERE lower(trim(address))=lower(trim(NEW.recipient))) OR EXISTS(SELECT 1 FROM contacts WHERE lower(trim(address_or_channel))=lower(trim(NEW.recipient)) AND do_not_contact=1) THEN RAISE(ABORT,'suppression overrides approval') END;
END;

-- Queue guard: suppressed prospects cannot enter queue
CREATE TRIGGER IF NOT EXISTS mm_message_queue_guard BEFORE INSERT ON mm_messages BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM mm_holds WHERE business_id=NEW.business_id) OR EXISTS(SELECT 1 FROM mm_deals WHERE business_id=NEW.business_id AND stage='SUPPRESSED') OR EXISTS(SELECT 1 FROM mm_suppression WHERE lower(trim(address))=lower(trim(NEW.recipient))) OR EXISTS(SELECT 1 FROM contacts WHERE lower(trim(address_or_channel))=lower(trim(NEW.recipient)) AND do_not_contact=1) THEN RAISE(ABORT,'suppressed prospect cannot enter queue') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_evidence WHERE id=NEW.evidence_id AND business_id=NEW.business_id) THEN RAISE(ABORT,'evidence belongs to different prospect') END;
END;

-- Message edit: invalidate approvals on content changes
CREATE TRIGGER IF NOT EXISTS mm_message_edit AFTER UPDATE OF body,recipient,evidence_id,digest,kind,parent_id,business_id,invalidated_reason ON mm_messages
WHEN NEW.body IS NOT OLD.body OR NEW.recipient IS NOT OLD.recipient OR NEW.evidence_id IS NOT OLD.evidence_id OR NEW.digest IS NOT OLD.digest OR NEW.kind IS NOT OLD.kind OR NEW.parent_id IS NOT OLD.parent_id OR NEW.business_id IS NOT OLD.business_id OR NEW.invalidated_reason IS NOT OLD.invalidated_reason BEGIN
 UPDATE mm_messages SET approved_hash=NULL,approved_by=NULL,approval_ref=NULL,permission_basis=NULL WHERE id=NEW.id;
END;

-- Sent content immutable
CREATE TRIGGER IF NOT EXISTS mm_sent_immutable BEFORE UPDATE OF body,recipient,evidence_id,digest,kind,parent_id,business_id ON mm_messages WHEN OLD.sent_at IS NOT NULL BEGIN SELECT RAISE(ABORT,'sent content is immutable');END;

-- Proposal edit: invalidate approvals on content changes
CREATE TRIGGER IF NOT EXISTS mm_proposal_edit AFTER UPDATE OF recipient,body,price_cents,evidence_id,digest,invalidated_reason ON mm_proposals WHEN NEW.recipient IS NOT OLD.recipient OR NEW.body IS NOT OLD.body OR NEW.price_cents IS NOT OLD.price_cents OR NEW.evidence_id IS NOT OLD.evidence_id OR NEW.digest IS NOT OLD.digest OR NEW.invalidated_reason IS NOT OLD.invalidated_reason BEGIN UPDATE mm_proposals SET approved_hash=NULL,approved_by=NULL,approval_ref=NULL,permission_basis=NULL WHERE id=NEW.id;END;

-- Proposal insert: requires draft and human approval
CREATE TRIGGER IF NOT EXISTS mm_proposal_insert BEFORE INSERT ON mm_proposals WHEN NEW.sent_at IS NOT NULL BEGIN SELECT RAISE(ABORT,'proposal requires draft and human approval');END;

-- Proposal send: exact price/content approval + receipt required
CREATE TRIGGER IF NOT EXISTS mm_proposal_send BEFORE UPDATE OF sent_at,send_receipt ON mm_proposals WHEN NEW.sent_at IS NOT NULL BEGIN
 SELECT CASE WHEN OLD.sent_at IS NOT NULL OR OLD.approved_hash IS NULL OR OLD.approved_hash IS NOT mm_proposal_digest(NEW.recipient,NEW.body,NEW.price_cents) OR OLD.approval_ref IS NULL OR NEW.invalidated_reason IS NOT NULL THEN RAISE(ABORT,'proposal requires exact price and content approval') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_receipts WHERE cast(id AS TEXT)=NEW.send_receipt AND kind='proposal_send' AND business_id=NEW.business_id AND object_id=NEW.id AND content_hash=OLD.approved_hash) THEN RAISE(ABORT,'proposal receipt required') END;
 SELECT CASE WHEN EXISTS(SELECT 1 FROM mm_holds WHERE business_id=NEW.business_id) OR EXISTS(SELECT 1 FROM mm_deals WHERE business_id=NEW.business_id AND stage='SUPPRESSED') OR EXISTS(SELECT 1 FROM mm_suppression WHERE lower(trim(address))=lower(trim(NEW.recipient))) THEN RAISE(ABORT,'suppression overrides proposal approval') END;
END;

-- Cash proof: payment evidence required
CREATE TRIGGER IF NOT EXISTS mm_cash_proof BEFORE INSERT ON mm_cash BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_receipts WHERE cast(id AS TEXT)=NEW.receipt AND kind='payment' AND business_id=NEW.business_id AND amount_cents=NEW.amount_cents AND currency='NZD') THEN RAISE(ABORT,'payment evidence required') END;
END;

-- Cash immutable
CREATE TRIGGER IF NOT EXISTS mm_cash_immutable BEFORE UPDATE ON mm_cash BEGIN SELECT RAISE(ABORT,'cash ledger immutable; record a refund');END;
CREATE TRIGGER IF NOT EXISTS mm_cash_no_delete BEFORE DELETE ON mm_cash BEGIN SELECT RAISE(ABORT,'cash ledger immutable; record a refund');END;

-- Refund proof and limits
CREATE TRIGGER IF NOT EXISTS mm_refund_proof BEFORE INSERT ON mm_refunds BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_receipts r JOIN mm_cash c ON c.id=NEW.payment_id WHERE cast(r.id AS TEXT)=NEW.receipt AND r.kind='refund' AND r.object_id=c.id AND r.business_id=c.business_id AND r.amount_cents=NEW.amount_cents AND r.currency='NZD') THEN RAISE(ABORT,'refund evidence required') END;
 SELECT CASE WHEN NEW.amount_cents+coalesce((SELECT sum(amount_cents) FROM mm_refunds WHERE payment_id=NEW.payment_id),0)>(SELECT amount_cents FROM mm_cash WHERE id=NEW.payment_id) THEN RAISE(ABORT,'refund exceeds payment') END;
END;

-- Refund immutable
CREATE TRIGGER IF NOT EXISTS mm_refund_immutable BEFORE UPDATE ON mm_refunds BEGIN SELECT RAISE(ABORT,'refund ledger immutable');END;
CREATE TRIGGER IF NOT EXISTS mm_refund_no_delete BEFORE DELETE ON mm_refunds BEGIN SELECT RAISE(ABORT,'refund ledger immutable');END;

-- Receipt immutable
CREATE TRIGGER IF NOT EXISTS mm_receipt_immutable BEFORE UPDATE ON mm_receipts BEGIN SELECT RAISE(ABORT,'receipt immutable');END;
CREATE TRIGGER IF NOT EXISTS mm_receipt_no_delete BEFORE DELETE ON mm_receipts BEGIN SELECT RAISE(ABORT,'receipt immutable');END;

-- Hold immutable
CREATE TRIGGER IF NOT EXISTS mm_hold_no_delete BEFORE DELETE ON mm_holds BEGIN SELECT RAISE(ABORT,'manual reconciliation required; no unsuppression path');END;

-- Suppression immutable
CREATE TRIGGER IF NOT EXISTS mm_suppression_no_delete BEFORE DELETE ON mm_suppression BEGIN SELECT RAISE(ABORT,'no unsuppression path');END;

-- Suppression revoke: cascade to messages, proposals, deals
CREATE TRIGGER IF NOT EXISTS mm_suppression_revoke AFTER INSERT ON mm_suppression BEGIN
 UPDATE mm_messages SET approved_hash=NULL,approval_ref=NULL WHERE lower(trim(recipient))=lower(trim(NEW.address));
 UPDATE mm_proposals SET approved_hash=NULL,approval_ref=NULL WHERE lower(trim(recipient))=lower(trim(NEW.address));
 UPDATE mm_deals SET stage='SUPPRESSED',next_action='Do not contact',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE business_id IN(SELECT business_id FROM mm_messages WHERE lower(trim(recipient))=lower(trim(NEW.address)) UNION SELECT business_id FROM contacts WHERE lower(trim(address_or_channel))=lower(trim(NEW.address)));
END;

-- Stage guard: suppressed cannot reopen, SENT/PROPOSAL_SENT/WON require evidence
CREATE TRIGGER IF NOT EXISTS mm_stage_guard BEFORE UPDATE OF stage ON mm_deals BEGIN
 SELECT CASE WHEN (OLD.stage='SUPPRESSED' OR EXISTS(SELECT 1 FROM mm_holds WHERE business_id=NEW.business_id)) AND NEW.stage!='SUPPRESSED' THEN RAISE(ABORT,'suppressed businesses cannot reopen') END;
 SELECT CASE WHEN NEW.stage='SENT' AND NOT EXISTS(SELECT 1 FROM mm_messages m JOIN mm_receipts r ON cast(r.id AS TEXT)=m.send_receipt WHERE m.business_id=NEW.business_id AND m.sent_at IS NOT NULL AND r.kind='send') THEN RAISE(ABORT,'SENT requires external-send evidence') END;
 SELECT CASE WHEN NEW.stage='PROPOSAL_SENT' AND NOT EXISTS(SELECT 1 FROM mm_proposals p JOIN mm_receipts r ON cast(r.id AS TEXT)=p.send_receipt WHERE p.business_id=NEW.business_id AND p.sent_at IS NOT NULL AND r.kind='proposal_send') THEN RAISE(ABORT,'proposal send evidence required') END;
 SELECT CASE WHEN NEW.stage='WON' AND NOT EXISTS(SELECT 1 FROM mm_cash WHERE business_id=NEW.business_id) THEN RAISE(ABORT,'WON requires payment evidence in current workflow') END;
END;

-- Stage event: record transitions
CREATE TRIGGER IF NOT EXISTS mm_stage_event AFTER UPDATE OF stage ON mm_deals WHEN NEW.stage IS NOT OLD.stage BEGIN
 UPDATE mm_deals SET updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE business_id=NEW.business_id;
 INSERT INTO mm_events(event_at,action,business_id,detail) VALUES(strftime('%Y-%m-%dT%H:%M:%fZ','now'),'stage_transition',NEW.business_id,OLD.stage||' -> '||NEW.stage);
END;

-- Legacy closures
CREATE TRIGGER IF NOT EXISTS mm_legacy_send_closed BEFORE UPDATE OF sent_at,approved_by_human ON outreach WHEN NEW.sent_at IS NOT NULL AND (NEW.sent_at IS NOT OLD.sent_at OR NEW.approved_by_human IS NOT OLD.approved_by_human) BEGIN SELECT RAISE(ABORT,'legacy send recording retired; use verified receipt workflow');END;
CREATE TRIGGER IF NOT EXISTS mm_legacy_revenue_closed BEFORE INSERT ON revenue WHEN NEW.collected_nzd!=0 BEGIN SELECT RAISE(ABORT,'use verified cash ledger');END;
CREATE TRIGGER IF NOT EXISTS mm_legacy_revenue_update BEFORE UPDATE OF collected_nzd ON revenue WHEN NEW.collected_nzd IS NOT OLD.collected_nzd BEGIN SELECT RAISE(ABORT,'use verified cash ledger');END;

-- Message approval proof: artifact required
CREATE TRIGGER IF NOT EXISTS mm_message_approval_proof BEFORE UPDATE OF approved_hash ON mm_messages WHEN NEW.approved_hash IS NOT NULL BEGIN
 SELECT CASE WHEN NEW.invalidated_reason IS NOT NULL OR NOT EXISTS(SELECT 1 FROM mm_receipts WHERE cast(id AS TEXT)=NEW.approval_ref AND kind='approval' AND business_id=NEW.business_id AND object_id=NEW.id AND content_hash=NEW.approved_hash AND verified_by=NEW.approved_by AND mm_artifact_valid(artifact_path,artifact_hash)=1) THEN RAISE(ABORT,'approval evidence artifact required') END;
END;

-- Message readiness guard: verified evidence + contact + demo QA
CREATE TRIGGER IF NOT EXISTS mm_message_readiness_guard BEFORE UPDATE OF approved_hash,sent_at ON mm_messages WHEN NEW.approved_hash IS NOT NULL OR (NEW.sent_at IS NOT OLD.sent_at AND NEW.sent_at IS NOT NULL) BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_evidence e JOIN mm_evidence_meta m ON m.evidence_id=e.id WHERE e.id=NEW.evidence_id AND e.business_id=NEW.business_id AND m.status='verified' AND m.confidence>=0.7 AND julianday(e.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND julianday(m.expires_at)>=julianday('now') AND mm_artifact_valid(m.capture_path,m.capture_hash)=1) THEN RAISE(ABORT,'current verified captured evidence required') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_contact_evidence c WHERE c.business_id=NEW.business_id AND lower(c.recipient)=lower(NEW.recipient) AND length(c.permission_verified_by)>0 AND length(c.permission_basis)>0 AND c.unsubscribe_state='none_recorded' AND c.confidence>=0.7 AND julianday(c.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND mm_artifact_valid(c.capture_path,c.capture_hash)=1) THEN RAISE(ABORT,'verified contact source and permission required') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_demo_qa q WHERE q.business_id=NEW.business_id AND q.passed=1 AND q.score>=80 AND julianday(q.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND mm_artifact_valid(q.path,q.file_hash)=1) THEN RAISE(ABORT,'current demo QA required') END;
 SELECT CASE WHEN EXISTS(SELECT 1 FROM mm_holds WHERE business_id=NEW.business_id) OR EXISTS(SELECT 1 FROM mm_deals WHERE business_id=NEW.business_id AND stage='SUPPRESSED') OR EXISTS(SELECT 1 FROM mm_suppression WHERE lower(trim(address))=lower(trim(NEW.recipient))) OR EXISTS(SELECT 1 FROM contacts WHERE lower(trim(address_or_channel))=lower(trim(NEW.recipient)) AND do_not_contact=1) THEN RAISE(ABORT,'suppression overrides approval') END;
END;

-- Sent record immutable
CREATE TRIGGER IF NOT EXISTS mm_message_sent_record_immutable BEFORE UPDATE OF sent_at,send_receipt ON mm_messages WHEN OLD.sent_at IS NOT NULL AND (NEW.sent_at IS NOT OLD.sent_at OR NEW.send_receipt IS NOT OLD.send_receipt) BEGIN SELECT RAISE(ABORT,'recorded send is immutable');END;

-- Approval insert: create draft first
CREATE TRIGGER IF NOT EXISTS mm_message_approval_insert BEFORE INSERT ON mm_messages WHEN NEW.approved_hash IS NOT NULL BEGIN SELECT RAISE(ABORT,'create draft before recording exact human approval');END;

-- Proposal approval proof
CREATE TRIGGER IF NOT EXISTS mm_proposal_approval_proof BEFORE UPDATE OF approved_hash ON mm_proposals WHEN NEW.approved_hash IS NOT NULL BEGIN
 SELECT CASE WHEN NEW.invalidated_reason IS NOT NULL OR NOT EXISTS(SELECT 1 FROM mm_receipts WHERE cast(id AS TEXT)=NEW.approval_ref AND kind='approval' AND business_id=NEW.business_id AND object_id=NEW.id AND content_hash=NEW.approved_hash AND verified_by=NEW.approved_by AND mm_artifact_valid(artifact_path,artifact_hash)=1) THEN RAISE(ABORT,'approval evidence artifact required') END;
END;

-- Proposal readiness guard
CREATE TRIGGER IF NOT EXISTS mm_proposal_readiness_guard BEFORE UPDATE OF approved_hash,sent_at ON mm_proposals WHEN NEW.approved_hash IS NOT NULL OR (NEW.sent_at IS NOT OLD.sent_at AND NEW.sent_at IS NOT NULL) BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_evidence e JOIN mm_evidence_meta m ON m.evidence_id=e.id WHERE e.id=NEW.evidence_id AND e.business_id=NEW.business_id AND m.status='verified' AND m.confidence>=0.7 AND julianday(e.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND julianday(m.expires_at)>=julianday('now') AND mm_artifact_valid(m.capture_path,m.capture_hash)=1) THEN RAISE(ABORT,'current verified captured evidence required') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_contact_evidence c WHERE c.business_id=NEW.business_id AND lower(c.recipient)=lower(NEW.recipient) AND length(c.permission_verified_by)>0 AND length(c.permission_basis)>0 AND c.unsubscribe_state='none_recorded' AND c.confidence>=0.7 AND julianday(c.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND mm_artifact_valid(c.capture_path,c.capture_hash)=1) THEN RAISE(ABORT,'verified contact source and permission required') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_demo_qa q WHERE q.business_id=NEW.business_id AND q.passed=1 AND q.score>=80 AND julianday(q.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND mm_artifact_valid(q.path,q.file_hash)=1) THEN RAISE(ABORT,'current demo QA required') END;
 SELECT CASE WHEN EXISTS(SELECT 1 FROM mm_holds WHERE business_id=NEW.business_id) OR EXISTS(SELECT 1 FROM mm_deals WHERE business_id=NEW.business_id AND stage='SUPPRESSED') OR EXISTS(SELECT 1 FROM mm_suppression WHERE lower(trim(address))=lower(trim(NEW.recipient))) OR EXISTS(SELECT 1 FROM contacts WHERE lower(trim(address_or_channel))=lower(trim(NEW.recipient)) AND do_not_contact=1) THEN RAISE(ABORT,'suppression overrides approval') END;
END;

-- Proposal sent record immutable
CREATE TRIGGER IF NOT EXISTS mm_proposal_sent_record_immutable BEFORE UPDATE OF sent_at,send_receipt ON mm_proposals WHEN OLD.sent_at IS NOT NULL AND (NEW.sent_at IS NOT OLD.sent_at OR NEW.send_receipt IS NOT OLD.send_receipt) BEGIN SELECT RAISE(ABORT,'recorded send is immutable');END;

-- Proposal approval insert: create draft first
CREATE TRIGGER IF NOT EXISTS mm_proposal_approval_insert BEFORE INSERT ON mm_proposals WHEN NEW.approved_hash IS NOT NULL BEGIN SELECT RAISE(ABORT,'create draft before recording exact human approval');END;

-- Proposal sent content immutable
CREATE TRIGGER IF NOT EXISTS mm_proposal_sent_content_immutable BEFORE UPDATE OF recipient,body,price_cents,evidence_id,digest,business_id ON mm_proposals WHEN OLD.sent_at IS NOT NULL BEGIN SELECT RAISE(ABORT,'sent proposal immutable');END;

-- Evidence change: revoke approvals
CREATE TRIGGER IF NOT EXISTS mm_evidence_change_revoke AFTER UPDATE ON mm_evidence BEGIN
 UPDATE mm_messages SET approved_hash=NULL,approval_ref=NULL WHERE evidence_id=NEW.id;
 UPDATE mm_proposals SET approved_hash=NULL,approval_ref=NULL WHERE evidence_id=NEW.id;
END;

-- Evidence meta change: revoke approvals
CREATE TRIGGER IF NOT EXISTS mm_evidence_meta_change_revoke AFTER UPDATE ON mm_evidence_meta BEGIN
 UPDATE mm_messages SET approved_hash=NULL,approval_ref=NULL WHERE evidence_id=NEW.evidence_id;
 UPDATE mm_proposals SET approved_hash=NULL,approval_ref=NULL WHERE evidence_id=NEW.evidence_id;
END;

-- Contact change: revoke approvals
CREATE TRIGGER IF NOT EXISTS mm_contact_change_revoke AFTER UPDATE ON mm_contact_evidence BEGIN
 UPDATE mm_messages SET approved_hash=NULL,approval_ref=NULL WHERE business_id=NEW.business_id;
 UPDATE mm_proposals SET approved_hash=NULL,approval_ref=NULL WHERE business_id=NEW.business_id;
END;

-- Ready stage guard: approval-ready stage requires current complete packet
CREATE TRIGGER IF NOT EXISTS mm_ready_stage_guard BEFORE UPDATE OF stage ON mm_deals WHEN NEW.stage IN ('DRAFT_READY','AWAITING_APPROVAL','APPROVED_TO_SEND','PROPOSAL_READY') BEGIN
 SELECT CASE WHEN NOT EXISTS(
  SELECT 1 FROM (SELECT business_id,evidence_id,recipient,approved_hash,invalidated_reason,'message' AS kind FROM mm_messages UNION ALL SELECT business_id,evidence_id,recipient,approved_hash,invalidated_reason,'proposal' AS kind FROM mm_proposals) p
  JOIN mm_evidence e ON e.id=p.evidence_id AND e.business_id=p.business_id JOIN mm_evidence_meta m ON m.evidence_id=e.id
  JOIN mm_contact_evidence c ON c.business_id=p.business_id AND lower(c.recipient)=lower(p.recipient)
  JOIN mm_demo_qa q ON q.business_id=p.business_id
  WHERE p.business_id=NEW.business_id AND p.invalidated_reason IS NULL AND m.status='verified' AND m.confidence>=0.7
   AND ((NEW.stage='PROPOSAL_READY' AND p.kind='proposal') OR (NEW.stage!='PROPOSAL_READY' AND p.kind='message'))
   AND (NEW.stage!='APPROVED_TO_SEND' OR p.approved_hash IS NOT NULL)
   AND e.id=(SELECT id FROM mm_evidence WHERE business_id=p.business_id ORDER BY julianday(checked_at) DESC,id DESC LIMIT 1)
   AND julianday(e.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND julianday(m.expires_at)>=julianday('now')
   AND mm_artifact_valid(m.capture_path,m.capture_hash)=1 AND length(c.permission_verified_by)>0 AND length(c.permission_basis)>0 AND c.unsubscribe_state='none_recorded' AND c.confidence>=0.7
   AND julianday(c.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND mm_artifact_valid(c.capture_path,c.capture_hash)=1
   AND q.passed=1 AND q.score>=80 AND julianday(q.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND mm_artifact_valid(q.path,q.file_hash)=1
   AND NOT EXISTS(SELECT 1 FROM mm_suppression WHERE lower(trim(address))=lower(trim(p.recipient)))
 ) THEN RAISE(ABORT,'approval-ready stage requires current complete packet') END;
END;