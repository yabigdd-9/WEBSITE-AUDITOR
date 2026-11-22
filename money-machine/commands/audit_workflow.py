"""Audit workflow command for mm_operator."""

from __future__ import annotations

import argparse
import sys


def register(subparsers: argparse._SubParsersAction):
    """Register audit workflow command."""
    p = subparsers.add_parser("audit-packet")
    p.add_argument("--case", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--rendered-review")


def handle(a: argparse.Namespace) -> int:
    """Handle audit workflow command."""
    import mm_audit_workflow

    # Pass arguments to mm_audit_workflow.main
    args = ["--case", a.case, "--output", a.output]
    if a.rendered_review:
        args += ["--rendered-review", a.rendered_review]

    return mm_audit_workflow.main(args)