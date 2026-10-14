#!/usr/bin/env python3
"""
HERMES_ZERO_TOKEN Outreach Draft Worker (P2)

Produces HUMAN-REVIEW-ONLY outreach drafts. NEVER sends anything.
Drafts are written to reports/hermes_zero_token/outreach_drafts/*.md and
APPROVAL_QUEUE.yaml is updated with review items.

Safety: no email, no SMS, no messaging DMs, no form submissions.
All outreach remains in the human-review queue.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.chdir(PROJECT_ROOT)

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


def main():
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
        tag = _now_tag()
        path = DRAFTS_DIR / f"business-{bid}-{tag}.md"
        body = draft_body(biz)
        path.write_text(body)
        report["drafts_created"] += 1
        report["details"].append({
            "business_id": bid,
            "name": biz["name"],
            "url": biz["public_website"],
            "evidence_id": biz["evidence_id"],
            "draft_path": str(path),
            "status": "DRAFT_ONLY_NOT_SENT",
        })

    # Update APPROVAL_QUEUE.yaml (append-only review items, never send)
    queue = {"generated_at": _now(), "policy": "Nothing in this queue has been sent, published, purchased or committed.", "items": []}
    if APPROVAL_QUEUE_PATH.exists():
        try:
            existing = yaml.safe_load(APPROVAL_QUEUE_PATH.read_text()) or {}
            queue["existing_items"] = existing.get("requires_dion_approval", [])
        except yaml.YAMLError:
            pass
    queue["requires_dion_approval"] = queue.get("existing_items", []) + [
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
    APPROVAL_QUEUE_PATH.write_text(yaml.safe_dump(queue, sort_keys=False, default_flow_style=False))

    report["approval_queue_path"] = str(APPROVAL_QUEUE_PATH)
    report_path = DRAFTS_DIR / "outreach_draft_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
