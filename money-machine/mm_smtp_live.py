"""Canonical manually invoked SMTP integration. No scheduler or automatic retry.

The durable claim, provider-neutral intent, send ledger, and event outbox share
one SQLite transaction. SMTP acceptance is not delivery or a verified receipt.
The JSONL event log is a replayable projection of the durable SQLite outbox.
"""

from __future__ import annotations

import json
import os
import re
import smtplib
import subprocess
from pathlib import Path

import mm_approval
import mm_core as core
import mm_email_lifecycle as lifecycle
import mm_email_tracking as tracking
import mm_smtp_candidate as engine

CAMPAIGN = "owner-exact-approved-smtp"
KEYCHAIN_SERVICE = "CATALYX WEBSITE-AUDITOR Gmail Bridge replacement-v2"
DDL = """CREATE TABLE IF NOT EXISTS smtp_event_outbox(
  event_id TEXT PRIMARY KEY,
  message_id INTEGER NOT NULL REFERENCES mm_messages(id),
  submission_key TEXT NOT NULL,
  event_json TEXT NOT NULL,
  created_at TEXT NOT NULL
)"""


def keychain_password(account):
    if account != engine.SENDER:
        raise engine.SubmissionHeldError("unregistered_sender")
    result = subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account, "-w"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    value = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"[a-z]{16}", value):
        raise engine.SubmissionHeldError("sender_keychain_credential_unavailable")
    return value


def _strict_approval(db, message_id, envelope):
    """Preserve the canonical approval artifact, copy and readiness gates."""
    row = db.execute("SELECT * FROM mm_messages WHERE id=?", (message_id,)).fetchone()
    if not row or not row["approval_ref"] or not row["approved_by"]:
        raise engine.SubmissionHeldError("human_approval_artifact_required")
    receipt = core.receipt(
        db, row["approval_ref"], "approval", row["business_id"], message_id, envelope.content_hash
    )
    if receipt["verified_by"] != row["approved_by"]:
        raise engine.SubmissionHeldError("approval_actor_mismatch")
    reasons = core.readiness(db, row["business_id"], row["evidence_id"], row["recipient"])
    if reasons:
        raise engine.SubmissionHeldError("canonical_recipient_or_evidence_readiness_failed")
    from mm_outreach import require_copy

    require_copy(row["body"], initial=row["kind"] == "initial")


def _event(db, message_id, envelope, kind, status, note):
    row = db.execute("SELECT business_id FROM mm_messages WHERE id=?", (message_id,)).fetchone()
    event = tracking.normalize_event(
        {
            "provider": "gmail",
            "provider_event_id": envelope.submission_key + ":" + kind,
            "message_id": str(message_id),
            "business_id": row["business_id"],
            "recipient": envelope.recipient,
            "kind": kind,
            "status": status,
            "note": note,
        }
    )
    db.execute(
        "INSERT INTO smtp_event_outbox VALUES(?,?,?,?,?)",
        (
            event["event_id"],
            message_id,
            envelope.submission_key,
            json.dumps(event, sort_keys=True),
            core.now(),
        ),
    )


def _claim(db, message_id, envelope):
    current = engine._approved_envelope(db, message_id)
    if current != envelope:
        raise engine.SubmissionHeldError("message_changed_before_claim")
    row = db.execute("SELECT business_id FROM mm_messages WHERE id=?", (message_id,)).fetchone()
    bid = row["business_id"]
    # An unresolved claim cannot be evaded by creating another message/campaign.
    prior = db.execute(
        "SELECT 1 FROM smtp_candidate_submissions s JOIN mm_messages m ON m.id=s.message_id "
        "WHERE s.message_id<>? AND (m.business_id=? OR lower(trim(m.recipient))=?)",
        (message_id, bid, envelope.recipient.lower()),
    ).fetchone()
    if prior:
        raise engine.SubmissionHeldError("recipient_or_business_submission_requires_review")
    if mm_approval.quarantine_check(db)["quarantined"]:
        raise engine.SubmissionHeldError("bounce_quarantine")
    approval = db.execute(
        "SELECT id,status,content_hash FROM approval_records "
        "WHERE business_id=? ORDER BY id DESC LIMIT 1",
        (bid,),
    ).fetchone()
    if (
        not approval
        or approval["status"] != "APPROVED"
        or approval["content_hash"] != envelope.content_hash
    ):
        raise engine.SubmissionHeldError("latest_exact_approval_required")
    key = lifecycle._intent_key(message_id, envelope.content_hash, CAMPAIGN)
    existing = db.execute(
        "SELECT status FROM email_delivery_intents WHERE idempotency_key=?", (key,)
    ).fetchone()
    if existing and existing["status"] != "planned":
        raise engine.SubmissionHeldError("prior_intent_requires_review")
    timestamp = core.now()
    db.execute(
        """INSERT OR IGNORE INTO email_delivery_intents(
      idempotency_key,message_id,business_id,recipient,content_hash,campaign,
      approval_id,transport,status,max_attempts,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,'none','planned',1,?,?)""",
        (
            key,
            message_id,
            bid,
            envelope.recipient.lower(),
            envelope.content_hash,
            CAMPAIGN,
            approval["id"],
            timestamp,
            timestamp,
        ),
    )
    db.execute(
        """INSERT INTO outreach_send_ledger(
      idempotency_key,business_id,recipient,content_hash,campaign,approval_id,
      transport,status,created_at,updated_at) VALUES(?,?,?,?,?,?,'gmail','planned',?,?)""",
        (
            envelope.submission_key,
            bid,
            envelope.recipient.lower(),
            envelope.content_hash,
            CAMPAIGN,
            approval["id"],
            timestamp,
            timestamp,
        ),
    )
    _event(
        db,
        message_id,
        envelope,
        "queued",
        "queued",
        "Durable single-attempt SMTP claim; no send yet.",
    )


