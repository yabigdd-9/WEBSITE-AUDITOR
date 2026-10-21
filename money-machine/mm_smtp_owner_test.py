"""One-off diagnostic email between authenticated owner mailboxes only.

This separate purpose never fabricates a prospect, contact consent or audit.
It shares the canonical Gmail policy, daily claim cap and zero-cost accounting.
No scheduler, bulk route, arbitrary recipient, automatic approval or retry.
"""

from __future__ import annotations

import imaplib
import json
import os
import re
import smtplib
import ssl
import subprocess
import uuid
from pathlib import Path

import mm_core as core
import mm_email_tracking as tracking
import mm_smtp_candidate as engine
import mm_smtp_live as live

ACCOUNTS = (engine.SENDER, "yabigdd@gmail.com")
SUBJECT = "Website Auditor owner email test"
DDL = """
CREATE TABLE IF NOT EXISTS owner_transport_test_packets(
 id INTEGER PRIMARY KEY,recipient TEXT NOT NULL,body TEXT NOT NULL,content_hash TEXT NOT NULL UNIQUE,
 verification TEXT NOT NULL,prepared_by TEXT NOT NULL,created_at TEXT NOT NULL,
 approved_hash TEXT,approved_by TEXT
);
CREATE TABLE IF NOT EXISTS owner_transport_test_claims(
 packet_id INTEGER PRIMARY KEY REFERENCES owner_transport_test_packets(id),
 submission_key TEXT NOT NULL UNIQUE,created_day TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('RESERVED','ACCEPTED','REJECTED','UNKNOWN','HELD')),
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS owner_transport_test_events(
 event_id TEXT PRIMARY KEY,packet_id INTEGER NOT NULL REFERENCES owner_transport_test_packets(id),
 event_json TEXT NOT NULL,created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS owner_test_packet_immutable
BEFORE UPDATE OF recipient,body,content_hash,verification,prepared_by,created_at ON owner_transport_test_packets
BEGIN SELECT RAISE(ABORT,'Owner test packet is immutable; prepare a new packet'); END;
"""


def _actor(actor):
    if not isinstance(actor, str) or not 2 <= len(actor.strip()) <= 120:
        raise engine.SubmissionHeldError("explicit_owner_identity_required")
    return actor.strip()


def _recipient(recipient):
    if recipient not in ACCOUNTS:
        raise engine.SubmissionHeldError("owner_test_recipient_not_allowlisted")
    return recipient


def verify_owned_mailbox(account):
    _recipient(account)
    result = subprocess.run(
        [
            "/usr/bin/security",
            "find-generic-password",
            "-s",
            live.KEYCHAIN_SERVICE,
            "-a",
            account,
            "-w",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    password = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"[a-z]{16}", password):
        raise engine.SubmissionHeldError("owner_mailbox_keychain_credential_unavailable")
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        client = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=context, timeout=20)
        try:
            client.login(account, password)
            if client.select("INBOX", readonly=True)[0] != "OK":
                raise engine.SubmissionHeldError("owner_mailbox_verification_failed")
        finally:
            try:
                client.logout()
            except Exception:
                pass
    except Exception:
        raise engine.SubmissionHeldError("owner_mailbox_verification_failed") from None
    return {
        "account": account,
        "source": "authenticated_readonly_imap",
        "authenticated": True,
        "checked_at": core.now(),
        "messages_read": 0,
        "external_messages_sent": 0,
    }


def prepare(db, recipient, *, actor, verifier=verify_owned_mailbox):
    if db.in_transaction:
        raise engine.SubmissionHeldError("caller_transaction_must_be_closed")
    recipient = _recipient(recipient)
    actor = _actor(actor)
    proof = verifier(recipient)
    _proof(proof, recipient)
    reference = uuid.uuid4().hex[:12]
    body = (
        f"Subject: {SUBJECT}\n\nHi Dion,\n\n"
        "This is a one-off test of Website Auditor's owner-approved Gmail transport.\n\n"
        "This message contains no prospect or customer information. SMTP acceptance alone "
        "does not confirm inbox delivery. Automatic sending remains off.\n\n"
        "No action is required. You can reply to confirm receipt.\n\n"
        f"Dion\nCATALYX Labs\n\nOwner test reference: {reference}\n"
    )
    db.executescript(DDL)
    cursor = db.execute(
        "INSERT INTO owner_transport_test_packets(recipient,body,content_hash,verification,prepared_by,created_at) VALUES(?,?,?,?,?,?)",
        (
            recipient,
            body,
            core.digest(recipient, body),
            json.dumps(proof, sort_keys=True),
            actor,
            core.now(),
        ),
    )
    db.commit()
    return preview(db, cursor.lastrowid)


