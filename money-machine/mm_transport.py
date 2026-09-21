"""Canonical P14 transport boundary.

Current production policy is intentionally preview-only. This module contains no SMTP,
Gmail, HTTP-send, or provider client. A future live adapter must be separately reviewed
and must preserve approval, idempotency, suppression, bounce and receipt gates.
"""
from __future__ import annotations

import json
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
    if doc["provider"] != "none":
        raise ValueError("No live transport provider is approved in v32")
    if doc["enabled"] is not False or doc["external_send_allowed"] is not False:
        raise ValueError("v32 transport must remain disabled")
    if doc["daily_cap"] != 0:
        raise ValueError("Disabled transport daily_cap must be 0")
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
    return {
        "checked_at": core.now(),
        "mode": "DRAFT_ONLY",
        "provider": config["provider"],
        "enabled": False,
        "external_send_allowed": False,
        "daily_cap": 0,
        "network_send_implementation": False,
        "approval_required": True,
        "reason": "No live transport adapter is approved in v32.",
    }


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
