"""Price command for mm_operator."""

from __future__ import annotations

import argparse
from .compat import OFFERS


def register(subparsers: argparse._SubParsersAction):
    """Register price command."""
    p = subparsers.add_parser("price")
    p.add_argument("--problem", choices=list(OFFERS), required=True)
    p.add_argument("--hours-low", type=float)
    p.add_argument("--hours-high", type=float)


def handle(a: argparse.Namespace) -> dict:
    """Handle price command."""
    from mm_operator import pricing

    if (a.hours_low is None) != (a.hours_high is None):
        raise ValueError("Both hour bounds required")

    return pricing(a.problem, [a.hours_low, a.hours_high] if a.hours_low is not None else None)