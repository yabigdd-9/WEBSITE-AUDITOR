"""Evidence-driven outreach approval and auditable send ledger.

Approval is never "the model thinks this looks fine". Every mandatory gate is
checked against machine-readable evidence in the database/filesystem. All gate
results, the deciding actor and the exact approved content hash are recorded.

State machine for an approval request:
    PENDING -> CHECKING -> APPROVED | REJECTED | NEEDS_REVIEW
UNKNOWN can never become APPROVED: missing evidence fails the gate.

Send execution is separate (this module sends nothing); it decides, records,
rate-limits, prevents duplicates, and quarantines on abnormal signals.
"""
import datetime as dt
import json
import re

from mm_core import now, digest, timestamp
from mm_pipeline import transition, item, rate_ok, log

APPROVAL_STATES = ('PENDING', 'CHECKING', 'APPROVED', 'REJECTED', 'NEEDS_REVIEW')

DDL = """
CREATE TABLE IF NOT EXISTS approval_records(
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  status TEXT NOT NULL CHECK(status IN ('PENDING','CHECKING','APPROVED','REJECTED','NEEDS_REVIEW')),
  gates_json TEXT,
  reason TEXT,
  actor TEXT,
  content_hash TEXT,
  created_at TEXT NOT NULL,
  decided_at TEXT);
CREATE TABLE IF NOT EXISTS outreach_send_ledger(
  idempotency_key TEXT PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  recipient TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  campaign TEXT NOT NULL,
  approval_id INTEGER REFERENCES approval_records(id),
  transport TEXT,
  status TEXT NOT NULL CHECK(status IN ('planned','sent','bounced','failed','quarantined')),
  retry_count INTEGER NOT NULL DEFAULT 0,
  provider_message_id TEXT,
  sent_at TEXT,
  bounce TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL);
"""

BOUNCE_QUARANTINE_RATE = 0.2   # >20% bounce in the ledger
BOUNCE_QUARANTINE_MIN = 5      # ...with at least this many sends recorded
DAILY_SEND_CAP = 20            # consent_gate policy: 20/day

SECRET_PATTERNS = [
    r'-----BEGIN [A-Z ]*PRIVATE KEY-----',
    r'(?i)api[_-]?key\s*[:=]\s*["\']?[A-Za-z0-9_\-]{16,}',
    r'(?i)password\s*[:=]\s*\S+',
    r'ya29\.[A-Za-z0-9_\-]+',            # Google OAuth access token
    r'sk-[A-Za-z0-9]{20,}',              # OpenAI-style key
]


def migrate(d):
    d.executescript(DDL)


def contains_secret(text):
    for rx in SECRET_PATTERNS:
        if re.search(rx, text or ''):
            return rx
    return None


# ---------------------------------------------------------------------------
# Mandatory gates — every one needs machine-readable evidence to pass
# ---------------------------------------------------------------------------

def _gate_identity(d, bid):
    r = d.execute("SELECT name,public_website FROM businesses WHERE id=?", (bid,)).fetchone()
    ok = bool(r and r['name'] and r['public_website'])
    return ok, {'name': r['name'] if r else None,
                'website': r['public_website'] if r else None}


def _gate_pipeline_state(d, bid):
    try:
        r = item(d, bid)
    except ValueError:
        return False, {'state': 'UNKNOWN'}
    ok = r['state'] in ('OUTREACH_PENDING', 'APPROVAL_PENDING', 'APPROVED')
    return ok, {'state': r['state']}


def _gate_audit_evidence(d, bid):
    r = d.execute("SELECT id FROM mm_evidence WHERE business_id=? ORDER BY id DESC LIMIT 1",
                  (bid,)).fetchone()
    return bool(r), {'evidence_id': r['id'] if r else None}


def _gate_verified_email(d, bid):
    rows = d.execute(
        "SELECT v.email,v.result_json FROM email_verifications v "
        "WHERE v.prospect_id=? ORDER BY v.id DESC", (bid,)).fetchall()
    for row in rows or []:
        try:
            res = json.loads(row['result_json'])
        except (ValueError, TypeError):
            continue
        if res.get('confidence_label') == 'VERIFIED_HIGH':
            return True, {'email': row['email'], 'confidence': 'VERIFIED_HIGH'}
    return False, {'checked': len(rows or [])}


