"""Deterministic MoneyMachine integrity layer. No network or model clients.

Local evidence attestation is not independent provider verification. A person with
write access to the DB can change its schema; these gates protect normal use.
"""
import datetime as dt
import contextlib
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import sqlite3
import tarfile
import time
import uuid
from urllib.parse import urlsplit

UTC = dt.timezone.utc
STAGES = ('DISCOVERED','VERIFIED','AUDITED','QUALIFIED','DRAFT_READY','AWAITING_APPROVAL','APPROVED_TO_SEND','SENT','REPLIED','CALL_OR_DISCOVERY','PROPOSAL_READY','PROPOSAL_SENT','WON','LOST','SUPPRESSED')

def now(): return dt.datetime.now(UTC).isoformat()
def root(): return Path(os.environ.get('MM_ROOT', Path(__file__).resolve().parents[1])).resolve()
def sha(data): return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()
def digest(recipient, body): return sha(recipient.strip().lower()+'\n'+body)
def proposal_digest(recipient, body, price): return sha(json.dumps([recipient.strip().lower(),body,price],separators=(',',':')))
def timestamp(value):
    # Legacy SQLite CURRENT_TIMESTAMP is UTC without an offset. Retain raw source.
    t = dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)
def fresh(checked, days=7):
    try: return dt.timedelta(0) <= dt.datetime.now(UTC)-timestamp(checked) <= dt.timedelta(days=days)
    except (ValueError,TypeError,AttributeError): return False

def public_url(url):
    p=urlsplit(url); host=(p.hostname or '').lower().removeprefix('www.')
    if p.scheme not in ('https','http') or not host or p.username or p.password or p.port not in (None,80,443): raise ValueError('Public HTTP(S) website URL required')
    if host=='localhost' or host.endswith(('.local','.internal')): raise ValueError('Private website URL rejected')
    try:
        if not ipaddress.ip_address(host).is_global: raise ValueError('Private IP rejected')
    except ValueError as e:
        if 'Private IP' in str(e): raise
    return host

def connect(path=None, readonly=False):
    p=Path(path) if path else root()/'database/money_machine.db'
    d=sqlite3.connect('file:'+str(p)+('?mode=ro' if readonly else '?mode=rw'),uri=True,timeout=10)
    d.row_factory=sqlite3.Row;d.execute('PRAGMA foreign_keys=ON');d.execute('PRAGMA busy_timeout=10000')
    d.create_function('mm_digest',2,digest,deterministic=True)
    d.create_function('mm_artifact_valid',2,artifact_valid)
    d.create_function('mm_proposal_digest',3,proposal_digest,deterministic=True)
    return d

def event(d, action, bid, detail):
    d.execute('INSERT INTO mm_events(event_at,action,business_id,detail) VALUES(?,?,?,?)',(now(),action,bid,detail))

def backup(r=None):
    r=Path(r or root());folder=r/'backups'/('mm-v2-'+dt.datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:6]);folder.mkdir(parents=True,mode=0o700)
    items=[]
    preserve = (
        Path('money-machine/config'),
        Path('money-machine/scripts'),
        Path('money-machine/supervisor'),
        Path('state'),
        Path('approval'),
    )
    for relative in preserve:
        source = r / relative
        if not source.exists():
            continue
        archive_name = str(relative).replace('/', '-') + '.tgz'
        p = folder / archive_name
        with tarfile.open(p, 'w:gz') as t:
            t.add(source, arcname=str(relative))
        items.append({'source':str(source),'path':str(p),'sha256':sha(p.read_bytes())})
    src=r/'database/money_machine.db';dest=folder/'money_machine.db'
    # A read-only open of a WAL-mode database can fail transiently under
    # concurrent access ("unable to open database file"). Retry with bounded
    # backoff, and fall back to an rw open purely so WAL recovery can run; the
    # backup API itself never writes to the source.
    last=None
    for attempt, readonly in ((1,True),(2,True),(3,False),(4,False)):
        try:
            s=connect(src,readonly=readonly);t=sqlite3.connect(dest);s.backup(t)
            if t.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup failed integrity check')
            t.close();s.close();break
        except (sqlite3.OperationalError,ValueError) as ex:
            last=ex;time.sleep(0.25*attempt)
    else:
        raise ValueError('Backup could not read the source database: %s' % last)
    items.append({'source':str(src),'path':str(dest),'sha256':sha(dest.read_bytes())})
    (folder/'manifest.json').write_text(json.dumps({'created_at':now(),'items':items},indent=2))
    return folder

