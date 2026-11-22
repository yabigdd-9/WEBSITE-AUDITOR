"""Polish status and module status commands for mm_operator."""

from __future__ import annotations

import argparse
import json


def register(subparsers: argparse._SubParsersAction):
    """Register polish/module status commands."""
    for cmd in ("polish-status", "module-status"):
        subparsers.add_parser(cmd)


def handle(a: argparse.Namespace) -> dict:
    """Handle polish/module status commands."""
    from mm_core import root
    import sys

    if a.cmd == "polish-status":
        r = root()
        report = json.loads((r / "reports" / "polish-status.json").read_text())
        report.update(workspace=str(r), python=sys.executable, snapshot_only=True)
        return report
    elif a.cmd == "module-status":
        import mm_module_registry
        return mm_module_registry.status()
    else:
        raise ValueError(f"Unknown command: {a.cmd}")