def _gate_consent(d, bid):
    """UEMA consent gate: requires a recorded human-ratified basis."""
    r = d.execute("SELECT permission_basis,permission_verified_by FROM "
                  "mm_contact_evidence WHERE business_id=? ORDER BY id DESC LIMIT 1",
                  (bid,)).fetchone()
    ok = bool(r and r['permission_verified_by'])
    return ok, {'basis': r['permission_basis'] if r else None,
                'ratified_by': r['permission_verified_by'] if r else None}


def _gate_suppression(d, bid):
    for row in d.execute("SELECT recipient FROM mm_contact_evidence WHERE business_id=?",
                         (bid,)).fetchall():
        if d.execute("SELECT 1 FROM mm_suppression WHERE address=?",
                     (row['recipient'].strip().lower(),)).fetchone():
            return False, {'suppressed': row['recipient']}
    return True, {}


def _gate_duplicate_send(d, bid):
    r = d.execute("SELECT count(*) n FROM outreach_send_ledger WHERE business_id=? "
                  "AND status IN ('planned','sent')", (bid,)).fetchone()
    return (r['n'] == 0), {'existing_sends': r['n'] if r else 0}


def _gate_content_qa(d, bid):
    r = d.execute("SELECT id,body FROM mm_messages WHERE business_id=? "
                  "AND invalidated_reason IS NULL ORDER BY id DESC LIMIT 1", (bid,)).fetchone()
    if not r:
        return False, {'reason': 'no valid message draft'}
    if contains_secret(r['body']):
        return False, {'reason': 'draft contains secret-like material'}
    return True, {'message_id': r['id']}


GATES = (
    ('identity_resolved', _gate_identity),
    ('pipeline_state_valid', _gate_pipeline_state),
    ('audit_evidence_present', _gate_audit_evidence),
    ('email_verified_high', _gate_verified_email),
    ('consent_ratified', _gate_consent),
    ('not_suppressed', _gate_suppression),
    ('no_duplicate_send', _gate_duplicate_send),
    ('content_qa', _gate_content_qa),
)


def evaluate(d, bid):
    """Run every gate; return machine-readable results. Read-only."""
    results = {}
    passed = True
    for name, fn in GATES:
        try:
            ok, evidence = fn(d, bid)
        except Exception as ex:  # a gate that cannot run never passes
            ok, evidence = False, {'gate_error': '%s: %s' % (type(ex).__name__, ex)}
        results[name] = {'passed': bool(ok), 'evidence': evidence}
        passed = passed and ok
    return {'business_id': bid, 'all_passed': passed, 'gates': results,
            'evaluated_at': now()}


# ---------------------------------------------------------------------------
# Approval decision — PENDING -> CHECKING -> APPROVED/REJECTED/NEEDS_REVIEW
# ---------------------------------------------------------------------------

def request_approval(d, bid):
    migrate(d)
    cur = d.execute("INSERT INTO approval_records(business_id,status,created_at) "
                    "VALUES(?,'PENDING',?)", (bid, now()))
    return cur.lastrowid


def decide(d, approval_id, actor, reason, reviewable=True):
    """Evaluate gates and record a decision. APPROVED only if all pass."""
    migrate(d)
    r = d.execute("SELECT * FROM approval_records WHERE id=?", (approval_id,)).fetchone()
    if not r or r['status'] not in ('PENDING', 'NEEDS_REVIEW'):
        raise ValueError('Approval %s not decidable from status %s'
                         % (approval_id, r['status'] if r else 'MISSING'))
    d.execute("UPDATE approval_records SET status='CHECKING' WHERE id=?", (approval_id,))
    ev = evaluate(d, r['business_id'])
    if ev['all_passed']:
        status = 'APPROVED'
        content = d.execute("SELECT recipient,body FROM mm_messages WHERE business_id=? "
                            "AND invalidated_reason IS NULL ORDER BY id DESC LIMIT 1",
                            (r['business_id'],)).fetchone()
        chash = digest(content['recipient'], content['body']) if content else None
    else:
        missing = {k for k, v in ev['gates'].items() if not v['passed']}
        # Hard compliance failures reject; missing evidence routes to review.
        status = 'REJECTED' if (missing & {'not_suppressed', 'no_duplicate_send'}) \
            else ('NEEDS_REVIEW' if reviewable else 'REJECTED')
        chash = None
    d.execute("UPDATE approval_records SET status=?,gates_json=?,reason=?,actor=?,"
              "content_hash=?,decided_at=? WHERE id=?",
              (status, json.dumps(ev), reason, actor, chash, now(), approval_id))
    log({'kind': 'approval_decision', 'approval_id': approval_id,
         'business_id': r['business_id'], 'status': status, 'actor': actor})
    return {'approval_id': approval_id, 'status': status, 'gates': ev['gates']}


