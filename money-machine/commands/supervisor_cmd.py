"""Supervisor command for mm_operator."""

from __future__ import annotations

import argparse
import sys


def register(subparsers: argparse._SubParsersAction):
    """Register supervisor command."""
    p = subparsers.add_parser("supervisor")
    p.add_argument("action", choices=["start", "stop", "restart", "ensure-running", "status", "health", "logs"])
    p.add_argument("--sleep", type=float, default=5)
    p.add_argument("--tail", type=int, default=50)
    p.add_argument("--timeout", type=float, default=15)


def handle(a: argparse.Namespace) -> dict:
    """Handle supervisor command."""
    # Add supervisor module path
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from supervisor import cli as _sc
    return _sc.COMMANDS[a.action](a)