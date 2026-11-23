"""Transport commands for mm_operator."""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path


def register(subparsers: argparse._SubParsersAction):
    """Register transport commands."""
    for cmd in ("transport-status", "transport-preflight", "transport-send"):
        p = subparsers.add_parser(cmd)
        if cmd in ("transport-preflight", "transport-send"):
            p.add_argument("--packet", required=True)
        if cmd == "transport-send":
            p.add_argument("--execute", action="store_true")


def handle(a: argparse.Namespace) -> dict:
    """Handle transport commands."""
    import mm_transport

    if a.cmd == "transport-send":
        if not a.execute:
            return {"status": "DRY_RUN", "note": "Pass --execute to trigger mock transport."}
        from mm_core import connect, root

        r = root()
        if not r.exists():
            raise ValueError(f"MM_ROOT directory does not exist: {r}")

        with contextlib.closing(connect(r / "database" / "money_machine.db")) as d, d:
            return mm_transport.send_approved(d, int(a.packet))
    elif a.cmd == "transport-status":
        return mm_transport.status()
    elif a.cmd == "transport-preflight":
        return mm_transport.preflight_packet(json.loads(Path(a.packet).read_text()))
    else:
        raise ValueError(f"Unknown transport command: {a.cmd}")