"""Challenger evaluation command for mm_operator."""

from __future__ import annotations

import argparse


def register(subparsers: argparse._SubParsersAction):
    """Register challenger evaluation command."""
    p = subparsers.add_parser("challenger-eval")
    p.add_argument("--golden", required=True)
    p.add_argument("--baseline", required=True)
    p.add_argument("--challenger", required=True)
    p.add_argument("--min-improvement", type=float, default=0.01)


def handle(a: argparse.Namespace) -> dict:
    """Handle challenger evaluation command."""
    import mm_challenger

    return mm_challenger.compare(
        mm_challenger.load_jsonl(a.golden),
        mm_challenger.load_jsonl(a.baseline),
        mm_challenger.load_jsonl(a.challenger),
        a.min_improvement,
    )