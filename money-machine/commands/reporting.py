"""Reporting commands for mm_operator."""

from __future__ import annotations

import argparse


def register(subparsers: argparse._SubParsersAction):
    """Register reporting commands."""
    p = subparsers.add_parser("report")
    p.add_argument("granularity", nargs="?", choices=["daily"], default="daily")

    for cmd in ("alerts", "rotate-logs"):
        subparsers.add_parser(cmd)


def handle(a: argparse.Namespace) -> dict:
    """Handle reporting commands."""
    import mm_reporting

    if a.cmd == "report":
        result = mm_reporting.daily_report()
        return {k: result[k] for k in ("report", "delta", "safety_attestation")}
    elif a.cmd == "alerts":
        return mm_reporting.evaluate_alerts()
    elif a.cmd == "rotate-logs":
        result = [r for r in (mm_reporting.rotate_jsonl("metrics.jsonl"), mm_reporting.rotate_jsonl("errors.jsonl")) if r]
        return {"rotated": result}
    else:
        raise ValueError(f"Unknown reporting command: {a.cmd}")