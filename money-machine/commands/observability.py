"""Observability commands for mm_operator."""

from __future__ import annotations

import argparse


def register(subparsers: argparse._SubParsersAction):
    """Register observability commands."""
    for cmd in ("health", "metrics", "queue", "observability-snapshot"):
        subparsers.add_parser(cmd)

    errors = subparsers.add_parser("errors")
    errors.add_argument("--root-causes", "--root-cases", dest="root_causes", action="store_true")

    dl = subparsers.add_parser("dead-letter")
    dl_sub = dl.add_subparsers(dest="dead_letter_action")
    r = dl_sub.add_parser("resolve")
    r.add_argument("--all", action="store_true", required=True)
    r.add_argument("--reason", required=True)


def handle(a: argparse.Namespace) -> dict:
    """Handle observability commands."""
    import mm_observability

    if a.cmd == "errors":
        return mm_observability.errors(show_root_causes=getattr(a, "root_causes", False))
    elif a.cmd == "dead-letter":
        if getattr(a, "dead_letter_action", None) == "resolve":
            from mm_operator import cmd_dead_letter_resolve
            return cmd_dead_letter_resolve(a.reason)
        return mm_observability.dead_letter()
    elif a.cmd == "health":
        return mm_observability.health()
    elif a.cmd == "metrics":
        return mm_observability.metrics()
    elif a.cmd == "queue":
        return mm_observability.queue()
    elif a.cmd == "observability-snapshot":
        return mm_observability.write_snapshots()
    else:
        raise ValueError(f"Unknown observability command: {a.cmd}")