SCHEMA = '''
CREATE TABLE IF NOT EXISTS mm_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, backup_path TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mm_evidence_meta(evidence_id INTEGER PRIMARY KEY REFERENCES mm_evidence(id),status TEXT NOT NULL CHECK(status IN ('verified','refuted','partial','unverified')),method TEXT NOT NULL,confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),claim_type TEXT NOT NULL,commercial_relevance TEXT NOT NULL,expires_at TEXT NOT NULL,capture_path TEXT NOT NULL,capture_hash TEXT NOT NULL,verified_by TEXT NOT NULL,verification_count INTEGER NOT NULL CHECK(verification_count>0));
CREATE TABLE IF NOT EXISTS mm_contact_evidence(id INTEGER PRIMARY KEY,business_id INTEGER NOT NULL REFERENCES businesses(id),recipient TEXT NOT NULL,source_url TEXT NOT NULL,checked_at TEXT NOT NULL,relevance TEXT NOT NULL,permission_basis TEXT NOT NULL,permission_verified_by TEXT,unsubscribe_state TEXT NOT NULL CHECK(unsubscribe_state IN ('none_recorded','unsubscribed','unknown')),confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),capture_path TEXT NOT NULL,capture_hash TEXT NOT NULL,UNIQUE(business_id,recipient));
CREATE TABLE IF NOT EXISTS mm_demo_qa(business_id INTEGER PRIMARY KEY REFERENCES businesses(id),path TEXT NOT NULL,file_hash TEXT NOT NULL,score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),checks_json TEXT NOT NULL,passed INTEGER NOT NULL CHECK(passed IN (0,1)),checked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mm_proposals(id INTEGER PRIMARY KEY,business_id INTEGER NOT NULL REFERENCES businesses(id),evidence_id INTEGER NOT NULL REFERENCES mm_evidence(id),recipient TEXT NOT NULL,body TEXT NOT NULL,price_cents INTEGER NOT NULL CHECK(price_cents>0),digest TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL,approved_hash TEXT,approved_by TEXT,approval_ref TEXT,permission_basis TEXT,sent_at TEXT,send_receipt TEXT,invalidated_reason TEXT);
CREATE TABLE IF NOT EXISTS mm_receipts(id INTEGER PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN ('send','proposal_send','payment','refund','reply','approval')),business_id INTEGER NOT NULL REFERENCES businesses(id),object_id INTEGER,source_system TEXT NOT NULL,external_id TEXT NOT NULL,artifact_path TEXT NOT NULL,artifact_hash TEXT NOT NULL,content_hash TEXT,amount_cents INTEGER,currency TEXT NOT NULL DEFAULT 'NZD',verified_by TEXT NOT NULL,verified_at TEXT NOT NULL,occurred_at TEXT NOT NULL,UNIQUE(source_system,external_id),UNIQUE(artifact_hash,kind));
CREATE TABLE IF NOT EXISTS mm_refunds(id INTEGER PRIMARY KEY,payment_id INTEGER NOT NULL REFERENCES mm_cash(id),amount_cents INTEGER NOT NULL CHECK(amount_cents>0),receipt TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mm_scores(business_id INTEGER PRIMARY KEY REFERENCES businesses(id),evidence_id INTEGER NOT NULL REFERENCES mm_evidence(id),inputs_json TEXT NOT NULL,computed_json TEXT NOT NULL,calculated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mm_jobs(job_key TEXT PRIMARY KEY,kind TEXT NOT NULL,business_id INTEGER REFERENCES businesses(id),state TEXT NOT NULL CHECK(state IN ('pending','running','failed','completed')),checkpoint TEXT NOT NULL DEFAULT '{}',attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),lease_until TEXT,updated_at TEXT NOT NULL,error TEXT);
CREATE TABLE IF NOT EXISTS mm_model_invocations(id INTEGER PRIMARY KEY,run_key TEXT NOT NULL UNIQUE,model TEXT NOT NULL,provider TEXT NOT NULL,purpose_hash TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('blocked','started','failed','completed')),model_calls INTEGER NOT NULL DEFAULT 0 CHECK(model_calls>=0),input_tokens INTEGER,output_tokens INTEGER,cost_usd REAL NOT NULL DEFAULT 0 CHECK(cost_usd=0),created_at TEXT NOT NULL,finished_at TEXT,error TEXT);
CREATE TABLE IF NOT EXISTS mm_experiments(id INTEGER PRIMARY KEY,business_id INTEGER NOT NULL REFERENCES businesses(id),message_id INTEGER NOT NULL UNIQUE REFERENCES mm_messages(id),industry TEXT NOT NULL,problem TEXT NOT NULL,offer TEXT NOT NULL,price_band TEXT NOT NULL,style TEXT NOT NULL,demo_type TEXT NOT NULL,variant TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mm_learning(id INTEGER PRIMARY KEY,pattern TEXT NOT NULL,expected TEXT NOT NULL,actual TEXT NOT NULL,evidence_ref TEXT NOT NULL,confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),recommended_change TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS mm_evidence_business_date ON mm_evidence(business_id,checked_at DESC);
CREATE INDEX IF NOT EXISTS mm_message_business ON mm_messages(business_id,kind,sent_at);
CREATE INDEX IF NOT EXISTS mm_event_business_time ON mm_events(business_id,event_at);
CREATE INDEX IF NOT EXISTS mm_receipt_object ON mm_receipts(kind,business_id,object_id);
CREATE INDEX IF NOT EXISTS mm_deal_queue ON mm_deals(stage,due);
CREATE UNIQUE INDEX IF NOT EXISTS mm_one_initial ON mm_messages(business_id) WHERE kind='initial';
CREATE UNIQUE INDEX IF NOT EXISTS mm_unique_send_receipt ON mm_messages(send_receipt) WHERE send_receipt IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS mm_unique_proposal_receipt ON mm_proposals(send_receipt) WHERE send_receipt IS NOT NULL;
'''

def migrate(d, backup_path):
    manifest=Path(backup_path)/'manifest.json'
    if not manifest.is_file():raise ValueError('Verified backup required before migration')
    doc=json.loads(manifest.read_text())
    for item in doc['items']:
        p=Path(item.get('path',item.get('backup','')))
        if not p.is_file() or sha(p.read_bytes())!=item['sha256']:raise ValueError('Backup checksum mismatch')
    # executescript begins its own explicit transaction; no half-applied migration.
    sql='BEGIN IMMEDIATE;\n'+SCHEMA
    cols={x[1] for x in d.execute('PRAGMA table_info(mm_messages)')}
    if 'invalidated_reason' not in cols: sql+='ALTER TABLE mm_messages ADD COLUMN invalidated_reason TEXT;\n'
    sql+=TRIGGERS
    try:
        d.executescript(sql)
        d.execute('INSERT OR IGNORE INTO mm_migrations VALUES(2,?,?)',(now(),str(backup_path)))
        d.commit()
    except Exception:d.rollback();raise

