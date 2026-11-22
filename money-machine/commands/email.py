"""Email commands for mm_operator."""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path


def register(subparsers: argparse._SubParsersAction):
    """Register email commands."""
    # Email tracking/lifecycle
    for cmd in ("email-event", "email-track", "email-reconcile"):
        p = subparsers.add_parser(cmd)
        if cmd == "email-event":
            p.add_argument("--file", required=True)
            p.add_argument("--store")
        elif cmd == "email-track":
            p.add_argument("--store")
        elif cmd == "email-reconcile":
            p.add_argument("message_id")
            p.add_argument("--store")

    for cmd in ("email-intent", "email-intent-result", "email-lifecycle"):
        p = subparsers.add_parser(cmd)
        if cmd == "email-intent":
            p.add_argument("message_id", type=int)
            p.add_argument("--campaign", required=True)
            p.add_argument("--max-attempts", type=int, default=3)
            p.add_argument("--store")
        elif cmd == "email-intent-result":
            p.add_argument("idempotency_key")
            p.add_argument("--status", required=True)
            p.add_argument("--provider-message-id")
            p.add_argument("--error")
            p.add_argument("--store")
        elif cmd == "email-lifecycle":
            p.add_argument("message_id", type=int)
            p.add_argument("--store")

    # Email store
    for cmd in ("email-migrate", "email-status", "email-find", "email-shadow", "email-duplicates", "email-v1", "email-rollback"):
        p = subparsers.add_parser(cmd)
        if cmd == "email-migrate":
            p.add_argument("--backup", required=True)
        elif cmd == "email-status":
            p.add_argument("id", type=int)
            p.add_argument("--json", action="store_true")
        elif cmd == "email-find":
            p.add_argument("id", type=int)
            p.add_argument("--json", action="store_true")
        elif cmd == "email-shadow":
            p.add_argument("--persist", action="store_true")
        elif cmd == "email-v1":
            p.add_argument("id", type=int)


def handle(a: argparse.Namespace) -> dict:
    """Handle email commands."""
    from mm_core import root

    r = root()
    if not r.exists():
        raise ValueError(f"MM_ROOT directory does not exist: {r}")

    # Tracking/lifecycle commands
    if a.cmd in ("email-event", "email-track", "email-reconcile", "email-intent", "email-intent-result", "email-lifecycle"):
        import mm_email_tracking as tracking
        import mm_email_lifecycle as lifecycle

        if a.cmd == "email-event":
            return tracking.record(json.loads(Path(a.file).read_text(encoding="utf-8")), a.store)
        elif a.cmd == "email-track":
            return tracking.summary(a.store)
        elif a.cmd == "email-reconcile":
            return tracking.reconcile(a.message_id, a.store)
        elif a.cmd == "email-intent":
            with contextlib.closing(connect(r / "database" / "money_machine.db")) as d, d:
                return lifecycle.create_intent(d, a.message_id, a.campaign, max_attempts=a.max_attempts, event_store=a.store)
        elif a.cmd == "email-intent-result":
            with contextlib.closing(connect(r / "database" / "money_machine.db")) as d, d:
                return lifecycle.record_result(d, a.idempotency_key, a.status, provider_message_id=a.provider_message_id, error=a.error, event_store=a.store)
        elif a.cmd == "email-lifecycle":
            with contextlib.closing(connect(r / "database" / "money_machine.db")) as d, d:
                return lifecycle.reconstruct(d, a.message_id, event_store=a.store)

    # Store commands
    elif a.cmd.startswith("email-"):
        import mm_email_store as email_store
        import mm_email_cli as email_cli

        readonly = a.cmd in ("email-status", "email-find", "email-duplicates", "email-v1")

        with contextlib.closing(connect(r / "database" / "money_machine.db", readonly=readonly)) as d, d:
            if a.cmd == "email-migrate":
                return email_store.migrate_email(d, a.backup)
            elif a.cmd == "email-status":
                return email_store.status(d, a.id)
            elif a.cmd == "email-find":
                return email_cli.find_one(d, a.id)
            elif a.cmd == "email-shadow":
                return email_cli.shadow(d, a.persist)
            elif a.cmd == "email-duplicates":
                return email_store.duplicate_entities(d)
            elif a.cmd == "email-v1":
                return {
                    "business": dict(business(d, a.id)),
                    "legacy_contacts": [dict(x) for x in d.execute("SELECT address_or_channel, source, last_verified, do_not_contact FROM contacts WHERE business_id=?", (a.id,))],
                    "legacy_captures": [dict(x) for x in d.execute("SELECT recipient, source_url, checked_at, confidence FROM mm_contact_evidence WHERE business_id=?", (a.id,))],
                    "email_status": "UNVERIFIED_LEGACY_VIEW",
                    "outreach_eligible": False,
                    "note": "Historical confidence is a capture-only score; it is not email verification.",
                }
            elif a.cmd == "email-rollback":
                d.executescript((Path(__file__).resolve().parent / "003_email_finder_v2_rollback.sql").read_text())
                return {"mode": "v1_hold", "history_retained": True, "new_approvals_held": True, "external_sends": 0}

    raise ValueError(f"Unknown email command: {a.cmd}")


def business(d, bid):
    """Get business by ID."""
    row = d.execute("SELECT * FROM businesses WHERE id=?", (bid,)).fetchone()
    if not row:
        raise ValueError(f"Business {bid} not found")
    return row