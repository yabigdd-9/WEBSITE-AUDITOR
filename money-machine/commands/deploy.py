"""Deploy check command for mm_operator."""

from __future__ import annotations

import argparse
import sys


def register(subparsers: argparse._SubParsersAction):
    """Register deploy check command."""
    p = subparsers.add_parser("deploy-check")
    p.add_argument("--candidate")
    p.add_argument("--execute", action="store_true")


def handle(a: argparse.Namespace) -> dict:
    """Handle deploy check command."""
    if not a.execute:
        return {
            "status": "DRY_RUN",
            "required_gates": list(__import__("mm_deploy").REQUIRED_GATES),
            "note": "Pass --execute to run gates. Deployment is local-workstation only.",
        }

    import mm_deploy
    from mm_core import connect, root

    r = root()
    if not r.exists():
        raise ValueError(f"MM_ROOT directory does not exist: {r}")

    with contextlib.closing(connect(r / "database" / "money_machine.db")) as d, d:
        tests = [
            "test_acceptance",
            "test_email_finder",
            "test_email_hardening",
            "test_email_integration",
            "test_lead_qualifier",
            "test_outreach",
            "test_pipeline",
            "test_polish",
        ]
        return mm_deploy.deploy(d, sys.executable, tests, a.candidate)


import contextlib
from mm_core import connect, root