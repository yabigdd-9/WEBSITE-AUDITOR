"""Short supervisor-owned application of hash-bound machine identity proposals."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import mm_email as email
import mm_email_store as email_store


def eligible(d, business_id, recipient=""):
    b = d.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone()
    p = d.execute("SELECT * FROM pipeline_items WHERE business_id=?", (business_id,)).fetchone()
    if not b or not p or b["is_dummy"] or p["state"] not in {"IDENTITY_PENDING", "CONTACT_PENDING", "NEEDS_REVIEW"}:
        return False
    if b["suppression_reason"] or b["current_status"] == "SUPPRESSED" or p["lease_owner"]:
        return False
    return not email_store.is_suppressed(d, business_id, recipient)


def human_name_protected(d, business_id):
    # Prior human corrections remain authoritative; never reinterpret as training.
    for row in d.execute("SELECT action,detail FROM mm_events WHERE business_id=?", (business_id,)):
        action = str(row["action"]).lower()
        if any(term in action for term in ("human", "identity_name", "name_correction", "name_change")):
            return True
        try:
            detail = json.loads(row["detail"] or "{}")
        except (ValueError, TypeError):
            continue
        if isinstance(detail, dict) and any(detail.get(k) for k in ("human_authorized", "human_review", "reviewer")):
            if any(k in detail for k in ("name", "before_name", "after_name", "changed_fields")):
                return True
    return False


def apply_identity(d, business, proposal, job):
    if not proposal or proposal.get("permitted_action") != "APPLY_VALIDATED_IDENTITY_NAME":
        return {"applied": False, "reason": "NO_VALIDATED_PROPOSAL"}
    bid = business["live_business_id"]
    if human_name_protected(d, bid) or not eligible(d, bid):
        return {"applied": False, "reason": "PROTECTED_OR_INELIGIBLE"}
    proposed = proposal.get("business", {})
    if proposal.get("changed_fields") != ["name"] or any(
            proposed.get(k) != value for k, value in business.items() if k != "name"):
        return {"applied": False, "reason": "IDENTITY_SCOPE_CHANGED"}
    row = proposal.get("row", {})
    if row.get("identity", {}).get("status") != "HIGH":
        return {"applied": False, "reason": "IDENTITY_NOT_HIGH"}
    identity = row.get("verifier", {}).get("identity", {})
    if identity.get("status") != "HIGH" or identity.get("reasons") or identity.get("weighted_confidence", {}).get("conflicts"):
        return {"applied": False, "reason": "IDENTITY_CONFLICT"}
    pages = identity.get("page_evidence", [])
    if not pages:
        return {"applied": False, "reason": "IDENTITY_CAPTURE_MISSING"}
    for page in pages:
        capture = Path(page.get("capture_path", ""))
        if not capture.is_file() or hashlib.sha256(capture.read_bytes()).hexdigest() != page.get("capture_hash"):
            return {"applied": False, "reason": "IDENTITY_CAPTURE_CHANGED"}
    name = proposed.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        return {"applied": False, "reason": "INVALID_NAME"}
    existing = d.execute("SELECT name,region,public_website FROM businesses WHERE id=?", (bid,)).fetchone()
    if not existing or any(existing[k] != business[k] for k in ("name", "region", "public_website")):
        return {"applied": False, "reason": "STALE_IDENTITY"}
    cur = d.execute("UPDATE businesses SET name=?,normalized_name=? WHERE id=? AND name=? AND region=? AND public_website=?",
                    (name, email.normalize_name(name), bid, business["name"], business["region"], business["public_website"]))
    if cur.rowcount != 1:
        return {"applied": False, "reason": "STALE_IDENTITY"}
    detail = {"before_name": business["name"], "after_name": name,
              "machine_evidence_only": True, "independent_human_label": None,
              "proposal_sha256": hashlib.sha256(json.dumps(proposal, sort_keys=True).encode()).hexdigest(),
              "job_directory": str(Path(job)), "changed_fields": ["name", "normalized_name"]}
    d.execute("INSERT INTO mm_events(business_id,action,detail,event_at) VALUES(?,?,?,?)",
              (bid, "automatic_identity_resolution", json.dumps(detail, sort_keys=True), datetime.now(timezone.utc).isoformat()))
    return {"applied": True, **detail}
