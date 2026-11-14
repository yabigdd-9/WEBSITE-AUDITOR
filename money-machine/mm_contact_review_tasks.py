"""Pure, bounded scheduling decisions for automatic evidence and local drafts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

VERSION = "contact-review-task-v2"
BACKOFF_SECONDS = (60, 300, 1800)
ACCESS_ERRORS = ("ACCESS_RESTRICTED", "ROBOTS_UNAVAILABLE", "ROBOTS_DENIED")


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def schedule(latest, fingerprint, at=None, refresh_hours=24):
    """A completed held review is fresh; failed execution has separate backoff."""
    at = at or datetime.now(timezone.utc)
    latest = latest or {}
    reviewed = timestamp(latest.get("reviewed_at"))
    if latest.get("fingerprint") != fingerprint or reviewed is None or reviewed > at:
        return {"due": True, "due_at": at.isoformat(), "reason": "EVIDENCE_CHANGED", "attempts": 0}
    attempts = max(0, int(latest.get("retry_attempts", 0)))
    status = latest.get("status", "COMPLETE")
    errors = json.dumps(latest.get("row", {}).get("scout", {}).get("acquisition_errors", []))
    errors += str(latest.get("error", ""))
    access = any(code in errors for code in ACCESS_ERRORS)
    transient = status in {"REVIEW_ERROR", "INCOMPLETE", "TIMEOUT", "SCHEDULED"}
    # Partial collection errors deserve a bounded retry even if evaluation ran.
    transient |= status == "COMPLETE" and bool(latest.get("retryable_acquisition_error"))
    if access or not transient or attempts >= len(BACKOFF_SECONDS):
        due_at = reviewed + timedelta(hours=refresh_hours)
        reason = "ACCESS_HOLD" if access else "RETRY_EXHAUSTED" if transient else "FRESH_REVIEW"
    else:
        due_at = reviewed + timedelta(seconds=BACKOFF_SECONDS[attempts])
        reason = "TRANSIENT_RETRY"
    return {"due": at >= due_at, "due_at": due_at.isoformat(), "reason": reason,
            "attempts": attempts if at < due_at or reason == "TRANSIENT_RETRY" else 0}


def task_for(result):
    row = result.get("row") or {}
    judge = row.get("judge") or {}
    proof = row.get("proofer") or {}
    route = judge.get("route") or result.get("status", "INCOMPLETE")
    supported = result.get("status") == "COMPLETE" and route == "MACHINE_SUPPORTED_RECOMMENDATION"
    worker = "DRAFT_PREPARATION" if supported else judge.get("next_worker", "SCOUT")
    checks = [name for name, passed in proof.get("checks", {}).items() if passed is not True]
    evidence_key = key({"fingerprint": result.get("fingerprint"), "row": row})
    return {"version": VERSION, "business_id": result["live_business_id"],
            "evidence_fingerprint": evidence_key, "business_fingerprint": result.get("fingerprint"),
            "required_worker": worker, "permitted_action": "BUILD_LOCAL_DRAFT" if supported else
            "REVIEW_ALLOWED_PUBLIC_EVIDENCE", "blocking_checks": checks,
            "required_evidence": judge.get("required_evidence", checks),
            "reason_code": route, "attempts": result.get("retry_attempts", 0),
            "next_retry": result.get("next_retry_at"),
            "status": "PENDING" if supported else "RETRY_WAIT" if result.get("retryable_acquisition_error") else "HELD",
            "authority": "DRAFT_ONLY", "external_sends": 0, "model_calls": 0}
