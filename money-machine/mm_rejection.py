"""P2: terminal rejection intelligence.

Every terminal rejection is recorded with its raw reason preserved verbatim and
a canonical_reason assigned by the classification layer. original decision rows
are never mutated by this module; it only appends to the terminal_rejections
table. The module also connects experience_ledger outcomes to prior decisions
so downstream mining can correlate rejections with the evidence stage that led
to them.

Gates:
  * raw_reason is stored exactly as supplied; canonical_reason is a separate,
    normalized label chosen from a fixed vocabulary.
  * source_query_stage names the pipeline stage that produced the terminal.
  * evidence_refs is a JSON list of evidence row ids the rejection was based on.
  * No automated threshold change or challenger promotion happens here.
"""
import json
import sqlite3
from pathlib import Path

from mm_core import now, sha

# Fixed canonical-reason vocabulary. New labels are added here by a human;
# the pipeline never invents new canonical reasons at runtime.
CANONICAL_REASONS = frozenset([
    'DUPLICATE_BUSINESS',
    'NO_VERIFIED_EMAIL',
    'SUPPRESSED_RECIPIENT',
    'INSUFFICIENT_EVIDENCE',
    'IDENTITY_NOT_RESOLVED',
    'AUDIT_REJECTED',
    'QUALIFICATION_FAILED',
    'OUTREACH_NOT_APPROVED',
    'CONTACT_NOT_VERIFIED',
    'PERMANENT_FAILURE',
    'BLOCKED_COST',
    'UNKNOWN_ROUTE_TO_REVIEW',
])

# canonical_reason labels that always route to human review in the CLI report.
REVIEW_ROUTE_LABELS = frozenset([
    'UNKNOWN_ROUTE_TO_REVIEW',
    'PERMANENT_FAILURE',
    'BLOCKED_COST',
    'INSUFFICIENT_EVIDENCE',
])


def migrate(d):
    """Idempotent; safe to call on every invocation."""
    d.executescript("""
CREATE TABLE IF NOT EXISTS terminal_rejections(
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  terminal_state TEXT NOT NULL,
  raw_reason TEXT NOT NULL,
  canonical_reason TEXT NOT NULL,
  source_query_stage TEXT NOT NULL,
  evidence_refs TEXT NOT NULL DEFAULT '[]',
  recorded_at TEXT NOT NULL,
  actor TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS terminal_rejections_business
  ON terminal_rejections(business_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS terminal_rejections_canonical
  ON terminal_rejections(canonical_reason, recorded_at DESC);
CREATE INDEX IF NOT EXISTS terminal_rejections_state
  ON terminal_rejections(terminal_state, recorded_at DESC);
CREATE TRIGGER IF NOT EXISTS terminal_rejections_no_update
BEFORE UPDATE ON terminal_rejections BEGIN
  SELECT RAISE(ABORT,'terminal rejections are append-only');
END;
CREATE TRIGGER IF NOT EXISTS terminal_rejections_no_delete
BEFORE DELETE ON terminal_rejections BEGIN
  SELECT RAISE(ABORT,'terminal rejections are append-only');
END;
""" + _P3_SCHEMA + _P3_TRIGGERS)


def classify_canonical(state, raw_reason):
    """Map a terminal state + raw reason string to a canonical_reason label.

    Unknown combinations are preserved under UNKNOWN_ROUTE_TO_REVIEW so the
    report surfaces them for human review rather than silently dropping them.
    """
    raw = (raw_reason or '').strip().lower()
    if state == 'DUPLICATE':
        return 'DUPLICATE_BUSINESS'
    if state == 'NO_VERIFIED_EMAIL':
        return 'NO_VERIFIED_EMAIL'
    if state == 'SUPPRESSED':
        return 'SUPPRESSED_RECIPIENT'
    if state == 'REJECTED':
        if 'duplicate' in raw:
            return 'DUPLICATE_BUSINESS'
        if 'suppress' in raw or 'suppressed' in raw:
            return 'SUPPRESSED_RECIPIENT'
        if 'evidence' in raw or 'verified' in raw:
            return 'INSUFFICIENT_EVIDENCE'
        return 'OUTREACH_NOT_APPROVED'
    if state == 'PERMANENT_FAILURE':
        return 'PERMANENT_FAILURE'
    if state == 'RETRYABLE_FAILURE':
        # Not terminal in the v44 state machine; classified here for completeness
        # when observed as a terminal-like dead-letter in integration paths.
        if 'blocked_cost' in raw or 'blocked cost' in raw:
            return 'BLOCKED_COST'
        return 'INSUFFICIENT_EVIDENCE'
    if state in ('NEEDS_REVIEW',):
        return 'UNKNOWN_ROUTE_TO_REVIEW'
    # Unknown terminal state: preserve, flag for review.
    return 'UNKNOWN_ROUTE_TO_REVIEW'


