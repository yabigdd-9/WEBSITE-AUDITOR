"""Version-bound owner decisions and a sandbox-only outreach state machine.

There is no live transport adapter. Proposal approval is not send approval.
Permissions below are owner-attested evidence records, not legal conclusions.
"""

from __future__ import annotations

import hashlib
import re

from scripts.cloud_opportunities import digest

HASH = re.compile(r"[0-9a-f]{64}\Z")
STATES = {"DRAFT", "REVIEW", "APPROVED", "SEND_ELIGIBLE", "SENT", "REJECTED", "BLOCKED", "FAILED", "OPTED_OUT"}


def actor_record(actor, reason, now):
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 100:
        raise ValueError("Authenticated owner identity required")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ValueError("A bounded owner decision reason is required")
    return dict(actor_sha256=hashlib.sha256(actor.encode()).hexdigest(), reason=reason.strip(), timestamp=now)


def current_proposal(prospect, version):
    if not version or prospect.get("proposal_version") != version:
        raise ValueError("Current exact proposal version required")
    proposal = next((p for p in prospect.get("proposal_versions", []) if p["version_sha256"] == version), None)
    if proposal is None or digest({k: v for k, v in proposal.items() if k != "version_sha256"}) != version:
        raise ValueError("Proposal integrity check failed")
    if prospect.get("status") in {"suppressed", "removed"}:
        raise ValueError("Prospect is suppressed")
    return proposal


def append(prospect, key, record):
    records = prospect.setdefault(key, [])
    if len(records) >= 1000:
        raise ValueError("Owner archival required")
    records.append(record)


def approve_proposal(prospect, version, *, actor, reason, now):
    current_proposal(prospect, version)
    record = actor_record(actor, reason, now)
    previous = [a for a in prospect.get("approvals", []) if a["action_type"] == "proposal"]
    if previous and all(previous[-1].get(key) == value for key, value in {
        "decision": "approved", "version_sha256": version,
        "actor_sha256": record["actor_sha256"], "reason": record["reason"],
    }.items()):
        return
    append(prospect, "approvals", dict(
        **record, action_type="proposal", decision="approved", version_sha256=version,
    ))


def prepare_outreach(prospect, *, recipient_hash, body, now):
    version = prospect.get("proposal_version")
    current_proposal(prospect, version)
    if not isinstance(recipient_hash, str) or not HASH.fullmatch(recipient_hash):
        raise ValueError("Hashed verified-recipient reference required")
    if not isinstance(body, str) or not body.strip() or len(body) > 9000:
        raise ValueError("Bounded internal outreach draft required")
    draft = dict(recipient_hash=recipient_hash, body=body, proposal_version=version)
    draft["version_sha256"] = digest(draft)
    previous = next((d for d in prospect.get("outreach_drafts", [])
                     if d["version_sha256"] == draft["version_sha256"]), None)
    if previous is None:
        append(prospect, "outreach_drafts", draft)
        event(prospect, draft["version_sha256"], "DRAFT", now)
    prospect["outreach_version"] = draft["version_sha256"]
    return draft["version_sha256"]


def current_draft(prospect, version):
    if not version or prospect.get("outreach_version") != version:
        raise ValueError("Current exact outreach version required")
    draft = next((d for d in prospect.get("outreach_drafts", []) if d["version_sha256"] == version), None)
    if draft is None or digest({k: v for k, v in draft.items() if k != "version_sha256"}) != version:
        raise ValueError("Outreach integrity check failed")
    current_proposal(prospect, draft["proposal_version"])
    return draft


def stage(prospect, version):
    events = [e for e in prospect.get("outreach_events", []) if e["version_sha256"] == version]
    return events[-1]["status"] if events else None


def event(prospect, version, status, now, **extra):
    if status not in STATES:
        raise ValueError("Unknown outreach state")
    append(prospect, "outreach_events", dict(
        version_sha256=version, status=status, timestamp=now, sandbox_only=True, **extra,
    ))


def review_outreach(prospect, version, *, actor, reason, now):
    current_draft(prospect, version)
    record = actor_record(actor, reason, now)
    if stage(prospect, version) not in {"DRAFT", "BLOCKED", "FAILED", "REJECTED"}:
        raise ValueError("Draft cannot enter review from its current state")
    event(prospect, version, "REVIEW", now, decision_record=record)


