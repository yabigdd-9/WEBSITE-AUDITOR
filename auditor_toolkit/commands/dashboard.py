"""Dashboard command implementation."""

from __future__ import annotations

import getpass
from argparse import ArgumentParser, Namespace
from pathlib import Path

from auditor_toolkit.portal import create_app, setup_password

from .base import Command, register_command


class DashboardCommand(Command):
    """Serve the owner dashboard."""

    name = "dashboard"
    help = "Serve the owner dashboard"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--output-root", default="outputs/toolkit")
        parser.add_argument("--set-password", action="store_true")
        parser.add_argument("--port", type=int, default=8080)
        parser.add_argument("--pipeline-db", type=Path, help="Existing private pipeline SQLite database")
        parser.add_argument("--pipeline-postgres", action="store_true", help="Existing private Postgres via server-only WA_POSTGRES_DSN")
        parser.add_argument("--report-archive-root", type=Path, help="Existing private ciphertext archive directory")
        parser.add_argument("--region", default="default", help="Region identifier (default: default)")
        parser.add_argument("--region-config", type=Path, help="Path to region-specific configuration JSON")

    def execute(self, args: Namespace) -> int:
        region_config = None
        if args.region_config:
            import json
            region_config = json.loads(args.region_config.read_text())

        if args.set_password:
            setup_password(
                args.output_root, getpass.getpass("New portal password (12+ characters): ")
            )
            return 0
        import uvicorn

        uvicorn.run(
            create_app(
                args.output_root,
                pipeline_db=args.pipeline_db,
                report_archive_root=args.report_archive_root,
                pipeline_postgres=args.pipeline_postgres,
                region=args.region,
                region_config=region_config,
            ),
            host="127.0.0.1",
            port=args.port,
        )
        return 0


register_command(DashboardCommand())