# Pure SQL guards also protect callers that do not use this Python module.
# Hash UDFs intentionally fail closed on unregistered SQLite connections.
TRIGGERS = '''
DROP TRIGGER IF EXISTS prevent_unapproved_mm_messages_send;
CREATE TRIGGER prevent_unapproved_mm_messages_send BEFORE UPDATE OF sent_at,send_receipt ON mm_messages
WHEN NEW.sent_at IS NOT NULL BEGIN
 SELECT CASE WHEN OLD.sent_at IS NOT NULL OR OLD.approved_hash IS NULL OR OLD.approved_hash IS NOT mm_digest(NEW.recipient,NEW.body) OR OLD.approval_ref IS NULL OR NEW.invalidated_reason IS NOT NULL THEN RAISE(ABORT,'send blocked: exact current approval required') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_receipts r WHERE cast(r.id AS TEXT)=NEW.send_receipt AND r.kind='send' AND r.business_id=NEW.business_id AND r.object_id=NEW.id AND r.content_hash=OLD.approved_hash) THEN RAISE(ABORT,'send blocked: verified external receipt required') END;
 SELECT CASE WHEN EXISTS(SELECT 1 FROM mm_holds WHERE business_id=NEW.business_id) OR EXISTS(SELECT 1 FROM mm_deals WHERE business_id=NEW.business_id AND stage='SUPPRESSED') OR EXISTS(SELECT 1 FROM mm_suppression WHERE lower(trim(address))=lower(trim(NEW.recipient))) OR EXISTS(SELECT 1 FROM contacts WHERE lower(trim(address_or_channel))=lower(trim(NEW.recipient)) AND do_not_contact=1) THEN RAISE(ABORT,'suppression overrides approval') END;
END;
CREATE TRIGGER IF NOT EXISTS mm_message_queue_guard BEFORE INSERT ON mm_messages BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM mm_holds WHERE business_id=NEW.business_id) OR EXISTS(SELECT 1 FROM mm_deals WHERE business_id=NEW.business_id AND stage='SUPPRESSED') OR EXISTS(SELECT 1 FROM mm_suppression WHERE lower(trim(address))=lower(trim(NEW.recipient))) OR EXISTS(SELECT 1 FROM contacts WHERE lower(trim(address_or_channel))=lower(trim(NEW.recipient)) AND do_not_contact=1) THEN RAISE(ABORT,'suppressed prospect cannot enter queue') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_evidence WHERE id=NEW.evidence_id AND business_id=NEW.business_id) THEN RAISE(ABORT,'evidence belongs to different prospect') END;
END;
CREATE TRIGGER IF NOT EXISTS mm_message_edit AFTER UPDATE OF body,recipient,evidence_id,digest,kind,parent_id,business_id,invalidated_reason ON mm_messages
WHEN NEW.body IS NOT OLD.body OR NEW.recipient IS NOT OLD.recipient OR NEW.evidence_id IS NOT OLD.evidence_id OR NEW.digest IS NOT OLD.digest OR NEW.kind IS NOT OLD.kind OR NEW.parent_id IS NOT OLD.parent_id OR NEW.business_id IS NOT OLD.business_id OR NEW.invalidated_reason IS NOT OLD.invalidated_reason BEGIN
 UPDATE mm_messages SET approved_hash=NULL,approved_by=NULL,approval_ref=NULL,permission_basis=NULL WHERE id=NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS mm_sent_immutable BEFORE UPDATE OF body,recipient,evidence_id,digest,kind,parent_id,business_id ON mm_messages WHEN OLD.sent_at IS NOT NULL BEGIN SELECT RAISE(ABORT,'sent content is immutable');END;
CREATE TRIGGER IF NOT EXISTS mm_proposal_edit AFTER UPDATE OF recipient,body,price_cents,evidence_id,digest,invalidated_reason ON mm_proposals WHEN NEW.recipient IS NOT OLD.recipient OR NEW.body IS NOT OLD.body OR NEW.price_cents IS NOT OLD.price_cents OR NEW.evidence_id IS NOT OLD.evidence_id OR NEW.digest IS NOT OLD.digest OR NEW.invalidated_reason IS NOT OLD.invalidated_reason BEGIN UPDATE mm_proposals SET approved_hash=NULL,approved_by=NULL,approval_ref=NULL,permission_basis=NULL WHERE id=NEW.id;END;
CREATE TRIGGER IF NOT EXISTS mm_proposal_insert BEFORE INSERT ON mm_proposals WHEN NEW.sent_at IS NOT NULL BEGIN SELECT RAISE(ABORT,'proposal requires draft and human approval');END;
CREATE TRIGGER IF NOT EXISTS mm_proposal_send BEFORE UPDATE OF sent_at,send_receipt ON mm_proposals WHEN NEW.sent_at IS NOT NULL BEGIN
 SELECT CASE WHEN OLD.sent_at IS NOT NULL OR OLD.approved_hash IS NULL OR OLD.approved_hash IS NOT mm_proposal_digest(NEW.recipient,NEW.body,NEW.price_cents) OR OLD.approval_ref IS NULL OR NEW.invalidated_reason IS NOT NULL THEN RAISE(ABORT,'proposal requires exact price and content approval') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_receipts WHERE cast(id AS TEXT)=NEW.send_receipt AND kind='proposal_send' AND business_id=NEW.business_id AND object_id=NEW.id AND content_hash=OLD.approved_hash) THEN RAISE(ABORT,'proposal receipt required') END;
 SELECT CASE WHEN EXISTS(SELECT 1 FROM mm_holds WHERE business_id=NEW.business_id) OR EXISTS(SELECT 1 FROM mm_deals WHERE business_id=NEW.business_id AND stage='SUPPRESSED') OR EXISTS(SELECT 1 FROM mm_suppression WHERE lower(trim(address))=lower(trim(NEW.recipient))) THEN RAISE(ABORT,'suppression overrides proposal approval') END;
END;
CREATE TRIGGER IF NOT EXISTS mm_cash_proof BEFORE INSERT ON mm_cash BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_receipts WHERE cast(id AS TEXT)=NEW.receipt AND kind='payment' AND business_id=NEW.business_id AND amount_cents=NEW.amount_cents AND currency='NZD') THEN RAISE(ABORT,'payment evidence required') END;
END;
CREATE TRIGGER IF NOT EXISTS mm_cash_immutable BEFORE UPDATE ON mm_cash BEGIN SELECT RAISE(ABORT,'cash ledger immutable; record a refund');END;
CREATE TRIGGER IF NOT EXISTS mm_cash_no_delete BEFORE DELETE ON mm_cash BEGIN SELECT RAISE(ABORT,'cash ledger immutable; record a refund');END;
CREATE TRIGGER IF NOT EXISTS mm_refund_proof BEFORE INSERT ON mm_refunds BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_receipts r JOIN mm_cash c ON c.id=NEW.payment_id WHERE cast(r.id AS TEXT)=NEW.receipt AND r.kind='refund' AND r.object_id=c.id AND r.business_id=c.business_id AND r.amount_cents=NEW.amount_cents AND r.currency='NZD') THEN RAISE(ABORT,'refund evidence required') END;
 SELECT CASE WHEN NEW.amount_cents+coalesce((SELECT sum(amount_cents) FROM mm_refunds WHERE payment_id=NEW.payment_id),0)>(SELECT amount_cents FROM mm_cash WHERE id=NEW.payment_id) THEN RAISE(ABORT,'refund exceeds payment') END;
END;
CREATE TRIGGER IF NOT EXISTS mm_refund_immutable BEFORE UPDATE ON mm_refunds BEGIN SELECT RAISE(ABORT,'refund ledger immutable');END;
CREATE TRIGGER IF NOT EXISTS mm_refund_no_delete BEFORE DELETE ON mm_refunds BEGIN SELECT RAISE(ABORT,'refund ledger immutable');END;
CREATE TRIGGER IF NOT EXISTS mm_receipt_immutable BEFORE UPDATE ON mm_receipts BEGIN SELECT RAISE(ABORT,'receipt immutable');END;
CREATE TRIGGER IF NOT EXISTS mm_receipt_no_delete BEFORE DELETE ON mm_receipts BEGIN SELECT RAISE(ABORT,'receipt immutable');END;
CREATE TRIGGER IF NOT EXISTS mm_hold_no_delete BEFORE DELETE ON mm_holds BEGIN SELECT RAISE(ABORT,'manual reconciliation required; no unsuppression path');END;
CREATE TRIGGER IF NOT EXISTS mm_suppression_no_delete BEFORE DELETE ON mm_suppression BEGIN SELECT RAISE(ABORT,'no unsuppression path');END;
CREATE TRIGGER IF NOT EXISTS mm_suppression_revoke AFTER INSERT ON mm_suppression BEGIN
 UPDATE mm_messages SET approved_hash=NULL,approval_ref=NULL WHERE lower(trim(recipient))=lower(trim(NEW.address));
 UPDATE mm_proposals SET approved_hash=NULL,approval_ref=NULL WHERE lower(trim(recipient))=lower(trim(NEW.address));
 UPDATE mm_deals SET stage='SUPPRESSED',next_action='Do not contact',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE business_id IN(SELECT business_id FROM mm_messages WHERE lower(trim(recipient))=lower(trim(NEW.address)) UNION SELECT business_id FROM contacts WHERE lower(trim(address_or_channel))=lower(trim(NEW.address)));
END;
CREATE TRIGGER IF NOT EXISTS mm_stage_guard BEFORE UPDATE OF stage ON mm_deals BEGIN
 SELECT CASE WHEN (OLD.stage='SUPPRESSED' OR EXISTS(SELECT 1 FROM mm_holds WHERE business_id=NEW.business_id)) AND NEW.stage!='SUPPRESSED' THEN RAISE(ABORT,'suppressed businesses cannot reopen') END;
 SELECT CASE WHEN NEW.stage='SENT' AND NOT EXISTS(SELECT 1 FROM mm_messages m JOIN mm_receipts r ON cast(r.id AS TEXT)=m.send_receipt WHERE m.business_id=NEW.business_id AND m.sent_at IS NOT NULL AND r.kind='send') THEN RAISE(ABORT,'SENT requires external-send evidence') END;
 SELECT CASE WHEN NEW.stage='PROPOSAL_SENT' AND NOT EXISTS(SELECT 1 FROM mm_proposals p JOIN mm_receipts r ON cast(r.id AS TEXT)=p.send_receipt WHERE p.business_id=NEW.business_id AND p.sent_at IS NOT NULL AND r.kind='proposal_send') THEN RAISE(ABORT,'proposal send evidence required') END;
 SELECT CASE WHEN NEW.stage='WON' AND NOT EXISTS(SELECT 1 FROM mm_cash WHERE business_id=NEW.business_id) THEN RAISE(ABORT,'WON requires payment evidence in current workflow') END;
END;
CREATE TRIGGER IF NOT EXISTS mm_stage_event AFTER UPDATE OF stage ON mm_deals WHEN NEW.stage IS NOT OLD.stage BEGIN
 UPDATE mm_deals SET updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE business_id=NEW.business_id;
 INSERT INTO mm_events(event_at,action,business_id,detail) VALUES(strftime('%Y-%m-%dT%H:%M:%fZ','now'),'stage_transition',NEW.business_id,OLD.stage||' -> '||NEW.stage);
END;
CREATE TRIGGER IF NOT EXISTS mm_legacy_send_closed BEFORE UPDATE OF sent_at,approved_by_human ON outreach WHEN NEW.sent_at IS NOT NULL AND (NEW.sent_at IS NOT OLD.sent_at OR NEW.approved_by_human IS NOT OLD.approved_by_human) BEGIN SELECT RAISE(ABORT,'legacy send recording retired; use verified receipt workflow');END;
CREATE TRIGGER IF NOT EXISTS mm_legacy_revenue_closed BEFORE INSERT ON revenue WHEN NEW.collected_nzd!=0 BEGIN SELECT RAISE(ABORT,'use verified cash ledger');END;
CREATE TRIGGER IF NOT EXISTS mm_legacy_revenue_update BEFORE UPDATE OF collected_nzd ON revenue WHEN NEW.collected_nzd IS NOT OLD.collected_nzd BEGIN SELECT RAISE(ABORT,'use verified cash ledger');END;
'''

