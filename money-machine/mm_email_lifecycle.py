"""Reconstructable, human-approved email delivery intent lifecycle.

This module prepares delivery intent only. It never calls a provider, sends mail,
creates approval records, removes suppression, or retries work automatically.
A separately approved transport may later consume a PLANNED intent.
"""
from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

import mm_core as core
import mm_email_tracking as tracking

STATUSES = {
    "planned",
    "retryable_failed",
    "dead_lettered",
    "provider_accepted",
    "delivered",
    "delayed",
    "bounced",
    "replied",
    "suppressed",
    "failed",
}
TERMINAL = {"dead_lettered", "provider_accepted", "delivered", "bounced", "replied", "suppressed"}

DDL = """
CREATE TABLE IF NOT EXISTS email_delivery_intents(
  idempotency_key TEXT PRIMARY KEY,
  message_id INTEGER NOT NULL,
  business_id INTEGER NOT NULL,
  recipient TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  campaign TEXT NOT NULL,
  approval_id INTEGER NOT NULL,
  transport TEXT NOT NULL CHECK(transport='none'),
  status TEXT NOT NULL CHECK(status IN ('planned','retryable_failed','dead_lettered','provider_accepted','delivered','delayed','bounced','replied','suppressed','failed')),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
  max_attempts INTEGER NOT NULL DEFAULT 3 CHECK(max_attempts BETWEEN 1 AND 10),
  provider_message_id TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS email_delivery_intents_message ON email_delivery_intents(message_id);
"""


def migrate(db: sqlite3.Connection) -> None:
    db.executescript(DDL)


def _row(db: sqlite3.Connection, sql: str, args: tuple[Any, ...]):
    return db.execute(sql, args).fetchone()


