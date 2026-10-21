"""Canonical P14 transport boundary.

The committed default is draft-only. A private owner policy can enable the
registered Gmail adapter for explicit, exact-approved single-message submissions.
No scheduler or automatic retry is registered.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import uuid
from pathlib import Path

import mm_core as core


def load_config(path=None):
    default = Path(__file__).resolve().parent / "config" / "transport.json"
    override = core.root() / "state" / "transport-policy.json"
    private = path is None and (override.exists() or override.is_symlink())
    path = Path(path) if path is not None else (override if private else default)
    if private:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077
        ):
            raise ValueError("Owner transport policy must be a private regular file")

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate transport configuration field")
            result[key] = value
        return result

    doc = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
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
    if type(doc["version"]) is not int or doc["version"] != 1:
        raise ValueError("Unsupported transport version")
    if doc["provider"] == "none":
        if doc["enabled"] is not False or doc["external_send_allowed"] is not False:
            raise ValueError("Disabled transport must remain disabled")
        if type(doc["daily_cap"]) is not int or doc["daily_cap"] != 0:
            raise ValueError("Disabled transport daily_cap must be 0")
    elif doc["provider"] == "gmail":
        if doc["enabled"] is not True or doc["external_send_allowed"] is not True:
            raise ValueError("Gmail requires explicit owner enablement")
        if type(doc["daily_cap"]) is not int or not 1 <= doc["daily_cap"] <= 10:
            raise ValueError("Gmail daily_cap must be between 1 and 10")
    else:
        raise ValueError("Unregistered transport provider")
    if not all(
        doc[name] is True
        for name in (
            "requires_exact_approval",
            "requires_verified_recipient",
            "requires_suppression_check",
        )
    ):
        raise ValueError("Mandatory transport safety gates cannot be disabled")
    return doc


def status(path=None):
    config = load_config(path)
    enabled = config["enabled"] and config["provider"] == "gmail"
    stopped = os.environ.get("MM_EXTERNAL_SEND_DISABLED") == "1"
    return {
        "checked_at": core.now(),
        "mode": "MANUAL_EXACT_APPROVAL" if enabled else "DRAFT_ONLY",
        "provider": config["provider"],
        "enabled": enabled,
        "external_send_allowed": enabled and not stopped,
        "daily_cap": config["daily_cap"],
        "network_send_implementation": enabled,
        "adapter_registered": True,
        "approval_required": True,
        "automatic_sending": False,
        "automatic_retry": False,
        "environment_send_disabled": stopped,
        "reason": "Exact message approval and current recipient/suppression gates required."
        if enabled
        else "Owner transport is disabled.",
    }


def submit(db, message_id, *, expected_content_hash=None, password_loader=None, smtp_factory=None):
    """Canonical explicit single-message entrypoint. No approval or retry override."""
    config = load_config()
    if not config["enabled"] or os.environ.get("MM_EXTERNAL_SEND_DISABLED") == "1":
        raise ValueError("Transport is disabled")
    if (
        not isinstance(expected_content_hash, str)
        or len(expected_content_hash) != 64
        or any(char not in "0123456789abcdef" for char in expected_content_hash)
    ):
        raise ValueError("Exact reviewed content hash required")
    import mm_smtp_live

    return mm_smtp_live.submit(
        db,
        message_id,
        expected_content_hash=expected_content_hash,
        password_loader=password_loader,
        smtp_factory=smtp_factory,
    )


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


def set_owner_policy(*, enabled, daily_cap, actor):
    """Explicit owner configuration action; never approves or sends a message."""
    if (
        type(enabled) is not bool
        or not isinstance(actor, str)
        or not 2 <= len(actor.strip()) <= 120
    ):
        raise ValueError("Explicit owner identity required")
    if (
        type(daily_cap) is not int
        or (enabled and not 1 <= daily_cap <= 10)
        or (not enabled and daily_cap != 0)
    ):
        raise ValueError("Enabled cap must be 1..10; disabled cap must be zero")
    config = {
        "version": 1,
        "enabled": enabled,
        "provider": "gmail" if enabled else "none",
        "daily_cap": daily_cap,
        "requires_exact_approval": True,
        "requires_verified_recipient": True,
        "requires_suppression_check": True,
        "external_send_allowed": enabled,
    }
    state = core.root() / "state"
    state.mkdir(parents=True, exist_ok=True)
    history = state / "transport-policy-history"
    history.mkdir(mode=0o700, exist_ok=True)
    path = state / "transport-policy.json"
    previous = path.read_bytes() if path.exists() and not path.is_symlink() else None
    if path.is_symlink():
        raise ValueError("Owner policy cannot be a symlink")
    if previous is not None:
        saved = history / (uuid.uuid4().hex + ".json")
        with saved.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(previous)
            stream.flush()
            os.fsync(stream.fileno())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=state, prefix=".transport-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(config, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        load_config(temporary)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        "actor": actor.strip(),
        "policy_sha256": core.sha(path.read_bytes()),
        "enabled": enabled,
        "daily_cap": daily_cap,
        "automatic_sending": False,
        "messages_approved": 0,
        "external_messages_sent": 0,
        "changed_at": core.now(),
    }


def submit_owner_test(db, packet_id, *, content_hash, actor):
    """Explicit owner-mailbox diagnostic purpose; never accepts prospect addresses."""
    config = load_config()
    if not config["enabled"] or os.environ.get("MM_EXTERNAL_SEND_DISABLED") == "1":
        raise ValueError("Transport is disabled")
    import mm_smtp_owner_test

    return mm_smtp_owner_test.submit(db, packet_id, content_hash=content_hash, actor=actor)
