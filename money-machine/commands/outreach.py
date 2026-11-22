"""Outreach commands for mm_operator."""

from __future__ import annotations

import argparse
import contextlib


def register(subparsers: argparse._SubParsersAction):
    """Register outreach commands."""
    p = subparsers.add_parser("outreach-plan")
    p.add_argument("--brief", required=True)

    for cmd in (
        "outreach-audit",
        "outreach-preflight",
        "outreach-dsn",
        "outreach-health",
    ):
        p = subparsers.add_parser(cmd)
        if cmd == "outreach-audit":
            p.add_argument("--packet", required=True)
        elif cmd == "outreach-preflight":
            p.add_argument("id", type=int)
        elif cmd == "outreach-dsn":
            p.add_argument("--eml", required=True)
            p.add_argument("--recipient", required=True)
            p.add_argument("--original-message-id", required=True)


def handle(a: argparse.Namespace) -> dict:
    """Handle outreach commands."""
    import mm_outreach

    from mm_core import connect, root

    r = root()
    if not r.exists():
        raise ValueError(f"MM_ROOT directory does not exist: {r}")

    with contextlib.closing(connect(r / "database" / "money_machine.db", readonly=True)) as d:
        result = mm_outreach.cli(a, d)

    return result


def should_exit_with_error(a: argparse.Namespace, result: dict) -> bool:
    """Check if command should exit with error code."""
    return (
        (a.cmd == "outreach-audit" and not result.get("passed", True))
        or (a.cmd == "outreach-plan" and result.get("planning_holds"))
        or a.cmd == "outreach-preflight"
    )