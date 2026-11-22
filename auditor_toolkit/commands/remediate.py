"""Remediate command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from auditor_toolkit.commands.base import Command, register_command
from auditor_toolkit.common import workspace_path
from auditor_toolkit.remediation import build_remediation


class RemediateCommand(Command):
    """Build remediation plan."""

    name = "remediate"
    help = "Build remediation plan from audit report"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("report", type=Path)
        parser.add_argument("--output-dir", type=Path, required=True)

    def execute(self, args: Namespace) -> int:
        report_path = workspace_path(args.report, must_exist=True, file_only=True)
        output_dir = workspace_path(args.output_dir)
        import json
        report = json.loads(report_path.read_text())
        result = build_remediation(report, output_dir)
        print(json.dumps(result, indent=2))
        return 0


register_command(RemediateCommand())