def _proof(proof, recipient):
    if (
        not isinstance(proof, dict)
        or proof.get("account") != recipient
        or proof.get("source") != "authenticated_readonly_imap"
        or proof.get("authenticated") is not True
        or not core.fresh(proof.get("checked_at"), 1)
    ):
        raise engine.SubmissionHeldError("fresh_authenticated_owner_mailbox_required")


def _packet(db, packet_id, content_hash):
    if type(packet_id) is not int or packet_id < 1:
        raise engine.SubmissionHeldError("invalid_owner_test_packet")
    row = db.execute(
        "SELECT * FROM owner_transport_test_packets WHERE id=?", (packet_id,)
    ).fetchone()
    if not row:
        raise engine.SubmissionHeldError("owner_test_packet_missing")
    _recipient(row["recipient"])
    _proof(json.loads(row["verification"]), row["recipient"])
    envelope = engine.prepare(packet_id, row["recipient"], row["body"], purpose="owner-test")
    if row["content_hash"] != content_hash or envelope.content_hash != content_hash:
        raise engine.SubmissionHeldError("exact_owner_test_content_approval_required")
    return row, envelope


def preview(db, packet_id=None):
    exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='owner_transport_test_packets'"
    ).fetchone()
    if not exists:
        return {"available": False, "external_messages_sent_by_preview": 0}
    row = (
        db.execute("SELECT * FROM owner_transport_test_packets WHERE id=?", (packet_id,)).fetchone()
        if packet_id
        else db.execute(
            "SELECT * FROM owner_transport_test_packets ORDER BY id DESC LIMIT 1"
        ).fetchone()
    )
    if not row:
        return {"available": False, "external_messages_sent_by_preview": 0}
    result = dict(row)
    result["verification"] = json.loads(result["verification"])
    claim = db.execute(
        "SELECT status,submission_key,created_at,updated_at FROM owner_transport_test_claims WHERE packet_id=?",
        (row["id"],),
    ).fetchone()
    result.update(
        available=True,
        purpose="authenticated_owner_mailbox_test",
        claim=dict(claim) if claim else None,
        approval_required=True,
        automatic_retry=False,
        external_messages_sent_by_preview=0,
        verification_current=core.fresh(result["verification"].get("checked_at"), 1),
    )
    try:
        policy = engine._policy()
        remaining = max(0, policy["daily_cap"] - engine.daily_claim_count(db, core.now()[:10]))
    except (ValueError, OSError):
        remaining = 0
    result.update(
        remaining_daily_claims=remaining,
        ready_for_owner_confirmation=(
            claim is None
            and result["verification_current"]
            and remaining > 0
            and os.environ.get("MM_EXTERNAL_SEND_DISABLED") != "1"
        ),
    )
    return result


def _event(db, packet_id, envelope, status):
    event = tracking.normalize_event(
        {
            "provider": "gmail",
            "provider_event_id": envelope.submission_key + ":" + status,
            "message_id": f"owner-test:{packet_id}",
            "recipient": envelope.recipient,
            "kind": "provider_accepted"
            if status == "ACCEPTED"
            else "queued"
            if status == "RESERVED"
            else "failed",
            "status": "provider_accepted"
            if status == "ACCEPTED"
            else "queued"
            if status == "RESERVED"
            else "dead_lettered",
            "note": f"Owner mailbox transport test: {status}. Delivery unconfirmed. No automatic retry.",
        }
    )
    db.execute(
        "INSERT INTO owner_transport_test_events VALUES(?,?,?,?)",
        (event["event_id"], packet_id, json.dumps(event, sort_keys=True), core.now()),
    )


