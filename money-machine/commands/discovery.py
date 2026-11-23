"""Discovery commands for mm_operator."""

from __future__ import annotations

import argparse
import contextlib


def register(subparsers: argparse._SubParsersAction):
    """Register discovery commands."""
    p = subparsers.add_parser("discover-import")
    p.add_argument("--file", required=True)
    p.add_argument("--region", default="")
    p.add_argument("--source", default="import")
    p.add_argument("--dry-run", action="store_true")

    p = subparsers.add_parser("discover-search")
    p.add_argument("--query", required=True)
    p.add_argument("--region", required=True)
    p.add_argument("--endpoint", default="http://127.0.0.1:8888")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--dry-run", action="store_true")


def handle(a: argparse.Namespace) -> dict:
    """Handle discovery commands."""
    import mm_discovery
    from mm_core import connect, root

    r = root()
    if not r.exists():
        raise ValueError(f"MM_ROOT directory does not exist: {r}")

    if a.cmd == "discover-import":
        candidates, rejected = mm_discovery.read_candidates(a.file, a.region, a.source)
    else:
        try:
            candidates = mm_discovery.searxng_candidates(a.query, a.region, a.endpoint, a.limit)
        except mm_discovery.SearchBlocked as e:
            return {
                "query": a.query,
                "region": a.region,
                "dry_run": a.dry_run,
                "candidates": [],
                "blocked": {"code": e.code, "endpoint": e.endpoint, "detail": e.detail},
                "note": "Search lane is blocked in this environment; run on a host with a local SearXNG for ranked candidates.",
            }
        rejected = []

    with contextlib.closing(connect(r / "database" / "money_machine.db")) as d, d:
        result = mm_discovery.ingest(d, candidates, actor="mm-" + a.cmd, dry_run=a.dry_run)

    result["source_rejections"] = rejected
    result["external_sends"] = 0
    return result