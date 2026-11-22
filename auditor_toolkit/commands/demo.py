"""Demo command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from auditor_toolkit.commands.base import Command, register_command
from auditor_toolkit.common import workspace_path
from auditor_toolkit.demo import build_demo


class DemoCommand(Command):
    """Build demo from report and remediation."""

    name = "demo"
    help = "Build demo from report and remediation"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("report", type=Path)
        parser.add_argument("remediation", type=Path)
        parser.add_argument("--output-dir", type=Path, required=True)
        parser.add_argument("--render", action="store_true")

    def execute(self, args: Namespace) -> int:
        report_path = workspace_path(args.report, must_exist=True, file_only=True)
        remediation_path = workspace_path(args.remediation, must_exist=True, file_only=True)
        output_dir = workspace_path(args.output_dir)
        import json
        report = json.loads(report_path.read_text())
        remediation = json.loads(remediation_path.read_text())
        result = build_demo(
            report,
            remediation,
            output_dir,
            render=args.render,
            report_path=report_path,
        )
        print(json.dumps(result, indent=2))
        return 0


register_command(DemoCommand())