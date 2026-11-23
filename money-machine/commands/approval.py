"""Approval commands for mm_operator."""

from __future__ import annotations

import argparse
import contextlib


def register(subparsers: argparse._SubParsersAction):
    """Register approval commands."""
    p = subparsers.add_parser("approval-check")
    p.add_argument("id", type=int)

    p = subparsers.add_parser("approval-decide")
    p.add_argument("approval_id", type=int)
    p.add_argument("--actor", required=True)
    p.add_argument("--reason", required=True)


def handle(a: argparse.Namespace) -> dict:
    """Handle approval commands."""
    import mm_approval
    from mm_core import connect, root

    r = root()
    if not r.exists():
        raise ValueError(f"MM_ROOT directory does not exist: {r}")

    readonly = a.cmd == "approval-check"

    with contextlib.closing(connect(r / "database" / "money_machine.db", readonly=readonly)) as d, d:
        mm_approval.migrate(d)
        if a.cmd == "approval-check":
            return mm_approval.evaluate(d, a.id)
        elif a.cmd == "approval-decide":
            return mm_approval.decide(d, a.approval_id, a.actor, a.reason)

    raise ValueError(f"Unknown approval command: {a.cmd}")