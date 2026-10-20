#!/usr/bin/env python3
"""
HERMES_ZERO_TOKEN Outreach Draft Worker (P2)

Produces HUMAN-REVIEW-ONLY outreach drafts. NEVER sends anything.
Drafts are written to reports/hermes_zero_token/outreach_drafts/*.md and
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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from ops.hermes_zero_token.worker_ownership import run_owned_worker  # noqa: E402

DRAFTS_DIR = PROJECT_ROOT / "reports" / "hermes_zero_token" / "outreach_drafts"
APPROVAL_QUEUE_PATH = PROJECT_ROOT / "approval" / "APPROVAL_QUEUE.yaml"

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


def _atomic_write(path, content):
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def append_review_items(details):
    if not details:
        return
    APPROVAL_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_path = APPROVAL_QUEUE_PATH.with_suffix(".yaml.lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        if APPROVAL_QUEUE_PATH.exists():
            queue = yaml.safe_load(APPROVAL_QUEUE_PATH.read_text())
        else:
            queue = {"requires_dion_approval": []}
        if not isinstance(queue, dict):
            raise ValueError("Approval queue must be a mapping; existing data preserved")
        items = queue.setdefault("requires_dion_approval", [])
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ValueError("Approval items must be mappings in a list; existing data preserved")
        existing_ids = {item.get("id") for item in items}
        for detail in details:
            item_id = f"APR-ZT-{detail['business_id']}-{detail['draft_sha256']}"
            if item_id in existing_ids:
                continue
            items.append({
                "id": item_id,
                "type": "cold_outreach_send",
                "engine": "Website Auditor Zero-Token",
                "description": f"Review outreach draft for {detail['name']}",
                "draft_path": detail["draft_path"],
                "draft_sha256": detail["draft_sha256"],
                "evidence_id": detail["evidence_id"],
                "blocked_until": "Dion approval of exact sender, recipient and message required",
                "status": "NOT_SENT_AWAITING_APPROVAL",
            })
            existing_ids.add(item_id)
        queue["zero_token_updated_at"] = _now()
        _atomic_write(APPROVAL_QUEUE_PATH, yaml.safe_dump(queue, sort_keys=False))


def _main():
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    businesses = get_businesses_with_evidence(limit=5)
    report = {
        "generated_at": _now(),
        "phase": "P2",
        "drafts_dir": str(DRAFTS_DIR),
        "production_written": False,
        "outbound_messages_sent": 0,  # ALWAYS ZERO
        "drafts_created": 0,
        "details": [],
    }

    for biz in businesses:
        bid = biz["business_id"]
        body = draft_body(biz)
        draft_hash = hashlib.sha256(body.encode()).hexdigest()
        path = DRAFTS_DIR / f"business-{bid}-evidence-{biz['evidence_id']}-{draft_hash}.md"
        _atomic_write(path, body)
        report["drafts_created"] += 1
        report["details"].append({
            "business_id": bid,
            "name": biz["name"],
            "url": biz["public_website"],
            "evidence_id": biz["evidence_id"],
            "draft_path": str(path),
            "draft_sha256": draft_hash,
            "status": "DRAFT_ONLY_NOT_SENT",
        })

    append_review_items(report["details"])

    report["approval_queue_path"] = str(APPROVAL_QUEUE_PATH)
    report_path = DRAFTS_DIR / "outreach_draft_report.json"
    _atomic_write(report_path, json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0


def main():
    return run_owned_worker(PROJECT_ROOT, 'outreach_draft', _main)


if __name__ == "__main__":
    sys.exit(main())