TRIGGERS += '''
CREATE TRIGGER IF NOT EXISTS mm_message_approval_proof BEFORE UPDATE OF approved_hash ON mm_messages WHEN NEW.approved_hash IS NOT NULL BEGIN
 SELECT CASE WHEN NEW.invalidated_reason IS NOT NULL OR NOT EXISTS(SELECT 1 FROM mm_receipts WHERE cast(id AS TEXT)=NEW.approval_ref AND kind='approval' AND business_id=NEW.business_id AND object_id=NEW.id AND content_hash=NEW.approved_hash AND verified_by=NEW.approved_by AND mm_artifact_valid(artifact_path,artifact_hash)=1) THEN RAISE(ABORT,'approval evidence artifact required') END;
END;
CREATE TRIGGER IF NOT EXISTS mm_message_readiness_guard BEFORE UPDATE OF approved_hash,sent_at ON mm_messages WHEN NEW.approved_hash IS NOT NULL OR (NEW.sent_at IS NOT OLD.sent_at AND NEW.sent_at IS NOT NULL) BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_evidence e JOIN mm_evidence_meta m ON m.evidence_id=e.id WHERE e.id=NEW.evidence_id AND e.business_id=NEW.business_id AND m.status='verified' AND m.confidence>=0.7 AND julianday(e.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND julianday(m.expires_at)>=julianday('now') AND mm_artifact_valid(m.capture_path,m.capture_hash)=1) THEN RAISE(ABORT,'current verified captured evidence required') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_contact_evidence c WHERE c.business_id=NEW.business_id AND lower(c.recipient)=lower(NEW.recipient) AND length(c.permission_verified_by)>0 AND length(c.permission_basis)>0 AND c.unsubscribe_state='none_recorded' AND c.confidence>=0.7 AND julianday(c.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND mm_artifact_valid(c.capture_path,c.capture_hash)=1) THEN RAISE(ABORT,'verified contact source and permission required') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_demo_qa q WHERE q.business_id=NEW.business_id AND q.passed=1 AND q.score>=80 AND julianday(q.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND mm_artifact_valid(q.path,q.file_hash)=1) THEN RAISE(ABORT,'current demo QA required') END;
 SELECT CASE WHEN EXISTS(SELECT 1 FROM mm_holds WHERE business_id=NEW.business_id) OR EXISTS(SELECT 1 FROM mm_deals WHERE business_id=NEW.business_id AND stage='SUPPRESSED') OR EXISTS(SELECT 1 FROM mm_suppression WHERE lower(trim(address))=lower(trim(NEW.recipient))) OR EXISTS(SELECT 1 FROM contacts WHERE lower(trim(address_or_channel))=lower(trim(NEW.recipient)) AND do_not_contact=1) THEN RAISE(ABORT,'suppression overrides approval') END;
END;
CREATE TRIGGER IF NOT EXISTS mm_message_sent_record_immutable BEFORE UPDATE OF sent_at,send_receipt ON mm_messages WHEN OLD.sent_at IS NOT NULL AND (NEW.sent_at IS NOT OLD.sent_at OR NEW.send_receipt IS NOT OLD.send_receipt) BEGIN SELECT RAISE(ABORT,'recorded send is immutable');END;
CREATE TRIGGER IF NOT EXISTS mm_message_approval_insert BEFORE INSERT ON mm_messages WHEN NEW.approved_hash IS NOT NULL BEGIN SELECT RAISE(ABORT,'create draft before recording exact human approval');END;

CREATE TRIGGER IF NOT EXISTS mm_proposal_approval_proof BEFORE UPDATE OF approved_hash ON mm_proposals WHEN NEW.approved_hash IS NOT NULL BEGIN
 SELECT CASE WHEN NEW.invalidated_reason IS NOT NULL OR NOT EXISTS(SELECT 1 FROM mm_receipts WHERE cast(id AS TEXT)=NEW.approval_ref AND kind='approval' AND business_id=NEW.business_id AND object_id=NEW.id AND content_hash=NEW.approved_hash AND verified_by=NEW.approved_by AND mm_artifact_valid(artifact_path,artifact_hash)=1) THEN RAISE(ABORT,'approval evidence artifact required') END;
END;
CREATE TRIGGER IF NOT EXISTS mm_proposal_readiness_guard BEFORE UPDATE OF approved_hash,sent_at ON mm_proposals WHEN NEW.approved_hash IS NOT NULL OR (NEW.sent_at IS NOT OLD.sent_at AND NEW.sent_at IS NOT NULL) BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_evidence e JOIN mm_evidence_meta m ON m.evidence_id=e.id WHERE e.id=NEW.evidence_id AND e.business_id=NEW.business_id AND m.status='verified' AND m.confidence>=0.7 AND julianday(e.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND julianday(m.expires_at)>=julianday('now') AND mm_artifact_valid(m.capture_path,m.capture_hash)=1) THEN RAISE(ABORT,'current verified captured evidence required') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_contact_evidence c WHERE c.business_id=NEW.business_id AND lower(c.recipient)=lower(NEW.recipient) AND length(c.permission_verified_by)>0 AND length(c.permission_basis)>0 AND c.unsubscribe_state='none_recorded' AND c.confidence>=0.7 AND julianday(c.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND mm_artifact_valid(c.capture_path,c.capture_hash)=1) THEN RAISE(ABORT,'verified contact source and permission required') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM mm_demo_qa q WHERE q.business_id=NEW.business_id AND q.passed=1 AND q.score>=80 AND julianday(q.checked_at) BETWEEN julianday('now','-7 days') AND julianday('now') AND mm_artifact_valid(q.path,q.file_hash)=1) THEN RAISE(ABORT,'current demo QA required') END;
 SELECT CASE WHEN EXISTS(SELECT 1 FROM mm_holds WHERE business_id=NEW.business_id) OR EXISTS(SELECT 1 FROM mm_deals WHERE business_id=NEW.business_id AND stage='SUPPRESSED') OR EXISTS(SELECT 1 FROM mm_suppression WHERE lower(trim(address))=lower(trim(NEW.recipient))) OR EXISTS(SELECT 1 FROM contacts WHERE lower(trim(address_or_channel))=lower(trim(NEW.recipient)) AND do_not_contact=1) THEN RAISE(ABORT,'suppression overrides approval') END;
END;
CREATE TRIGGER IF NOT EXISTS mm_proposal_sent_record_immutable BEFORE UPDATE OF sent_at,send_receipt ON mm_proposals WHEN OLD.sent_at IS NOT NULL AND (NEW.sent_at IS NOT OLD.sent_at OR NEW.send_receipt IS NOT OLD.send_receipt) BEGIN SELECT RAISE(ABORT,'recorded send is immutable');END;
CREATE TRIGGER IF NOT EXISTS mm_proposal_approval_insert BEFORE INSERT ON mm_proposals WHEN NEW.approved_hash IS NOT NULL BEGIN SELECT RAISE(ABORT,'create draft before recording exact human approval');END;

CREATE TRIGGER IF NOT EXISTS mm_proposal_sent_content_immutable BEFORE UPDATE OF recipient,body,price_cents,evidence_id,digest,business_id ON mm_proposals WHEN OLD.sent_at IS NOT NULL BEGIN SELECT RAISE(ABORT,'sent proposal immutable');END;
CREATE TRIGGER IF NOT EXISTS mm_evidence_change_revoke AFTER UPDATE ON mm_evidence BEGIN
 UPDATE mm_messages SET approved_hash=NULL,approval_ref=NULL WHERE evidence_id=NEW.id;
 UPDATE mm_proposals SET approved_hash=NULL,approval_ref=NULL WHERE evidence_id=NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS mm_evidence_meta_change_revoke AFTER UPDATE ON mm_evidence_meta BEGIN
 UPDATE mm_messages SET approved_hash=NULL,approval_ref=NULL WHERE evidence_id=NEW.evidence_id;
 UPDATE mm_proposals SET approved_hash=NULL,approval_ref=NULL WHERE evidence_id=NEW.evidence_id;
END;
CREATE TRIGGER IF NOT EXISTS mm_contact_change_revoke AFTER UPDATE ON mm_contact_evidence BEGIN
 UPDATE mm_messages SET approved_hash=NULL,approval_ref=NULL WHERE business_id=NEW.business_id;
 UPDATE mm_proposals SET approved_hash=NULL,approval_ref=NULL WHERE business_id=NEW.business_id;
END;
'''