def _has_table(db: sqlite3.Connection, name: str) -> bool:
    return bool(_row(db, "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)))


def _suppression_reason(db: sqlite3.Connection, business_id: int, recipient: str) -> str | None:
    address = recipient.strip().lower()
    if _has_table(db, "mm_suppression") and _row(
        db, "SELECT reason FROM mm_suppression WHERE lower(trim(address))=?", (address,)
    ):
        return "address_suppressed"
    if _has_table(db, "contacts") and _row(
        db,
        "SELECT 1 FROM contacts WHERE business_id=? AND lower(trim(address_or_channel))=? AND do_not_contact=1",
        (business_id, address),
    ):
        return "contact_do_not_contact"
    if _has_table(db, "mm_holds") and _row(db, "SELECT 1 FROM mm_holds WHERE business_id=?", (business_id,)):
        return "business_hold"
    if _has_table(db, "mm_deals") and _row(
        db, "SELECT 1 FROM mm_deals WHERE business_id=? AND stage='SUPPRESSED'", (business_id,)
    ):
        return "business_suppressed"
    return None


def _intent_key(message_id: int, content_hash: str, campaign: str) -> str:
    raw = f"message:{message_id}|content:{content_hash}|campaign:{campaign.strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _dict(row) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _event_store(path=None):
    return path


def create_intent(
    db: sqlite3.Connection,
    message_id: int,
    campaign: str,
    *,
    max_attempts: int = 3,
    event_store=None,
) -> dict[str, Any]:
    """Create or replay a delivery intent after exact human approval.

    The only created state is a provider-neutral ``transport='none'`` intent
    plus a queued event. No provider call or automatic retry is possible.
    """
    if not isinstance(campaign, str) or not campaign.strip():
        raise ValueError("campaign required")
    if not 1 <= max_attempts <= 10:
        raise ValueError("max_attempts must be between 1 and 10")
    migrate(db)
    message = _row(
        db,
        "SELECT id,business_id,recipient,body,sent_at,invalidated_reason FROM mm_messages WHERE id=?",
        (message_id,),
    )
    if not message:
        raise ValueError("message not found")
    if message["sent_at"] is not None:
        raise ValueError("message already sent")
    if message["invalidated_reason"] is not None:
        raise ValueError("message draft invalidated")
    content_hash = core.digest(message["recipient"], message["body"])
    approval = _row(
        db,
        "SELECT id,content_hash FROM approval_records WHERE business_id=? AND status='APPROVED' ORDER BY id DESC LIMIT 1",
        (message["business_id"],),
    )
    if not approval or approval["content_hash"] != content_hash:
        raise ValueError("exact human approval required")
    reason = _suppression_reason(db, message["business_id"], message["recipient"])
    if reason:
        raise ValueError("suppressed: " + reason)

    key = _intent_key(message_id, content_hash, campaign)
    existing = _row(db, "SELECT * FROM email_delivery_intents WHERE idempotency_key=?", (key,))
    if existing:
        return _result(existing, replayed=True)

    timestamp = core.now()
    db.execute(
        """INSERT INTO email_delivery_intents(
            idempotency_key,message_id,business_id,recipient,content_hash,campaign,
            approval_id,transport,status,max_attempts,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,'none','planned',?,?,?)""",
        (
            key,
            message_id,
            message["business_id"],
            message["recipient"].strip().lower(),
            content_hash,
            campaign.strip(),
            approval["id"],
            max_attempts,
            timestamp,
            timestamp,
        ),
    )
    tracking.record(
        {
            "provider": "none",
            "provider_event_id": key,
            "message_id": str(message_id),
            "business_id": message["business_id"],
            "recipient": message["recipient"],
            "kind": "queued",
            "status": "queued",
            "note": "Provider-neutral intent; no send performed",
        },
        _event_store(event_store),
    )
    return _result(_row(db, "SELECT * FROM email_delivery_intents WHERE idempotency_key=?", (key,)))


def record_result(
    db: sqlite3.Connection,
    idempotency_key: str,
    status: str,
    *,
    provider_message_id: str | None = None,
    error: str | None = None,
    max_attempts: int | None = None,
    event_store=None,
) -> dict[str, Any]:
    """Record a provider-neutral outcome; retry/dead-letter is bounded and explicit."""
    status = str(status).strip().lower()
    if status not in STATUSES - {"planned", "retryable_failed", "dead_lettered"}:
        raise ValueError("unsupported delivery result")
    if max_attempts is not None and not 1 <= max_attempts <= 10:
        raise ValueError("max_attempts must be between 1 and 10")
    migrate(db)
    intent = _row(db, "SELECT * FROM email_delivery_intents WHERE idempotency_key=?", (idempotency_key,))
    if not intent:
        raise ValueError("unknown delivery intent")
    message = _row(db, "SELECT recipient,body,sent_at,invalidated_reason FROM mm_messages WHERE id=?", (intent["message_id"],))
    if not message or message["sent_at"] is not None or message["invalidated_reason"] is not None:
        raise ValueError("message is no longer a valid unsent draft")
    if core.digest(message["recipient"], message["body"]) != intent["content_hash"]:
        raise ValueError("draft changed after approval")
    current = intent["status"]
    if current in TERMINAL:
        if current == status:
            return _result(intent, replayed=True)
        raise ValueError("terminal delivery state cannot regress")

    attempt_count = intent["attempt_count"]
    next_status = status
    if status in {"failed", "delayed"}:
        attempt_count += 1
        bound = max_attempts if max_attempts is not None else intent["max_attempts"]
        next_status = "dead_lettered" if attempt_count >= bound else "retryable_failed"
    timestamp = core.now()
    db.execute(
        """UPDATE email_delivery_intents SET status=?,attempt_count=?,provider_message_id=coalesce(?,provider_message_id),
           last_error=coalesce(?,last_error),updated_at=? WHERE idempotency_key=?""",
        (next_status, attempt_count, provider_message_id, error[:1000] if error else None, timestamp, idempotency_key),
    )
    kind = {
        "provider_accepted": "provider_accepted",
        "delivered": "delivered",
        "delayed": "delayed",
        "failed": "failed",
        "bounced": "bounce",
        "replied": "reply",
        "suppressed": "suppression",
    }[status]
    tracking.record(
        {
            "provider": "none",
            "provider_event_id": provider_message_id or f"{idempotency_key}:{attempt_count}:{status}",
            "message_id": str(intent["message_id"]),
            "business_id": intent["business_id"],
            "recipient": intent["recipient"],
            "kind": kind,
            "status": next_status,
            "note": error or "Provider-neutral result; no send performed",
        },
        _event_store(event_store),
    )
    return _result(_row(db, "SELECT * FROM email_delivery_intents WHERE idempotency_key=?", (idempotency_key,)))


def reconstruct(db: sqlite3.Connection, message_id: int, *, event_store=None) -> dict[str, Any]:
    """Return the message, exact approval, intent and ordered event trail."""
    migrate(db)
    message = _row(db, "SELECT * FROM mm_messages WHERE id=?", (message_id,))
    if not message:
        raise ValueError("message not found")
    approval = _row(
        db,
        "SELECT * FROM approval_records WHERE business_id=? AND status='APPROVED' ORDER BY id DESC LIMIT 1",
        (message["business_id"],),
    )
    intents = db.execute(
        "SELECT * FROM email_delivery_intents WHERE message_id=? ORDER BY created_at,idempotency_key", (message_id,)
    ).fetchall()
    events = tracking.events_for(str(message_id), _event_store(event_store))
    return {
        "message": _dict(message),
        "approval": _dict(approval),
        "intents": [_dict(row) for row in intents],
        "events": events,
        "human_approval_required": True,
        "external_sends": 0,
        "paid_calls": 0,
        "model_cost_usd": 0.0,
    }


def _result(row, replayed=False) -> dict[str, Any]:
    result = _dict(row)
    result.update(
        {
            "replayed": replayed,
            "transport_send_performed": False,
            "external_sends": 0,
            "paid_calls": 0,
            "model_cost_usd": 0.0,
            "human_approval_required": True,
        }
    )
    return result
