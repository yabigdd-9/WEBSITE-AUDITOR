"""Model commands for mm_operator."""

from __future__ import annotations

import argparse


def register(subparsers: argparse._SubParsersAction):
    """Register model commands."""
    for cmd in ("model-routes", "model-plan"):
        p = subparsers.add_parser(cmd)
        if cmd == "model-plan":
            p.add_argument("--purpose", required=True)


def handle(a: argparse.Namespace) -> dict:
    """Handle model commands."""
    if a.cmd == "model-routes":
        import mm_model_router
        return {"routes": mm_model_router.routes_report(), "paid_allowed": False, "max_cost_usd": 0, "fallback": "DEFER"}
    elif a.cmd == "model-plan":
        import mm_model_router
        from mm_core import connect, root

        r = root()
        if not r.exists():
            raise ValueError(f"MM_ROOT directory does not exist: {r}")

        with contextlib.closing(connect(r / "database" / "money_machine.db")) as d:
            return mm_model_router.plan(d, a.purpose)

    raise ValueError(f"Unknown model command: {a.cmd}")


import contextlib