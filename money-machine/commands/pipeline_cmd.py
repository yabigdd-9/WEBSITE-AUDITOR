"""Pipeline commands for mm_operator."""

from __future__ import annotations

import argparse
import contextlib
import json


def register(subparsers: argparse._SubParsersAction):
    """Register pipeline commands."""
    for cmd in ("pipeline-run", "pipeline-status", "pipeline-enqueue", "pipeline-requeue", "pipeline-transition", "pipeline-health"):
        p = subparsers.add_parser(cmd)
        if cmd == "pipeline-run":
            p.add_argument("--worker", action="append")
            p.add_argument("--limit", type=int, default=1)
            p.add_argument("--sleep", type=float, default=60)
            p.add_argument("--cycles", type=int, default=0)
            p.add_argument("--report-every", type=int, default=10)
        elif cmd == "pipeline-enqueue":
            p.add_argument("id", type=int)
            p.add_argument("--state", default="DISCOVERED")
        elif cmd == "pipeline-requeue":
            p.add_argument("id", type=int)
            p.add_argument("--reason", required=True)
            p.add_argument("--actor", default="operator")
        elif cmd == "pipeline-transition":
            p.add_argument("id", type=int)
            p.add_argument("--to", required=True)
            p.add_argument("--actor", required=True)
            p.add_argument("--reason", required=True)


def handle(a: argparse.Namespace) -> dict:
    """Handle pipeline commands."""
    import mm_pipeline
    import mm_approval
    import mm_model_router
    import mm_workers
    from mm_core import connect, root

    r = root()
    if not r.exists():
        raise ValueError(f"MM_ROOT directory does not exist: {r}")

    readonly = a.cmd in ("approval-check",)

    with contextlib.closing(connect(r / "database" / "money_machine.db", readonly=readonly)) as d, d:
        mm_pipeline.migrate(d)
        mm_approval.migrate(d)

        if a.cmd in ("pipeline-status", "pipeline-health"):
            return mm_pipeline.health(d)
        elif a.cmd == "pipeline-enqueue":
            return dict(mm_pipeline.enqueue(d, a.id, a.state))
        elif a.cmd == "pipeline-requeue":
            return dict(mm_pipeline.requeue_permanent_failure(d, a.id, a.reason, a.actor))
        elif a.cmd == "pipeline-transition":
            return dict(mm_pipeline.transition(d, a.id, a.to, a.actor, a.reason))
        elif a.cmd == "pipeline-run":
            names = getattr(a, "worker", None) or list(mm_workers.WORKERS)
            workers = [
                mm_pipeline.Worker(
                    "worker-" + name,
                    *mm_workers.WORKERS[name],
                    lease_seconds=int(getattr(a, "lease", 300)),
                )
                for name in sorted(names)
                if name in mm_workers.WORKERS
            ]
            cycles = mm_pipeline.run_pipelineloop(
                d,
                workers,
                sleep_seconds=float(getattr(a, "sleep", 60)),
                max_cycles=int(getattr(a, "cycles", 0) or 0),
                report_every=int(getattr(a, "report_every", 10)),
            )
            return {"cycles": cycles, "workers": sorted(names)}

    raise ValueError(f"Unknown pipeline command: {a.cmd}")


import contextlib
from mm_core import connect, root