TRIGGERS += '''
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
'''

def business(d,bid):
    b=d.execute('SELECT * FROM businesses WHERE id=? AND is_dummy=0',(bid,)).fetchone()
    if not b:raise ValueError('Real business ID required')
    return b

def eligible(d,bid,address=None):
    business(d,bid)
    if d.execute('SELECT 1 FROM mm_holds WHERE business_id=?',(bid,)).fetchone() or d.execute("SELECT 1 FROM mm_deals WHERE business_id=? AND stage='SUPPRESSED'",(bid,)).fetchone():raise ValueError('Suppressed business / unresolved legacy hold')
    if address is None:return
    from mm_email import normalize_email
    address,error=normalize_email(address)
    if error:raise ValueError(error)
    lookup=address.casefold()
    if address.count('@')!=1 or any(x.isspace() for x in address) or any(x in address for x in '<>,;'):raise ValueError('One email address required')
    if d.execute('SELECT 1 FROM mm_suppression WHERE lower(trim(address))=?',(lookup,)).fetchone() or d.execute('SELECT 1 FROM contacts WHERE lower(trim(address_or_channel))=? AND do_not_contact=1',(lookup,)).fetchone():raise ValueError('Suppressed recipient')
    if d.execute("SELECT 1 FROM outreach WHERE instr(lower(draft),?)>0 AND (sent_at IS NOT NULL OR lower(coalesce(unsubscribe_status,''))='unsubscribed')",(lookup,)).fetchone():raise ValueError('Unreconciled legacy contact')
    return address