def record(d, business_id, terminal_state, raw_reason, source_query_stage,
           evidence_refs=None, actor='system'):
    """Record one terminal rejection. Does NOT mutate any existing row.

    Returns the inserted row id.
    """
    import mm_experience_ledger
    mm_experience_ledger.migrate(d)
    canonical = classify_canonical(terminal_state, raw_reason)
    ev_refs = json.dumps(evidence_refs or [])
    row = d.execute("""INSERT INTO terminal_rejections
        (business_id, terminal_state, raw_reason, canonical_reason,
         source_query_stage, evidence_refs, recorded_at, actor)
        VALUES (?,?,?,?,?,?,?,?)""",
        (business_id, terminal_state, raw_reason, canonical,
         source_query_stage, ev_refs, now(), actor)).lastrowid
    d.execute("""INSERT INTO experience_ledger
        (outcome, actor, observed_at, business_id, evidence_hash, created_at)
        VALUES (?,?,?,?,?,?)""",
        ('terminal_rejection:' + terminal_state, actor, now(),
         business_id, sha((terminal_state + raw_reason).encode()), now()))
    return row


def by_business(d, business_id):
    return [dict(r) for r in d.execute(
        "SELECT * FROM terminal_rejections WHERE business_id=? "
        "ORDER BY recorded_at DESC", (business_id,)).fetchall()]


def recent(d, limit=50):
    return [dict(r) for r in d.execute(
        "SELECT * FROM terminal_rejections ORDER BY recorded_at DESC LIMIT ?",
        (limit,)).fetchall()]


def canonical_counts(d):
    rows = d.execute(
        "SELECT canonical_reason, count(*) n FROM terminal_rejections "
        "GROUP BY canonical_reason ORDER BY n DESC").fetchall()
    return {r['canonical_reason']: r['n'] for r in rows}


def review_route_rows(d):
    """Rows whose canonical_reason is in the REVIEW_ROUTE_LABELS set."""
    if not REVIEW_ROUTE_LABELS:
        return []
    marks = ','.join('?' * len(REVIEW_ROUTE_LABELS))
    return [dict(r) for r in d.execute(
        "SELECT * FROM terminal_rejections WHERE canonical_reason IN (%s) "
        "ORDER BY recorded_at DESC" % marks,
        tuple(REVIEW_ROUTE_LABELS)).fetchall()]


_P3_SCHEMA = """
CREATE TABLE IF NOT EXISTS error_clusters(
  id INTEGER PRIMARY KEY,
  canonical_reason TEXT NOT NULL,
  terminal_state TEXT NOT NULL,
  source_query_stage TEXT NOT NULL,
  cluster_key TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  observed_count INTEGER NOT NULL DEFAULT 1,
  false_positive INTEGER NOT NULL DEFAULT 0,
  false_negative INTEGER NOT NULL DEFAULT 0,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  latest_business_id INTEGER REFERENCES businesses(id),
  latest_raw_reason TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS error_clusters_cluster_key
  ON error_clusters(cluster_key);
CREATE INDEX IF NOT EXISTS error_clusters_fingerprint
  ON error_clusters(fingerprint);
CREATE INDEX IF NOT EXISTS error_clusters_state_reason
  ON error_clusters(terminal_state, canonical_reason);
CREATE TRIGGER IF NOT EXISTS error_clusters_no_delete
BEFORE DELETE ON error_clusters BEGIN
  SELECT RAISE(ABORT,'error clusters are append-only');
END;

CREATE TABLE IF NOT EXISTS human_corrections(
  id INTEGER PRIMARY KEY,
  rejection_id INTEGER NOT NULL REFERENCES terminal_rejections(id),
  corrected_label TEXT NOT NULL,
  correction_note TEXT NOT NULL DEFAULT '',
  corrected_by TEXT NOT NULL,
  corrected_at TEXT NOT NULL,
  created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS human_corrections_rejection
  ON human_corrections(rejection_id);
CREATE INDEX IF NOT EXISTS human_corrections_label
  ON human_corrections(corrected_label, corrected_at DESC);
CREATE TRIGGER IF NOT EXISTS human_corrections_no_update
BEFORE UPDATE ON human_corrections BEGIN
  SELECT RAISE(ABORT,'human corrections are append-only');
END;
CREATE TRIGGER IF NOT EXISTS human_corrections_no_delete
BEFORE DELETE ON human_corrections BEGIN
  SELECT RAISE(ABORT,'human corrections are append-only');
END;
"""

_P3_TRIGGERS = ""


# ---------------------------------------------------------------------------
# P3: error mining — FP/FN detection, deduplication, clustering
# ---------------------------------------------------------------------------

def cluster_key(canonical_reason, terminal_state, source_query_stage):
    """Deterministic cluster key for error clustering."""
    return sha(
        '|'.join([canonical_reason, terminal_state, source_query_stage])
    )


def fingerprint_for(raw_reason, canonical_reason, terminal_state):
    """Stable fingerprint per raw_reason text (normalized)."""
    return sha(
        '|'.join([raw_reason.strip().lower(), canonical_reason, terminal_state])
    )


