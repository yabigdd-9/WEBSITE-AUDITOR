"""Quote command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from auditor_toolkit.common import atomic_write_json, workspace_path
from auditor_toolkit.quote import calculate_quote

from .base import Command, register_command


class QuoteCommand(Command):
    """Calculate quote from audit report."""

    name = "quote"
    help = "Calculate quote from audit report"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("report", type=Path)
        parser.add_argument("--hourly-rate-nzd", type=float, required=True)
        parser.add_argument("--output", type=Path)

    def execute(self, args: Namespace) -> int:
        report_path = workspace_path(args.report, must_exist=True, file_only=True)
        import json
        report = json.loads(report_path.read_text())
        result = calculate_quote(report, args.hourly_rate_nzd)
        if args.output:
            atomic_write_json(workspace_path(args.output), result)
        print(json.dumps(result, indent=2))
        return 0


register_command(QuoteCommand())