def artifact_valid(path, expected):
    try:
        p=Path(path);return p.is_file() and bool(p.stat().st_size) and sha(p.read_bytes())==expected
    except OSError:return False

def evidence(d,eid,bid,allow_partial=False):
    e=d.execute('SELECT e.*,m.status,m.confidence,m.expires_at,m.capture_path,m.capture_hash,m.method FROM mm_evidence e LEFT JOIN mm_evidence_meta m ON m.evidence_id=e.id WHERE e.id=? AND e.business_id=?',(eid,bid)).fetchone()
    if not e or not fresh(e['checked_at']):raise ValueError('Missing, future-dated or stale evidence')
    if eid != latest_evidence(d,bid):raise ValueError('A newer evidence check supersedes this packet')
    if e['status'] not in (('verified','partial') if allow_partial else ('verified',)):raise ValueError('Commercial claim is unverified, partial or refuted')
    if timestamp(e['expires_at'])<dt.datetime.now(UTC) or e['confidence']<0.7:raise ValueError('Evidence expired or below confidence threshold')
    if not artifact_valid(e['capture_path'],e['capture_hash']):raise ValueError('Evidence capture missing or modified')
    return e

def latest_evidence(d,bid):
    e=d.execute('SELECT id FROM mm_evidence WHERE business_id=? ORDER BY julianday(checked_at) DESC,id DESC LIMIT 1',(bid,)).fetchone()
    if not e:raise ValueError('Dated evidence required')
    return e[0]

def readiness(d,bid,eid,address):
    reasons=[]
    for check in (lambda:eligible(d,bid,address),lambda:evidence(d,eid,bid)):
        try:check()
        except ValueError as e:reasons.append(str(e))
    c=d.execute('SELECT * FROM mm_contact_evidence WHERE business_id=? AND lower(recipient)=?',(bid,address.strip().lower())).fetchone()
    if not c or not fresh(c['checked_at']) or not artifact_valid(c['capture_path'],c['capture_hash']):reasons.append('Fresh contact source capture required')
    elif not c['permission_verified_by'] or not c['permission_basis'] or c['unsubscribe_state']!='none_recorded' or c['confidence']<0.7:reasons.append('Human-verified relevance and contact permission required')
    q=d.execute('SELECT * FROM mm_demo_qa WHERE business_id=?',(bid,)).fetchone()
    if not q or not q['passed'] or q['score']<80 or not fresh(q['checked_at']) or not artifact_valid(q['path'],q['file_hash']):reasons.append('Current demo QA at least 80/100 required')
    if d.execute("SELECT 1 FROM sqlite_master WHERE name='email_policy' AND type='table'").fetchone():
        mode=d.execute('SELECT mode FROM email_policy WHERE id=1').fetchone()[0]
        if mode!='shadow':
            from mm_email_store import require_email
            try:require_email(d,bid,address)
            except ValueError as e:reasons.append(str(e))
    return reasons