def _reserve(db, packet_id, content_hash, actor, cap):
    db.execute("PRAGMA synchronous=FULL")
    db.execute("BEGIN IMMEDIATE")
    try:
        row, envelope = _packet(db, packet_id, content_hash)
        if db.execute(
            "SELECT 1 FROM owner_transport_test_claims WHERE packet_id=?", (packet_id,)
        ).fetchone():
            raise engine.SubmissionHeldError("prior_owner_test_submission_requires_reconciliation")
        if db.execute(
            "SELECT 1 FROM owner_transport_test_claims c JOIN owner_transport_test_packets p ON p.id=c.packet_id "
            "WHERE p.recipient=? AND c.status IN ('RESERVED','UNKNOWN') LIMIT 1",
            (row["recipient"],),
        ).fetchone():
            raise engine.SubmissionHeldError("prior_uncertain_owner_test_requires_reconciliation")
        timestamp = core.now()
        if engine.daily_claim_count(db, timestamp[:10]) >= cap:
            raise engine.SubmissionHeldError("daily_cap_reserved")
        db.execute(
            "UPDATE owner_transport_test_packets SET approved_hash=?,approved_by=? WHERE id=?",
            (content_hash, actor, packet_id),
        )
        db.execute(
            "INSERT INTO owner_transport_test_claims VALUES(?,?,?,?,?,?)",
            (packet_id, envelope.submission_key, timestamp[:10], "RESERVED", timestamp, timestamp),
        )
        _event(db, packet_id, envelope, "RESERVED")
        db.commit()
        return envelope
    except Exception:
        db.rollback()
        raise


def submit(
    db,
    packet_id,
    *,
    content_hash,
    actor,
    password_loader=live.keychain_password,
    smtp_factory=smtplib.SMTP_SSL,
    event_store=None,
):
    if os.environ.get("MM_EXTERNAL_SEND_DISABLED") == "1":
        raise engine.SubmissionHeldError("transport_is_disabled")
    config = engine._policy()
    actor = _actor(actor)
    if db.in_transaction:
        raise engine.SubmissionHeldError("caller_transaction_must_be_closed")
    envelope = _reserve(db, packet_id, content_hash, actor, config["daily_cap"])
    outcome, attempted = "HELD", False
    try:
        password = password_loader(engine.SENDER)
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        with smtp_factory("smtp.gmail.com", 465, timeout=20, context=context) as client:
            client.ehlo()
            client.login(engine.SENDER, password)
            db.execute("BEGIN IMMEDIATE")
            row, current = _packet(db, packet_id, content_hash)
            if (
                current != envelope
                or row["approved_hash"] != content_hash
                or row["approved_by"] != actor
                or engine._policy() != config
            ):
                raise engine.SubmissionHeldError("owner_test_or_policy_changed")
            attempted = True
            outcome = (
                "REJECTED"
                if client.sendmail(engine.SENDER, [envelope.recipient], envelope.wire)
                else "ACCEPTED"
            )
    except Exception as exc:
        if outcome != "ACCEPTED":
            explicit = isinstance(
                exc,
                (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError),
            )
            outcome = "REJECTED" if attempted and explicit else "UNKNOWN" if attempted else "HELD"
    finally:
        db.rollback()
    try:
        db.execute(
            "UPDATE owner_transport_test_claims SET status=?,updated_at=? WHERE packet_id=?",
            (outcome, core.now(), packet_id),
        )
        _event(db, packet_id, envelope, outcome)
        db.commit()
    except Exception:
        db.rollback()
        raise
    projected = True
    try:
        target = Path(event_store) if event_store else core.root() / "state/email-events.jsonl"
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        for event in db.execute(
            "SELECT event_json FROM owner_transport_test_events ORDER BY created_at,event_id"
        ):
            tracking.record(json.loads(event["event_json"]), target)
    except Exception:
        projected = False
    return {
        "packet_id": packet_id,
        "status": outcome,
        "submission_key": envelope.submission_key,
        "provider_submission_attempted": attempted,
        "delivery_confirmed": False,
        "automatic_retry": False,
        "event_projection_complete": projected,
        "purpose": "authenticated_owner_mailbox_test",
        "prospects_contacted": 0,
        "external_receipt_verified": False,
    }
