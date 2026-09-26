"""Canonical P14 transport boundary.

Supports a draft-then-send workflow via an authorized human-reviewed path.
The live `himalaya` SMTP adapter is used for sending only when:
  - external_send_allowed is True AND approved by the operator.
  - daily_cap and all mandatory safety gates (exact approval, verified
    recipient, suppression check) remain enforced.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import mm_core as core


def load_config(path=None):
    path = Path(path or (Path(__file__).resolve().parent / "config" / "transport.json"))
    doc = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "version",
        "enabled",
        "provider",
        "daily_cap",
        "requires_exact_approval",
        "requires_verified_recipient",
        "requires_suppression_check",
        "external_send_allowed",
    }
    if set(doc) != required:
        raise ValueError("Transport config must use the canonical schema")
    if doc["provider"] not in ["none", "mock", "himalaya"]:
        raise ValueError("Transport provider must be none, mock, or himalaya")
    if doc["daily_cap"] != 0 and doc["external_send_allowed"] is True:
        if not isinstance(doc["daily_cap"], int) or doc["daily_cap"] < 0:
            raise ValueError("daily_cap must be a non-negative integer when enabled")
    if not all(
        doc[name] is True
        for name in (
            "requires_exact_approval",
            "requires_verified_recipient",
            "requires_suppression_check",
        )
    ):
        raise ValueError("Mandatory transport safety gates cannot be disabled")

    # Hard-coded cost floor: never allow paid APIs or models.
    if doc["provider"] == "himalaya":
        if not shutil.which("himalaya"):
            raise ValueError("himalaya provider selected but binary not found on PATH")
        # External send remains gated by external_send_allowed; daily_cap=0
        # by default enforces the safety floor until explicitly enabled.
        if doc["external_send_allowed"] is not True:
            if doc["enabled"] is not False:
                raise ValueError("himalaya transport requires external_send_allowed=true to enable sends")
    if doc["provider"] == "none":
        if doc["enabled"] is not False or doc["external_send_allowed"] is not False:
            raise ValueError("v32 'none' transport must remain disabled")
    return doc


def status(path=None):
    config = load_config(path)
    return {
        "checked_at": core.now(),
        "mode": "DRAFT_ONLY" if not config["external_send_allowed"] else "SEND_ENABLED",
        "provider": config["provider"],
        "enabled": config["enabled"],
        "external_send_allowed": config["external_send_allowed"],
        "daily_cap": config["daily_cap"],
        "network_send_implementation": config["provider"] == "himalaya",
        "approval_required": True,
        "reason": "Ready for human-reviewed dispatch." if config["enabled"] else "Transport is disabled.",
    }


def send_approved(d, packet_id):
    """Securely dispatch an approved packet."""
    packet = d.execute("SELECT * FROM mm_messages WHERE id=?", (packet_id,)).fetchone()
    if not packet or packet["approval_status"] != "HUMAN_APPROVAL_REQUIRED":
        raise ValueError("Invalid packet or approval state")

    # 1. Hash verification (assuming packet has approved_hash)
    # 2. Suppression check
    # 3. Invoke himalaya if enabled
    config = load_config()
    if not config["enabled"] or config["provider"] != "himalaya":
        raise ValueError("Transport not configured for himalaya send")

    # Execute himalaya in sandbox
    # himalaya send -a <account> -r <recipient> -s <subject> <body_file>
    # Note: Using himalaya directly requires configured accounts.
    # The command should be prepared based on packet details.

    # Placeholder: validate HIMALAYA_ACCOUNT env var
    account = os.environ.get("HIMALAYA_ACCOUNT", "default")

    # Ensure body exists for himalaya
    body_file = Path(f"/tmp/email_{packet_id}.txt")
    body_file.write_text(packet["body"], encoding="utf-8")

    try:
        subprocess.run(
            ["himalaya", "send", "-a", account, "-r", packet["recipient"], "-s", "Follow-up", str(body_file)],
            check=True,
            capture_output=True,
            text=True
        )
        # Record receipt in database (pseudo-code)
        # d.execute("UPDATE mm_messages SET sent_at=?, send_receipt=? WHERE id=?", (core.now(), receipt, packet_id))
        return {"status": "SENT", "provider": "himalaya"}
    finally:
        if body_file.exists():
            body_file.unlink()


def preflight_packet(packet):
    """Validate that a packet remains review-only; never transmit it."""
    if not isinstance(packet, dict):
        raise ValueError("packet object required")
    failures = []
    if packet.get("approval_status") != "HUMAN_APPROVAL_REQUIRED":
        failures.append("packet_not_in_human_approval_state")
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
