"""Read-only outreach review checks. Never generates, approves or sends email."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from outreach.consent_gate import check as consent_check
from scripts.cloud_prospect_pipeline import policy_rows

MAX_CONTACT_AGE_SECONDS = 30 * 24 * 3600  # Operational evidence freshness, not a legal threshold.


def host(value):
    return str(value or "").lower().removeprefix("www.").rstrip(".")


def _contact_blockers(contact, domain, now):
    reasons = []
    address = contact.get("address", "")
    if (
        not isinstance(address, str)
        or not re.fullmatch(r"[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+", address)
        or len(address) > 254
    ):
        reasons.append("recipient_invalid")
    if contact.get("address_verified") is not True:
        reasons.append("recipient_not_directly_verified")
    if contact.get("address_provenance") != "own_website":
        reasons.append("recipient_source_not_own_website")
    parts = urlsplit(str(contact.get("address_source_url", "")))
    if (
        parts.scheme != "https"
        or host(parts.hostname) != host(domain)
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        reasons.append("recipient_source_mismatch")
    observed = contact.get("address_verified_at")
    try:
        date = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        age = now - date.timestamp()
        if date.tzinfo is None or age < -300 or age > MAX_CONTACT_AGE_SECONDS:
            raise ValueError("Fresh source required")
    except (TypeError, ValueError, AttributeError):
        reasons.append("recipient_verification_stale_or_missing")
    # Never turn a statement that an address was guessed into verified evidence.
    provenance_text = " ".join(
        str(contact.get(k, "")) for k in ("address_found_where", "why_consent_believed")
    ).lower()
    if any(
        marker in provenance_text
        for marker in (
            "email inferred",
            "not directly confirmed",
            "not directly verified",
            "domain-pattern",
            "email not directly",
        )
    ):
        reasons.append("recipient_provenance_contradicts_verification")
    decision, _, _ = consent_check(contact)
    if decision != "PERMITTED":
        reasons.append("consent_gate_blocked")
    return reasons


def review(prospect, contact, sender, *, now, message=None, approved_sha256=None):
    reasons = []
    if prospect.get("suppressed") is True:
        reasons.append("target_suppressed")
    if prospect.get("active") is not True:
        reasons.append("target_not_active")
    reasons.extend(_contact_blockers(contact, prospect.get("domain"), now))
    findings = prospect.get("findings", [])
    verified = {
        x.get("finding_id")
        for x in findings
        if x.get("confidence") == "observed"
        and x.get("evidence_check_status") == "ok"
        and x.get("independently_verified") is True
        and x.get("source_url")
    }
    claimed = contact.get("verified_finding_ids")
    if (
        not isinstance(claimed, list)
        or not claimed
        or any(not isinstance(x, str) for x in claimed)
        or not set(claimed).issubset(verified)
    ):
        reasons.append("claims_not_bound_to_current_verified_findings")
    if not all(sender.get(k) for k in ("name", "email", "contact_details")):
        reasons.append("sender_identity_incomplete")
    if sender.get("unsubscribe_verified") is not True:
        reasons.append("unsubscribe_unverified")
    if not isinstance(message, str) or not message.strip():
        reasons.append("exact_message_missing")
    elif (
        not isinstance(approved_sha256, str)
        or hashlib.sha256(message.encode()).hexdigest() != approved_sha256
    ):
        reasons.append("exact_message_approval_missing")
    return {
        "candidate_review_ready": not reasons,
        "blockers": sorted(set(reasons)),
        "send_enabled": False,
        "provider": "none",
        "network_calls": 0,
        "mode": "READ_ONLY_PREFLIGHT",
    }


def legacy_review(repo):
    source = repo / "outreach" / "CONSENT_EVIDENCE_TASK001.json"
    records = json.loads(source.read_text())
    if not isinstance(records, list) or len(records) > 100:
        raise ValueError("Invalid legacy evidence list")
    current = {host(row["domain"]): row for row in policy_rows(repo)}
    checks = []
    now = int(datetime.now(timezone.utc).timestamp())
    for contact in records:
        domain = host(urlsplit(str(contact.get("address_source_url", ""))).hostname)
        row = current.get(domain, {})
        checks.append(
            review(
                {
                    "domain": domain,
                    "active": bool(row) and not row.get("suppressed"),
                    "suppressed": row.get("suppressed", False),
                    "findings": [],
                },
                contact,
                {},
                now=now,
            )
        )
    # Only aggregate codes; addresses, personal data and drafts do not enter logs.
    return {
        "legacy_records": len(checks),
        "candidate_review_ready": sum(x["candidate_review_ready"] for x in checks),
        "blocked": sum(not x["candidate_review_ready"] for x in checks),
        "blocker_codes": sorted({code for x in checks for code in x["blockers"]}),
        "send_enabled": False,
        "network_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-review", action="store_true", required=True)
    parser.parse_args()
    try:
        print(
            json.dumps(legacy_review(Path(__file__).resolve().parents[1]), indent=2, sort_keys=True)
        )
        return 0  # Produces a review report, never releases transport.
    except Exception:
        print("Outreach preflight blocked; review configuration privately.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
