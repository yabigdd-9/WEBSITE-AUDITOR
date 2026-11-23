"""Agent policy check command for mm_operator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def register(subparsers: argparse._SubParsersAction):
    """Register agent policy check command."""
    p = subparsers.add_parser("agent-policy-check")
    p.add_argument("--file", required=True)


def handle(a: argparse.Namespace) -> dict:
    """Handle agent policy check command."""
    import mm_agent_policy

    assignments = json.loads(Path(a.file).read_text())
    return mm_agent_policy.validate_assignments(assignments)