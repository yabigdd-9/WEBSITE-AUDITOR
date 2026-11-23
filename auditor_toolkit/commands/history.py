"""History command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from .base import Command, register_command
from auditor_toolkit.storage import History


class HistoryCommand(Command):
    """List audit history."""

    name = "history"
    help = "List audit history"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--query", default="", help="Search query")
        parser.add_argument("--output-root", default="outputs/toolkit", help="Output directory root")
        parser.add_argument("--retention-preview", type=int, metavar="KEEP_LAST", help="Preview retention (keep last N)")

    def execute(self, args: Namespace) -> int:
        reports = History(args.output_root).list(args.query, 1000)
        if args.retention_preview is not None:
            if args.retention_preview < 1:
                parser.error("Retention must keep at least one run")
                return 1
            import json
            print(
                json.dumps(
                    {
                        "mode": "preview",
                        "candidate_run_ids": [
                            r["run_id"] for r in reports[args.retention_preview :]
                        ],
                        "deleted": False,
                    }
                )
            )
        else:
            import json
            print(json.dumps(reports, indent=2))
        return 0


register_command(HistoryCommand())