# ---------------------------------------------------------------------------
# Send ledger: idempotency, rate limits, bounce quarantine
# ---------------------------------------------------------------------------

def idempotency_key(business_id, recipient, body, campaign):
    from mm_core import sha
    return sha('|'.join([str(business_id), recipient.strip().lower(),
                         digest(recipient, body), campaign]))


def quarantine_check(d):
    """Stop sending automatically on abnormal bounce signals."""
    rows = d.execute("SELECT status,count(*) n FROM outreach_send_ledger "
                     "GROUP BY status").fetchall()
    counts = {r['status']: r['n'] for r in rows}
    total = counts.get('sent', 0) + counts.get('bounced', 0)
    if total >= BOUNCE_QUARANTINE_MIN and \
            counts.get('bounced', 0) / total > BOUNCE_QUARANTINE_RATE:
        log({'kind': 'quarantine', 'reason': 'bounce_rate', 'counts': counts})
        return {'quarantined': True, 'reason': 'bounce_rate', 'counts': counts}
    return {'quarantined': False, 'counts': counts}


def plan_send(d, bid, recipient, body, campaign, transport='gmail'):
    """Create the auditable send record. Idempotent; fails closed.

    Returns the ledger row. Raises ValueError with reasons when blocked.
    """
    migrate(d)
    if quarantine_check(d)['quarantined']:
        raise ValueError('QUARANTINED: abnormal bounce signals; sending halted')
    if not rate_ok(d, 'outreach_send', DAILY_SEND_CAP, 86400):
        raise ValueError('RATE_LIMITED: daily send cap reached')
    appr = d.execute("SELECT * FROM approval_records WHERE business_id=? AND "
                     "status='APPROVED' ORDER BY id DESC LIMIT 1", (bid,)).fetchone()
    if not appr:
        raise ValueError('NO_APPROVAL: an APPROVED approval record is required')
    chash = digest(recipient, body)
    if appr['content_hash'] != chash:
        raise ValueError('CONTENT_MISMATCH: approved content hash differs')
    key = idempotency_key(bid, recipient, body, campaign)
    existing = d.execute("SELECT * FROM outreach_send_ledger WHERE idempotency_key=?",
                         (key,)).fetchone()
    if existing:
        return dict(existing)  # idempotent replay: no duplicate send
    d.execute("INSERT INTO outreach_send_ledger(idempotency_key,business_id,"
              "recipient,content_hash,campaign,approval_id,transport,status,"
              "created_at,updated_at) VALUES(?,?,?,?,?,?,?,'planned',?,?)",
              (key, bid, recipient.strip().lower(), chash, campaign,
               appr['id'], transport, now(), now()))
    log({'kind': 'send_planned', 'business_id': bid, 'campaign': campaign,
         'approval_id': appr['id'], 'idempotency_key': key[:16]})
    return dict(d.execute("SELECT * FROM outreach_send_ledger WHERE idempotency_key=?",
                          (key,)).fetchone())


def record_result(d, key, status, provider_message_id=None, bounce=None):
    """Record the transport outcome. Terminal statuses cannot regress."""
    r = d.execute("SELECT * FROM outreach_send_ledger WHERE idempotency_key=?",
                  (key,)).fetchone()
    if not r:
        raise ValueError('Unknown idempotency key')
    if r['status'] in ('sent', 'bounced') and status in ('planned', 'failed'):
        raise ValueError('Terminal send status cannot regress')
    retry = r['retry_count'] + (1 if status == 'failed' else 0)
    d.execute("UPDATE outreach_send_ledger SET status=?,retry_count=?,"
              "provider_message_id=coalesce(?,provider_message_id),"
              "sent_at=CASE WHEN ?='sent' THEN ? ELSE sent_at END,"
              "bounce=coalesce(?,bounce),updated_at=? WHERE idempotency_key=?",
              (status, retry, provider_message_id, status, now(),
               json.dumps(bounce) if bounce else None, now(), key))
    log({'kind': 'send_result', 'key': key[:16], 'status': status,
         'retry_count': retry})
    return dict(d.execute("SELECT * FROM outreach_send_ledger WHERE idempotency_key=?",
                          (key,)).fetchone())
