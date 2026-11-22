"""Smart reply command for mm_operator."""

from __future__ import annotations

import argparse


def register(subparsers: argparse._SubParsersAction):
    """Register smart reply command."""
    p = subparsers.add_parser("smart-reply")
    p.add_argument("id", type=int)


def handle(a: argparse.Namespace) -> dict:
    """Handle smart reply command."""
    import mm_smart_reply

    from mm_core import connect, root

    r = root()
    if not r.exists():
        raise ValueError(f"MM_ROOT directory does not exist: {r}")

    with contextlib.closing(connect(r / "database" / "money_machine.db")) as d, d:
        return mm_smart_reply.assistant_response(a.id, d)


import contextlib
from mm_core import connect, root