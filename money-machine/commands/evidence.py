"""Evidence commands for mm_operator."""

from __future__ import annotations

import argparse
import contextlib


def register(subparsers: argparse._SubParsersAction):
    """Register evidence commands."""
    p = subparsers.add_parser("audit-backfill")
    p.add_argument("--id", type=int, action="append", dest="ids")
    p.add_argument("--no-delay", action="store_true")

    p = subparsers.add_parser("discover-contacts")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--no-delay", action="store_true")


def handle(a: argparse.Namespace) -> dict:
    """Handle evidence commands."""
    import mm_evidence_ops
    from mm_core import connect, root

    r = root()
    if not r.exists():
        raise ValueError(f"MM_ROOT directory does not exist: {r}")

    politeness = 0.0 if a.no_delay else 1.0

    with contextlib.closing(connect(r / "database" / "money_machine.db")) as d, d:
        if a.cmd == "audit-backfill":
            return mm_evidence_ops.audit_backfill(d, ids=a.ids, politeness=politeness)
        elif a.cmd == "discover-contacts":
            return mm_evidence_ops.discover_own_site_contacts(d, a.id, politeness=politeness)

    raise ValueError(f"Unknown evidence command: {a.cmd}")