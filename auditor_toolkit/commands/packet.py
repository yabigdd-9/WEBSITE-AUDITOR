"""Packet command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from auditor_toolkit.common import workspace_path
from auditor_toolkit.packet import build_packet

from .base import Command, register_command


class PacketCommand(Command):
    """Build client packet from report, remediation, demo, and quote."""

    name = "packet"
    help = "Build client packet from report, remediation, demo, and quote"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("report", type=Path)
        parser.add_argument("remediation", type=Path)
        parser.add_argument("demo", type=Path)
        parser.add_argument("quote", type=Path)
        parser.add_argument("--output-dir", type=Path, required=True)

    def execute(self, args: Namespace) -> int:
        report_path = workspace_path(args.report, must_exist=True, file_only=True)
        remediation_path = workspace_path(args.remediation, must_exist=True, file_only=True)
        demo_path = workspace_path(args.demo, must_exist=True, file_only=True)
        quote_path = workspace_path(args.quote, must_exist=True, file_only=True)
        output_dir = workspace_path(args.output_dir)
        import json
        report = json.loads(report_path.read_text())
        remediation = json.loads(remediation_path.read_text())
        demo = json.loads(demo_path.read_text())
        quote = json.loads(quote_path.read_text())
        result = build_packet(report, remediation, demo, quote, output_dir)
        print(json.dumps(result, indent=2))
        return 0


register_command(PacketCommand())
