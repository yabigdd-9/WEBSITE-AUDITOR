#!/usr/bin/env python3
"""
HERMES_ZERO_TOKEN Outreach Draft Worker (P2)

Produces HUMAN-REVIEW-ONLY outreach drafts. NEVER sends anything.
Drafts are written to state/hermes_zero_token/outreach_drafts/*.md and
APPROVAL_QUEUE.yaml is updated with review items.

Safety: no email, no SMS, no messaging DMs, no form submissions.
All outreach remains in the human-review queue.
"""

import fcntl
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.chdir(PROJECT_ROOT)

DRAFTS_DIR = PROJECT_ROOT / "state" / "hermes_zero_token" / "outreach_drafts"
APPROVAL_QUEUE_PATH = PROJECT_ROOT / "state" / "hermes_zero_token" / "APPROVAL_QUEUE.yaml"
LEGACY_APPROVAL_QUEUE_PATH = PROJECT_ROOT / "approval" / "APPROVAL_QUEUE.yaml"

os.environ["HERMES_ZERO_TOKEN_MODE"] = "ZERO_LLM"
os.environ["HERMES_ALLOW_HOSTED_LLM"] = "0"
os.environ["HERMES_ALLOW_PAID_FALLBACK"] = "0"
os.environ["WEBSITE_AUDITOR_OUTREACH_SEND"] = "0"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _now_tag():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def get_businesses_with_evidence(limit=5):
    """Return businesses with evidence rows, sorted by evidence recency."""
    conn = __import__("sqlite3").connect(
        f"file:{PROJECT_ROOT / 'database' / 'money_machine.db'}?mode=ro", uri=True
    )
    conn.row_factory = __import__("sqlite3").Row
    rows = conn.execute(
        "SELECT b.id AS business_id, b.name, b.public_website, b.region, b.source, "
        "       e.id AS evidence_id, e.url AS evidence_url, "
        "       e.observation, e.limitation, e.checked_at, "
        "       m.status AS evidence_status, m.confidence "
        "FROM businesses b "
        "JOIN mm_evidence e ON e.business_id = b.id "
        "LEFT JOIN mm_evidence_meta m ON m.evidence_id = e.id "
        "WHERE b.is_dummy = 0 AND b.public_website IS NOT NULL AND b.public_website != '' "
        "ORDER BY e.checked_at DESC, b.id "
        "LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def draft_body(biz):
    """Build a review-only outreach draft from evidence."""
    name = biz.get("name") or "there"
    url = biz.get("public_website") or ""
    obs = (biz.get("observation") or "").strip()
    lim = (biz.get("limitation") or "").strip()
    ev_url = biz.get("evidence_url") or url

    body = (
        f"Subject: Quick question about {name}'s website\n\n"
        f"Hi {name} team,\n\n"
        f"I was reviewing {url} and noticed: {obs[:200]}\n\n"
        f"This is a draft for human review only. No message has been sent.\n\n"
        f"Evidence: {ev_url}\n"
        f"Limitation: {lim[:200]}\n\n"
        f"Dion\n"
    )
    return body


def load_review_queue():
    """Read runtime state first; import a legacy queue without modifying it."""
    path = APPROVAL_QUEUE_PATH if APPROVAL_QUEUE_PATH.exists() else LEGACY_APPROVAL_QUEUE_PATH
    try:
        queue = yaml.safe_load(path.read_text()) if path.exists() else {}
    except yaml.YAMLError:
        raise ValueError('Review queue contains invalid YAML; preserve it for review') from None
    if queue is None:
        queue = {}
    if not isinstance(queue, dict) or not isinstance(queue.get('requires_dion_approval', []), list):
        raise ValueError('Review queue must be a mapping with an approval item list')
    items = queue.get('requires_dion_approval', [])
    if not all(isinstance(item, dict) and isinstance(item.get('id'), str) for item in items):
        raise ValueError('Review items must have explicit string identities; preserve queue for review')
    queue.setdefault('requires_dion_approval', [])
    queue.setdefault('policy', 'Nothing in this queue has been sent, published, purchased or committed.')
    return queue


def save_review_queue(queue):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=APPROVAL_QUEUE_PATH.parent,
                                         prefix='.approval-', delete=False) as stream:
            temporary = Path(stream.name)
            yaml.safe_dump(queue, stream, sort_keys=False, default_flow_style=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, APPROVAL_QUEUE_PATH)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    APPROVAL_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Serialize read/append/publish so concurrent workers cannot lose review items.
    with (APPROVAL_QUEUE_PATH.parent / 'approval-queue.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return main_locked()


def main_locked():
    queue = load_review_queue()
    businesses = get_businesses_with_evidence(limit=5)
    report = {
        "generated_at": _now(),
        "phase": "P2",
        "drafts_dir": str(DRAFTS_DIR),
        "production_written": False,
        "outbound_messages_sent": 0,  # ALWAYS ZERO
        "drafts_created": 0,
        "existing_reviews_preserved": 0,
        "details": [],
    }

    existing = {item['id'] for item in queue['requires_dion_approval']}
    for biz in businesses:
        bid, evidence_id = biz['business_id'], biz['evidence_id']
        if type(bid) is not int or bid < 1 or type(evidence_id) is not int or evidence_id < 1:
            raise ValueError('Draft requires positive integer business and evidence identities')
        approval_id = f'APR-ZT-{bid}'
        # Any existing request preserves its current decision and draft reference.
        # Refreshing a draft or reopening a rejection requires a separate review.
        if approval_id in existing:
            report['existing_reviews_preserved'] += 1
            continue
        body = draft_body(biz)
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        path = DRAFTS_DIR / f'business-{bid}-evidence-{evidence_id}-{digest}.md'
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.read_bytes() != body.encode('utf-8'):
                raise ValueError('Existing draft does not match expected content; preserve it for review') from None
        else:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            report['drafts_created'] += 1
        existing.add(approval_id)
        report["details"].append({
            "business_id": bid,
            "name": biz["name"],
            "url": biz["public_website"],
            "evidence_id": biz["evidence_id"],
            "draft_path": str(path),
            "status": "DRAFT_ONLY_NOT_SENT",
        })

    # Update APPROVAL_QUEUE.yaml (append-only review items, never send)
    if report['details']:
        queue['generated_at'] = _now()
    queue["requires_dion_approval"] += [
        {
            "id": f"APR-ZT-{d['business_id']}",
            "type": "cold_outreach_send",
            "engine": "Website Auditor Zero-Token",
            "description": f"Send review-only outreach draft to {d['name']}",
            "draft_path": d["draft_path"],
            "blocked_until": "Dion approval required",
            "status": "NOT_SENT_AWAITING_APPROVAL",
        }
        for d in report["details"]
    ]
    if report['details']:
        save_review_queue(queue)

    report["approval_queue_path"] = str(APPROVAL_QUEUE_PATH)
    report_path = DRAFTS_DIR / "outreach_draft_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
