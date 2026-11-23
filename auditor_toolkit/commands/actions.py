"""Actions command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from .base import Command, register_command
from auditor_toolkit.actions import import_report, preview_report
from auditor_toolkit.common import atomic_write_text, workspace_path


class ActionsCommand(Command):
    """Preview or cancel action plans."""

    name = "actions"
    help = "Preview or cancel action plans"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("operation", choices=["preview", "cancel"])
        parser.add_argument("report", type=Path)
        parser.add_argument("--output-dir", type=Path, default=Path("outputs/action-previews"))

    def execute(self, args: Namespace) -> int:
        report = import_report(workspace_path(args.report, must_exist=True, file_only=True))
        output_dir = workspace_path(args.output_dir)
        directory = workspace_path(report["run_id"], root=output_dir)
        if args.operation == "cancel":
            atomic_write_text(workspace_path("CANCELLED", root=directory), "Cancelled by operator\n")
        import json
        print(json.dumps(preview_report(report, directory), indent=2))
        return 0


register_command(ActionsCommand())