"""Health command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from .base import Command, register_command


class HealthCommand(Command):
    """Run health checks."""

    name = "health"
    help = "Run health checks on the system"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--output-root", default="outputs/toolkit", help="Output directory root")
        parser.add_argument("--no-apis", action="store_true", help="Skip external API checks")
        parser.add_argument("--min-free-gb", type=float, default=1.0, help="Minimum free disk space in GB")
        parser.add_argument("--api-timeout", type=float, default=5.0, help="API check timeout in seconds")

    def execute(self, args: Namespace) -> int:
        from auditor_toolkit.runtime.health import run_all_health_checks

        result = run_all_health_checks(
            db_path=Path(args.output_root) / "history.sqlite3",
            disk_path=args.output_root,
            min_free_gb=args.min_free_gb,
            check_apis=not args.no_apis,
            api_timeout=args.api_timeout,
        )
        import json
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "healthy" else 1


register_command(HealthCommand())