"""Outcomes commands for mm_operator."""

from __future__ import annotations

import argparse
import contextlib


def register(subparsers: argparse._SubParsersAction):
    """Register outcomes commands."""
    for cmd in ("outcomes", "outcome-record"):
        p = subparsers.add_parser(cmd)
        if cmd == "outcome-record":
            p.add_argument("id", type=int)
            p.add_argument("--outcome", required=True)
            p.add_argument("--evidence", required=True)
            p.add_argument("--sha256", required=True)
            p.add_argument("--actor", required=True)
            p.add_argument("--note", default="")


def handle(a: argparse.Namespace) -> dict:
    """Handle outcomes commands."""
    import mm_outcomes

    from mm_core import connect, root

    r = root()
    if not r.exists():
        raise ValueError(f"MM_ROOT directory does not exist: {r}")

    readonly = a.cmd == "outcomes"

    with contextlib.closing(connect(r / "database" / "money_machine.db", readonly=readonly)) as d:
        if a.cmd == "outcomes":
            return mm_outcomes.summary(d)
        else:
            with d:
                return mm_outcomes.record(d, a.id, a.outcome, a.evidence, a.sha256, a.actor, a.note)