def approve_outreach(prospect, version, *, actor, reason, now):
    current_draft(prospect, version)
    record = actor_record(actor, reason, now)
    if stage(prospect, version) != "REVIEW":
        raise ValueError("Review is required before approval")
    append(prospect, "approvals", dict(
        **record, action_type="outreach", decision="approved", version_sha256=version,
    ))
    event(prospect, version, "APPROVED", now)


def eligibility(prospect, version, *, now):
    try:
        draft = current_draft(prospect, version)
    except ValueError:
        return False
    decisions = [a for a in prospect.get("approvals", []) if a["action_type"] == "outreach"]
    if not decisions or decisions[-1]["decision"] != "approved" or decisions[-1]["version_sha256"] != version:
        return False
    permission = prospect.get("contact_permission", {})
    checked = permission.get("checked_at")
    return (
        permission.get("recipient_hash") == draft["recipient_hash"]
        and permission.get("recipient_verified") is True
        and permission.get("consent_verified") is True
        and isinstance(permission.get("consent_evidence_sha256"), str)
        and bool(HASH.fullmatch(permission["consent_evidence_sha256"]))
        and permission.get("sender_identified") is True
        and permission.get("unsubscribe_functional") is True
        and permission.get("opted_out") is False
        and type(checked) in (int, float) and 0 <= now - checked <= 7 * 86400
    )


def mark_send_eligible(prospect, version, *, now):
    if stage(prospect, version) != "APPROVED":
        raise ValueError("Exact outreach approval required")
    if not eligibility(prospect, version, now=now):
        event(prospect, version, "BLOCKED", now, failure_code="eligibility_unverified")
        return False
    event(prospect, version, "SEND_ELIGIBLE", now)
    return True


class SandboxTransport:
    """Deterministic in-memory test transport. No network implementation exists."""

    def __init__(self):
        self.calls = 0

    def send(self, idempotency_key):
        self.calls += 1
        return dict(provider_id="sandbox-" + idempotency_key[:20], external_sends=0, sandbox=True)


def send_sandbox(prospect, version, *, now, transport):
    if type(transport) is not SandboxTransport:
        raise ValueError("Only the built-in sandbox transport is supported")
    draft = current_draft(prospect, version)
    idempotency_key = digest(dict(body=draft["body"], recipient=draft["recipient_hash"]))
    previous = next((e for e in prospect.get("outreach_events", [])
                     if e.get("idempotency_key") == idempotency_key and e["status"] == "SENT"), None)
    if previous and previous["version_sha256"] == version and stage(prospect, version) == "SENT":
        return previous["result"]
    if stage(prospect, version) != "SEND_ELIGIBLE":
        raise ValueError("Message is not send eligible")
    # Mandatory immediate recheck after approval and queueing.
    if not eligibility(prospect, version, now=now):
        event(prospect, version, "BLOCKED", now, failure_code="eligibility_changed")
        raise ValueError("Recipient or approval eligibility changed")
    if previous:
        return previous["result"]  # Content/recipient already simulated; never replay.
    if sum(e["status"] == "SENT" and int(e["timestamp"]) // 86400 == int(now) // 86400
           for e in prospect.get("outreach_events", [])) >= 3:
        event(prospect, version, "BLOCKED", now, failure_code="sandbox_daily_cap")
        raise ValueError("Sandbox daily cap reached")
    try:
        result = transport.send(idempotency_key)
    except Exception:
        event(prospect, version, "FAILED", now, failure_code="sandbox_transport_failed")
        raise ValueError("Sandbox transport failed") from None
    event(prospect, version, "SENT", now, result=result, idempotency_key=idempotency_key)
    return result


def revoke_outreach(prospect, version, *, actor, reason, now):
    current_draft(prospect, version)
    record = actor_record(actor, reason, now)
    append(prospect, "approvals", dict(
        **record, action_type="outreach", decision="revoked", version_sha256=version,
    ))
    event(prospect, version, "REJECTED", now)


def opt_out(prospect, *, actor, reason, now):
    record = actor_record(actor, reason, now)
    append(prospect, "suppression_events", dict(**record, status="OPTED_OUT"))
    if prospect.get("outreach_version"):
        event(prospect, prospect["outreach_version"], "OPTED_OUT", now, decision_record=record)
    prospect["status"] = "suppressed"
    prospect["draft"] = None
    prospect["proposal_version"] = None
    prospect.setdefault("contact_permission", {})["opted_out"] = True