def upsert_cluster(d, canonical_reason, terminal_state, source_query_stage,
                   raw_reason, business_id=None):
    """Create or increment an error cluster. Returns the cluster row dict."""
    key = cluster_key(canonical_reason, terminal_state, source_query_stage)
    fp = fingerprint_for(raw_reason, canonical_reason, terminal_state)
    now_time = now()
    existing = d.execute(
        "SELECT * FROM error_clusters WHERE fingerprint=?",
        (fp,)).fetchone()
    if existing:
        d.execute("""UPDATE error_clusters SET observed_count=observed_count+1,
            last_seen=?, latest_business_id=?, latest_raw_reason=?,
            updated_at=? WHERE id=?""",
            (now_time, business_id, raw_reason, now_time, existing['id']))
        return dict(d.execute(
            "SELECT * FROM error_clusters WHERE id=?", (existing['id'],)).fetchone())
    return dict(d.execute("""INSERT INTO error_clusters
        (canonical_reason, terminal_state, source_query_stage, cluster_key,
         fingerprint, first_seen, last_seen, latest_business_id,
         latest_raw_reason, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (canonical_reason, terminal_state, source_query_stage, key, fp,
         now_time, now_time, business_id, raw_reason, now_time, now_time)).lastrowid
    and d.execute("SELECT * FROM error_clusters WHERE id=last_insert_rowid()").fetchone())


def detect_false_positive(d, rejection_id, corrected_label):
    """Record that a recorded rejection was a false positive per human correction.

    Does NOT mutate the original rejection row; appends a human_corrections row
    and increments the cluster's false_positive counter.
    """
    row = d.execute("SELECT * FROM terminal_rejections WHERE id=?",
                    (rejection_id,)).fetchone()
    if not row:
        raise ValueError('Unknown rejection id: ' + str(rejection_id))
    corr = d.execute("""INSERT INTO human_corrections
        (rejection_id, corrected_label, correction_note, corrected_by,
         corrected_at, created_at)
        VALUES (?,?,?,?,?,?)""",
        (rejection_id, corrected_label, 'false_positive correction',
         'human', now(), now())).lastrowid
    fp = fingerprint_for(row['raw_reason'], row['canonical_reason'],
                         row['terminal_state'])
    upsert_cluster(d, row['canonical_reason'], row['terminal_state'],
                   row['source_query_stage'], row['raw_reason'], row['business_id'])
    d.execute("""UPDATE error_clusters SET false_positive=false_positive+1,
        updated_at=? WHERE fingerprint=?""", (now(), fp))
    return corr


def detect_false_negative(d, business_id, terminal_state, raw_reason,
                          source_query_stage, expected_label):
    """Record that a case should have been caught / flagged (false negative).

    Appends a human_corrections row pointing at the (possibly absent) rejection
    and increments the appropriate cluster's false_negative counter. If no
    rejection was recorded for this case, one is created first.
    """
    rejections = by_business(d, business_id)
    target = None
    for r in rejections:
        if (r['terminal_state'] == terminal_state and
                raw_reason.lower() in r['raw_reason'].lower()):
            target = r['id']
            break
    if target is None:
        # No rejection recorded: this IS the false negative — record it.
        target = record(d, business_id, terminal_state, raw_reason,
                        source_query_stage, actor='system')
    row = d.execute("SELECT * FROM terminal_rejections WHERE id=?", (target,)).fetchone()
    fp = fingerprint_for(row['raw_reason'], row['canonical_reason'], row['terminal_state'])
    upsert_cluster(d, row['canonical_reason'], row['terminal_state'],
                   row['source_query_stage'], row['raw_reason'], row['business_id'])
    d.execute("""INSERT INTO human_corrections
        (rejection_id, corrected_label, correction_note, corrected_by,
         corrected_at, created_at)
        VALUES (?,?,?,?,?,?)""",
        (target, expected_label, 'false_negative correction', 'human', now(), now()))
    d.execute("""UPDATE error_clusters SET false_negative=false_negative+1,
        updated_at=? WHERE fingerprint=?""", (now(), fp))
    return target


def error_summary(d):
    """Aggregate view of error clusters with FP/FN totals."""
    rows = d.execute("""SELECT canonical_reason, terminal_state,
        source_query_stage, sum(observed_count) observed,
        sum(false_positive) fp, sum(false_negative) fn,
        count(*) clusters
        FROM error_clusters GROUP BY canonical_reason, terminal_state,
        source_query_stage ORDER BY observed DESC""").fetchall()
    return [dict(r) for r in rows]


def unclassified_rejections(d):
    """Rows whose canonical_reason is UNKNOWN_ROUTE_TO_REVIEW — routes to human review."""
    return [dict(r) for r in d.execute(
        "SELECT * FROM terminal_rejections WHERE canonical_reason='UNKNOWN_ROUTE_TO_REVIEW' "
        "ORDER BY recorded_at DESC").fetchall()]