def record_evidence(d,bid,url,observation,limitation,path,status,method,confidence,claim_type='conversion',relevance='Unquantified',verifier='local review',days=7):
    business(d,bid);public_url(url);p=Path(path).resolve()
    if not p.is_file() or not p.stat().st_size:raise ValueError('Nonempty evidence capture required')
    if days<1 or days>7:raise ValueError('Evidence expiry must be 1-7 days')
    c=d.execute('INSERT INTO mm_evidence(business_id,url,observation,limitation,checked_at) VALUES(?,?,?,?,?)',(bid,url,observation,limitation,now()));eid=c.lastrowid
    d.execute('INSERT INTO mm_evidence_meta VALUES(?,?,?,?,?,?,?,?,?,?,?)',(eid,status,method,confidence,claim_type,relevance,(dt.datetime.now(UTC)+dt.timedelta(days=days)).isoformat(),str(p),sha(p.read_bytes()),verifier,1))
    # New checks invalidate old approvals; packets must bind to latest evidence.
    d.execute('UPDATE mm_messages SET approved_hash=NULL,approval_ref=NULL WHERE business_id=?',(bid,))
    d.execute('UPDATE mm_proposals SET approved_hash=NULL,approval_ref=NULL WHERE business_id=?',(bid,))
    event(d,'evidence_recorded',bid,json.dumps({'id':eid,'status':status,'method':method}));return eid

def record_contact(d,bid,address,url,path,relevance,permission_basis='Unconfirmed',permission_verified_by=None):
    from mm_email_store import require_email
    selected=require_email(d,bid,address)
    address=eligible(d,bid,address);public_url(url);p=Path(path).resolve()
    if not p.is_file() or not p.stat().st_size:raise ValueError('Nonempty selected-email source capture required')
    if not d.execute('SELECT 1 FROM email_evidence WHERE candidate_id=? AND url=? AND capture_path=? AND evidence_hash=?',(selected['candidate_id'],url,str(p),sha(p.read_bytes()))).fetchone():raise ValueError('Contact capture must match the selected email provenance')
    existing=d.execute('SELECT unsubscribe_state FROM mm_contact_evidence WHERE business_id=? AND lower(recipient)=?',(bid,address.casefold())).fetchone()
    if existing and existing[0]=='unsubscribed':raise ValueError('Unsubscribed contact cannot be reset by discovery')
    confidence=d.execute('SELECT confidence_score FROM email_verifications WHERE id=?',(selected['verification_id'],)).fetchone()[0]/100
    d.execute('INSERT INTO mm_contact_evidence(business_id,recipient,source_url,checked_at,relevance,permission_basis,permission_verified_by,unsubscribe_state,confidence,capture_path,capture_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(business_id,recipient) DO UPDATE SET source_url=excluded.source_url,checked_at=excluded.checked_at,relevance=excluded.relevance,permission_basis=excluded.permission_basis,permission_verified_by=excluded.permission_verified_by,confidence=excluded.confidence,capture_path=excluded.capture_path,capture_hash=excluded.capture_hash',(bid,address,url,now(),relevance,permission_basis,permission_verified_by,'none_recorded',confidence,str(p),sha(p.read_bytes())))
    d.execute('UPDATE mm_messages SET approved_hash=NULL,approval_ref=NULL WHERE business_id=?',(bid,));d.execute('UPDATE mm_proposals SET approved_hash=NULL,approval_ref=NULL WHERE business_id=?',(bid,))
    event(d,'contact_source_recorded',bid,url)

def change_stage(d,bid,stage,action,due=None):
    business(d,bid)
    if stage not in STAGES:raise ValueError('Unknown canonical stage')
    if stage!='SUPPRESSED':eligible(d,bid)
    if due:dt.date.fromisoformat(due)
    if stage in ('DRAFT_READY','AWAITING_APPROVAL','APPROVED_TO_SEND','PROPOSAL_READY'):
        table='mm_proposals' if stage=='PROPOSAL_READY' else 'mm_messages'
        m=d.execute(f'SELECT * FROM {table} WHERE business_id=? AND invalidated_reason IS NULL ORDER BY id DESC LIMIT 1',(bid,)).fetchone()
        if not m:raise ValueError('Valid packet required')
        reasons=readiness(d,bid,m['evidence_id'],m['recipient'])
        if reasons:raise ValueError('; '.join(reasons))
        if stage=='APPROVED_TO_SEND' and not m['approved_hash']:raise ValueError('Human approval required')
    if stage=='VERIFIED':evidence(d,latest_evidence(d,bid),bid)
    if stage in ('REPLIED','CALL_OR_DISCOVERY') and not d.execute("SELECT 1 FROM mm_receipts WHERE business_id=? AND kind='reply'",(bid,)).fetchone():raise ValueError('External reply evidence required')
    d.execute('UPDATE mm_deals SET stage=?,next_action=?,due=?,updated_at=? WHERE business_id=?',(stage,action,due,now(),bid))

def create_draft(d,bid,address,body,parent=None):
    from mm_outreach import require_copy
    require_copy(body,initial=not parent)
    address=eligible(d,bid,address);eid=latest_evidence(d,bid);evidence(d,eid,bid)
    from mm_email_store import require_email
    require_email(d,bid,address)
    if len(body)<80:raise ValueError('Complete draft required')
    if parent:
        m=d.execute('SELECT * FROM mm_messages WHERE id=?',(parent,)).fetchone()
        if not m or m['business_id']!=bid or m['recipient']!=address or not m['sent_at'] or not m['send_receipt'] or m['reply'] or m['kind']!='initial' or dt.datetime.now(UTC)-timestamp(m['sent_at'])<dt.timedelta(days=7):raise ValueError('One due, unreplied initial send required')
    c=d.execute('INSERT INTO mm_messages(business_id,evidence_id,recipient,body,digest,kind,parent_id,created_at) VALUES(?,?,?,?,?,?,?,?)',(bid,eid,address,body,digest(address,body),'followup' if parent else 'initial',parent,now()))
    event(d,'draft',bid,str(c.lastrowid));return c.lastrowid

