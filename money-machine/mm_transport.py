"""Configurable transport with exact approval and at-most-once dispatch.

The default configuration is draft-only. When an operator explicitly enables
the Himalaya provider, this module still requires a channel-bound approval,
current packet readiness, verified contact provenance, suppression checks, a
daily attempt cap, and a durable attempt reservation before provider I/O.
Provider acceptance is not treated as a verified send receipt; an operator
must import and reconcile that receipt separately.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import mm_core as core


_TRUTHY = {"1", "true", "yes", "on"}


def _kill_switch_enabled():
    return os.environ.get("MM_EXTERNAL_SEND_DISABLED", "").strip().lower() in _TRUTHY


def load_config(path=None):
    expected_dir = (Path(__file__).resolve().parent / "config").resolve()
    if path is None:
        path = expected_dir / "transport.json"
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(expected_dir):
        raise ValueError("Config path escapes allowed directory")
    doc = json.loads(resolved.read_text(encoding="utf-8"))
    required = {
        "version", "enabled", "provider", "daily_cap",
        "requires_exact_approval", "requires_verified_recipient",
        "requires_suppression_check", "external_send_allowed",
    }
    if not isinstance(doc, dict) or set(doc) != required:
        raise ValueError("Transport config must use the canonical schema")
    if type(doc["version"]) is not int or doc["version"] != 1:
        raise ValueError("Unsupported transport config version")
    for name in ("enabled", "external_send_allowed", "requires_exact_approval",
                 "requires_verified_recipient", "requires_suppression_check"):
        if type(doc[name]) is not bool:
            raise ValueError(f"{name} must be boolean")
    if type(doc["daily_cap"]) is not int or doc["daily_cap"] < 0:
        raise ValueError("daily_cap must be a non-negative integer")
    if doc["provider"] not in ("none", "mock", "himalaya"):
        raise ValueError("Transport provider must be none, mock, or himalaya")
    if not all(doc[name] for name in (
        "requires_exact_approval", "requires_verified_recipient",
        "requires_suppression_check",
    )):
        raise ValueError("Mandatory transport safety gates cannot be disabled")
    if doc["provider"] == "none" and (doc["enabled"] or doc["external_send_allowed"]):
        raise ValueError("The none provider must remain disabled")
    if doc["provider"] == "mock" and doc["external_send_allowed"]:
        raise ValueError("Mock transport cannot enable external sends")
    if doc["external_send_allowed"] and (
        not doc["enabled"] or doc["provider"] != "himalaya" or doc["daily_cap"] < 1
    ):
        raise ValueError("External sends require enabled Himalaya transport and a positive daily cap")
    if doc["enabled"] and doc["provider"] == "none":
        raise ValueError("An enabled transport must select a provider")
    return doc


def status(path=None, d=None):
    config = load_config(path)
    kill_switch = _kill_switch_enabled()
    effective = bool(config["enabled"] and config["external_send_allowed"]
                     and config["provider"] == "himalaya" and config["daily_cap"] > 0
                     and not kill_switch)
    unresolved = None
    if d is not None:
        exists = d.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mm_transport_attempts'").fetchone()
        unresolved = (d.execute(
            "SELECT count(*) FROM mm_transport_attempts WHERE status!='RECONCILED'"
        ).fetchone()[0] if exists else 0)
    if kill_switch:
        reason = "External transport is blocked by MM_EXTERNAL_SEND_DISABLED."
    elif effective:
        reason = "Himalaya dispatch is configured; each packet still needs exact human approval."
    else:
        reason = "Transport is disabled; drafts remain local."
    return {
        "checked_at": core.now(),
        "mode": "SEND_CONFIGURED" if effective else "DRAFT_ONLY",
        "provider": config["provider"],
        "enabled": config["enabled"],
        "configured_external_send_allowed": config["external_send_allowed"],
        "external_send_allowed": effective,
        "runtime_kill_switch": kill_switch,
        "daily_cap": config["daily_cap"],
        "network_send_implementation": config["provider"] == "himalaya",
        "approval_required": True,
        "unreconciled_attempts": unresolved,
        "reason": reason,
    }


def _message_bytes(packet, from_address):
    body = packet["body"]
    if not body.startswith("Subject: ") or "\n\n" not in body:
        raise ValueError("Stored draft must contain its reviewed Subject line and body")
    subject_line, content = body.split("\n\n", 1)
    subject = subject_line.removeprefix("Subject: ").strip()
    if not subject or "\n" in subject or "\r" in subject:
        raise ValueError("A single reviewed subject line is required")
    message = EmailMessage(policy=SMTP)
    message["From"] = from_address
    message["To"] = packet["recipient"]
    message["Subject"] = subject
    message.set_content(content)
    return message.as_bytes()


def _provider_message_id(stdout):
    try:
        value = json.loads(stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else stdout or "")
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(value, dict):
        for key in ("message_id", "messageId", "id"):
            found = value.get(key)
            if isinstance(found, (str, int)) and str(found).strip():
                return str(found).strip()[:256]
        for child in value.values():
            if isinstance(child, dict):
                found = _provider_message_id(json.dumps(child))
                if found:
                    return found
    return None


def send_approved(d, packet_id):
    """Make one durable dispatch attempt for a fully approved message packet.

    A started attempt is never automatically retried. A crash or ambiguous
    provider response must be resolved with provider evidence by an operator.
    """
    config = load_config()
    if _kill_switch_enabled():
        raise ValueError("External transport blocked by MM_EXTERNAL_SEND_DISABLED")
    if not (config["enabled"] and config["external_send_allowed"]
            and config["provider"] == "himalaya" and config["daily_cap"] > 0):
        raise ValueError("External Himalaya transport is not explicitly enabled")

    account = os.environ.get("HIMALAYA_ACCOUNT", "").strip()
    from_address = os.environ.get("HIMALAYA_FROM_ADDRESS", "").strip()
    if not account or any(ord(c) < 32 for c in account):
        raise ValueError("HIMALAYA_ACCOUNT must be configured for the approved transport")
    if not from_address or "\n" in from_address or "\r" in from_address:
        raise ValueError("HIMALAYA_FROM_ADDRESS must be configured for the approved transport")
    binary = shutil.which("himalaya")
    if not binary:
        raise ValueError("Himalaya binary is unavailable")
    channel = f"himalaya|{account}|{from_address}"
    if d.in_transaction:
        raise ValueError("Commit the reviewed approval before requesting transport")

    # Serialize eligibility, daily-cap accounting and the unique packet
    # reservation. The reservation commits before calling the provider so a
    # crash cannot make a restart silently send the same packet again.
    d.execute("BEGIN IMMEDIATE")
    try:
        packet = d.execute("SELECT * FROM mm_messages WHERE id=?", (packet_id,)).fetchone()
        if not packet or packet["sent_at"] or packet["invalidated_reason"]:
            raise ValueError("Valid unsent message packet required")
        if packet["approval_status"] != "APPROVED" or packet["approved_channel"] != channel:
            raise ValueError("Exact human approval for this Himalaya account and sender is required")
        expected_hash = core.delivery_digest(packet["recipient"], packet["body"], channel)
        if packet["approved_hash"] != expected_hash:
            raise ValueError("Stored approval does not match the current content and transport channel")
        from mm_outreach import require_copy
        require_copy(packet["body"], initial=packet["kind"] == "initial")
        reasons = core.readiness(d, packet["business_id"], packet["evidence_id"], packet["recipient"])
        if reasons:
            raise ValueError("Packet is no longer ready: " + "; ".join(reasons))
        approval = core.receipt(
            d, packet["approval_ref"], "approval", packet["business_id"],
            packet_id, expected_hash,
        )
        if approval["verified_by"] != packet["approved_by"]:
            raise ValueError("Approval receipt does not match the recorded human approver")
        if d.execute("SELECT 1 FROM mm_transport_attempts WHERE message_id=?", (packet_id,)).fetchone():
            raise ValueError("This packet already has a transport attempt; reconcile it before taking action")

        today = datetime.now(timezone.utc).date().isoformat()
        attempts_today = d.execute(
            "SELECT count(*) FROM mm_transport_attempts WHERE started_at>=?",
            (today + "T00:00:00+00:00",),
        ).fetchone()[0]
        if attempts_today >= config["daily_cap"]:
            raise ValueError("Configured daily transport attempt cap has been reached")
        raw = _message_bytes(packet, from_address)
        idempotency_key = core.sha(f"himalaya\n{packet_id}\n{expected_hash}\n{channel}")
        started = core.now()
        d.execute(
            "INSERT INTO mm_transport_attempts(message_id,idempotency_key,provider,approval_hash,approved_channel,status,started_at,updated_at) VALUES(?,?,?,?,?,'DISPATCHING',?,?)",
            (packet_id, idempotency_key, "himalaya", expected_hash, channel, started, started),
        )
        d.commit()
    except Exception:
        d.rollback()
        raise

    # No temporary body file is written. The approval-bound bytes are passed
    # directly to Himalaya via stdin, and errors are not echoed to the caller.
    try:
        result = subprocess.run(
            [binary, "--account", account, "--json", "message", "send"],
            input=raw,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        with d:
            d.execute(
                "UPDATE mm_transport_attempts SET status='OUTCOME_UNKNOWN',updated_at=? WHERE message_id=? AND status='DISPATCHING'",
                (core.now(), packet_id),
            )
        return {"status": "OUTCOME_UNKNOWN", "provider": "himalaya", "external_sends": None,
                "possible_external_send": True, "receipt_reconciliation_required": True}

    if result.returncode != 0:
        with d:
            d.execute(
                "UPDATE mm_transport_attempts SET status='OUTCOME_UNKNOWN',updated_at=? WHERE message_id=? AND status='DISPATCHING'",
                (core.now(), packet_id),
            )
        return {"status": "OUTCOME_UNKNOWN", "provider": "himalaya", "external_sends": None,
                "possible_external_send": True, "receipt_reconciliation_required": True}

    provider_id = _provider_message_id(result.stdout)
    with d:
        d.execute(
            "UPDATE mm_transport_attempts SET status='PROVIDER_ACCEPTED',provider_message_id=?,updated_at=? WHERE message_id=? AND status='DISPATCHING'",
            (provider_id, core.now(), packet_id),
        )
    return {"status": "PROVIDER_ACCEPTED_PENDING_HUMAN_RECEIPT", "provider": "himalaya",
            "provider_message_id": provider_id, "external_sends": 1,
            "receipt_reconciliation_required": True}


def preflight_packet(packet):
    """Validate a serialized packet as review-only; never transmit it."""
    if not isinstance(packet, dict):
        raise ValueError("packet object required")
    failures = []
    if packet.get("approval_status") not in ("DRAFT", "HUMAN_APPROVAL_REQUIRED"):
        failures.append("packet_not_in_review_state")
    if packet.get("send_enabled") is not False:
        failures.append("packet_send_enabled")
    if packet.get("external_send_allowed") is not False:
        failures.append("packet_external_send_allowed")
    if packet.get("outbound_sent") != 0:
        failures.append("packet_claims_outbound_send")
    return {
        "passed": not failures,
        "failures": failures,
        "external_send_allowed": False,
        "network_calls": 0,
        "checked_at": core.now(),
    }