def _finish(db, message_id, envelope, outcome, attempted):
    timestamp = core.now()
    accepted = outcome == "ACCEPTED"
    ledger_status = "sent" if accepted else "failed" if outcome == "REJECTED" else "quarantined"
    intent_status = "provider_accepted" if accepted else "dead_lettered"
    message_id_header = f"<wa-{envelope.submission_key}@gmail.com>"
    db.execute(
        "UPDATE outreach_send_ledger SET status=?,provider_message_id=?,sent_at=?,updated_at=? "
        "WHERE idempotency_key=?",
        (
            ledger_status,
            message_id_header,
            timestamp if accepted else None,
            timestamp,
            envelope.submission_key,
        ),
    )
    key = lifecycle._intent_key(message_id, envelope.content_hash, CAMPAIGN)
    db.execute(
        "UPDATE email_delivery_intents SET status=?,attempt_count=?,provider_message_id=?, "
        "last_error=?,updated_at=? WHERE idempotency_key=?",
        (
            intent_status,
            int(attempted),
            message_id_header,
            None if accepted else outcome,
            timestamp,
            key,
        ),
    )
    note = (
        (
            "SMTP server accepted the submission. Inbox delivery is unconfirmed; "
            "a verified external receipt is still separate."
        )
        if accepted
        else (f"{outcome}: no automatic retry. Reconcile the durable claim before further action.")
    )
    _event(
        db, message_id, envelope, "provider_accepted" if accepted else "failed", intent_status, note
    )


def project_events(db, event_store=None):
    """Replay every durable event idempotently; never submit or clear a claim."""
    target = Path(event_store) if event_store else core.root() / "state/email-events.jsonl"
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    event_store = target
    count = 0
    for row in db.execute("SELECT event_json FROM smtp_event_outbox ORDER BY created_at,event_id"):
        result = tracking.record(json.loads(row["event_json"]), event_store)
        count += int(result["recorded"])
    return {"events_projected": count, "provider_calls": 0, "claims_cleared": 0}


def submit(
    db,
    message_id,
    *,
    expected_content_hash=None,
    password_loader=None,
    smtp_factory=None,
    event_store=None,
):
    engine._policy()
    if db.in_transaction:
        raise engine.SubmissionHeldError("caller_transaction_must_be_closed")
    # All message, consent and suppression gates pass before even schema setup.
    envelope = engine._approved_envelope(db, message_id)
    _strict_approval(db, message_id, envelope)
    db.execute("PRAGMA synchronous=FULL")
    mm_approval.migrate(db)
    lifecycle.migrate(db)
    db.execute(DDL)
    db.commit()
    result = engine.submit(
        db,
        message_id,
        password_loader=password_loader or keychain_password,
        smtp_factory=smtp_factory or smtplib.SMTP_SSL,
        claim_hook=_claim,
        result_hook=_finish,
        approval_hook=_strict_approval,
        expected_content_hash=expected_content_hash,
    )
    try:
        result.update(event_projection=project_events(db, event_store))
    except Exception:
        # The authoritative event remains in SQLite; projection failure never retries SMTP.
        result["event_projection"] = {"state": "PENDING_REPLAY", "provider_calls": 0}
    result.update(
        transport="gmail",
        automatic_sending=False,
        shared_lifecycle_recorded=True,
        external_receipt_verified=False,
    )
    return result


def reconciliation_status(db, message_id):
    """Read-only claim inspection. Reconciliation never releases a resend."""
    names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    claim = None
    if "smtp_candidate_submissions" in names:
        row = db.execute(
            "SELECT message_id,submission_key,content_hash,status,created_at,updated_at "
            "FROM smtp_candidate_submissions WHERE message_id=?",
            (message_id,),
        ).fetchone()
        claim = dict(row) if row else None
    return {
        "message_id": message_id,
        "claim": claim,
        "automatic_retry": False,
        "resend_authorized": False,
        "database_writes": 0,
        "provider_calls": 0,
        "next_action": "Review independent provider evidence; claim is never automatically cleared."
        if claim
        else "No submission claim recorded.",
    }
