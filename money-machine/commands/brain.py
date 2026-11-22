"""Brain commands for mm_operator."""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path


def register(subparsers: argparse._SubParsersAction):
    """Register brain commands."""
    for cmd in ("bottlenecks", "schedule", "brain", "decisions", "decision", "brain-replay", "brain-shadow", "db-check", "safe-mode"):
        p = subparsers.add_parser(cmd)
        if cmd in ("schedule", "brain"):
            p.add_argument("--limit", type=int, default=10)
        elif cmd == "decisions":
            p.add_argument("--business", type=int)
            p.add_argument("--limit", type=int, default=100)
        elif cmd == "decision":
            p.add_argument("decision_id")
        elif cmd == "brain-replay":
            p.add_argument("decision_id")
        elif cmd == "brain-shadow":
            p.add_argument("--current", required=True)
            p.add_argument("--challenger", required=True)
        elif cmd == "safe-mode":
            p.add_argument("action", choices=["on", "off", "status"])


def handle(a: argparse.Namespace) -> dict:
    """Handle brain commands."""
    import mm_brain
    from mm_core import connect, root

    r = root()
    if not r.exists():
        raise ValueError(f"MM_ROOT directory does not exist: {r}")

    if a.cmd == "safe-mode":
        return mm_brain.safe_mode(True if a.action == "on" else False if a.action == "off" else None)
    elif a.cmd == "brain-shadow":
        return mm_brain.shadow(json.loads(Path(a.current).read_text()), json.loads(Path(a.challenger).read_text()))

    readonly = a.cmd in ("bottlenecks", "schedule", "brain", "decisions", "decision", "brain-replay", "db-check")

    with contextlib.closing(connect(r / "database" / "money_machine.db", readonly=readonly)) as d:
        if a.cmd == "bottlenecks":
            return mm_brain.bottlenecks(d)
        elif a.cmd in ("schedule", "brain"):
            return {"items": mm_brain.recommend(d, a.limit)}
        elif a.cmd == "decisions":
            return {"decisions": mm_brain.ledger(a.business, a.limit)}
        elif a.cmd == "decision":
            result = next((row for row in mm_brain.ledger() if row.get("decision_id") == a.decision_id), None)
            return result or {"error": "Decision not found"}
        elif a.cmd == "brain-replay":
            return mm_brain.replay(a.decision_id)
        elif a.cmd == "db-check":
            return mm_brain.db_check(d)

    raise ValueError(f"Unknown brain command: {a.cmd}")