def create_proposal(d,bid,address,body,price_cents):
    from mm_outreach import require_copy
    require_copy(body,initial=False)
    address=eligible(d,bid,address);eid=latest_evidence(d,bid);evidence(d,eid,bid)
    from mm_email_store import require_email
    require_email(d,bid,address)
    if type(price_cents)!=int or price_cents<=0:raise ValueError('Positive whole cents required')
    c=d.execute('INSERT INTO mm_proposals(business_id,evidence_id,recipient,body,price_cents,digest,created_at) VALUES(?,?,?,?,?,?,?)',(bid,eid,address,body,price_cents,proposal_digest(address,body,price_cents),now()));event(d,'proposal_draft',bid,str(c.lastrowid));return c.lastrowid

def approve(d,oid,body,by,approval_receipt,proposal=False):
    table='mm_proposals' if proposal else 'mm_messages';m=d.execute(f'SELECT * FROM {table} WHERE id=?',(oid,)).fetchone()
    if not m or m['sent_at'] or m['invalidated_reason']:raise ValueError('Valid unsent packet required')
    if m['body']!=body:raise ValueError('Revise draft separately; approval must match exact stored body')
    from mm_outreach import require_copy
    require_copy(body,initial=not proposal and m['kind']=='initial')
    reasons=readiness(d,m['business_id'],m['evidence_id'],m['recipient'])
    if reasons:raise ValueError('; '.join(reasons))
    if len(by.strip())<2 or '[' in body or 'reply' not in body.lower() or not any(s in body.lower() for s in ('no thanks','unsubscribe')):raise ValueError('Complete human identity and opt-out required')
    h=proposal_digest(m['recipient'],body,m['price_cents']) if proposal else digest(m['recipient'],body)
    r=receipt(d,approval_receipt,'approval',m['business_id'],oid,h)
    if r['verified_by']!=by:raise ValueError('Approval evidence approver mismatch')
    d.execute(f'UPDATE {table} SET approved_hash=?,approved_by=?,approval_ref=?,permission_basis=? WHERE id=?',(h,by,str(approval_receipt),'See verified contact evidence',oid));event(d,'human_approval_recorded',m['business_id'],str(approval_receipt))

def receipt(d,rid,kind,bid,oid=None,content_hash=None):
    r=d.execute('SELECT * FROM mm_receipts WHERE id=?',(rid,)).fetchone()
    if not r or r['kind']!=kind or r['business_id']!=bid or (oid is not None and r['object_id']!=oid) or (content_hash is not None and r['content_hash']!=content_hash):raise ValueError('Matching verified receipt required')
    if not artifact_valid(r['artifact_path'],r['artifact_hash']):raise ValueError('Receipt artifact missing or changed')
    return r

def import_receipt(d,path):
    """Import an operator-reviewed evidence envelope, never a bare receipt string.
    The importer records attestation, not a claim of independent bank/mail access.
    """
    p=Path(path).resolve();a=json.loads(p.read_text());required=['kind','business_id','source_system','external_id','artifact_path','artifact_hash','verified_by','verified_at','occurred_at','verification_note']
    if any(not a.get(k) for k in required):raise ValueError('Complete provider evidence and human verification envelope required')
    if len(a['verification_note'])<40 or not fresh(a['verified_at'],7) or timestamp(a['occurred_at'])>dt.datetime.now(UTC):raise ValueError('Current human verification, evidence note and nonfuture event required')
    business(d,a['business_id'])
    if not artifact_valid(a['artifact_path'],a['artifact_hash']):raise ValueError('Evidence artifact hash mismatch')
    if a['source_system'].lower() in ('manual','test','fixture','unknown','none'):raise ValueError('External source system required')
    c=d.execute('INSERT INTO mm_receipts(kind,business_id,object_id,source_system,external_id,artifact_path,artifact_hash,content_hash,amount_cents,currency,verified_by,verified_at,occurred_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',tuple(a.get(k) for k in ['kind','business_id','object_id','source_system','external_id','artifact_path','artifact_hash','content_hash','amount_cents'])+(a.get('currency','NZD'),a['verified_by'],a['verified_at'],a['occurred_at']))
    event(d,'evidence_attestation_imported',a['business_id'],str(c.lastrowid));return c.lastrowid

def record_sent(d,oid,rid,proposal=False):
    table='mm_proposals' if proposal else 'mm_messages';m=d.execute(f'SELECT * FROM {table} WHERE id=?',(oid,)).fetchone()
    if not m or m['sent_at'] or m['invalidated_reason']:raise ValueError('Unsent valid packet required')
    from mm_outreach import require_copy
    require_copy(m['body'],initial=not proposal and m['kind']=='initial')
    reasons=readiness(d,m['business_id'],m['evidence_id'],m['recipient'])
    if reasons:raise ValueError('; '.join(reasons))
    h=proposal_digest(m['recipient'],m['body'],m['price_cents']) if proposal else digest(m['recipient'],m['body'])
    if m['approved_hash']!=h:raise ValueError('Exact approval required')
    receipt(d,m['approval_ref'],'approval',m['business_id'],oid,h)
    r=receipt(d,rid,'proposal_send' if proposal else 'send',m['business_id'],oid,h)
    d.execute(f'UPDATE {table} SET sent_at=?,send_receipt=? WHERE id=?',(r['occurred_at'],str(rid),oid))
    change_stage(d,m['business_id'],'PROPOSAL_SENT' if proposal else 'SENT','Review actual reply; no automatic follow-up')
    event(d,'verified_send_recorded',m['business_id'],str(rid))

def cash(d,bid,cents,rid):
    if type(cents)!=int or cents<=0:raise ValueError('Positive whole cents required')
    r=receipt(d,rid,'payment',bid)
    if r['amount_cents']!=cents or r['currency']!='NZD':raise ValueError('Payment amount or currency mismatch')
    d.execute('INSERT INTO mm_cash(business_id,amount_cents,receipt,received_at) VALUES(?,?,?,?)',(bid,cents,str(rid),r['occurred_at']));event(d,'payment_recorded',bid,str(rid))

def refund(d,pid,cents,rid):
    p=d.execute('SELECT * FROM mm_cash WHERE id=?',(pid,)).fetchone()
    if not p:raise ValueError('Payment required')
    receipt(d,rid,'refund',p['business_id'],pid)
    d.execute('INSERT INTO mm_refunds(payment_id,amount_cents,receipt,created_at) VALUES(?,?,?,?)',(pid,cents,str(rid),now()))
