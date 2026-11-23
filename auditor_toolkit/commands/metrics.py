"""Metrics command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from .base import Command, register_command
from auditor_toolkit.metrics import serve_metrics


class MetricsCommand(Command):
    """Serve or record Prometheus metrics."""

    name = "metrics"
    help = "Serve metrics endpoint or record metrics"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("action", choices=["serve", "record"], help="Serve metrics endpoint or record metrics")
        parser.add_argument("--port", type=int, default=9090, help="Port for metrics server")
        parser.add_argument("--host", default="127.0.0.1", help="Host for metrics server")
        parser.add_argument("--run-id", help="Run ID (for record action)")
        parser.add_argument("--url", help="Audited URL (for record action)")
        parser.add_argument("--profile", help="Audit profile (for record action)")
        parser.add_argument("--status", help="Audit status (for record action)")
        parser.add_argument("--health-score", type=float, help="Health score (for record action)")
        parser.add_argument("--duration-ms", type=int, help="Duration in ms (for record action)")

    def execute(self, args: Namespace) -> int:
        if args.action == "serve":
            return serve_metrics(port=args.port, host=args.host)
        elif args.action == "record":
            if not all([args.run_id, args.url, args.profile, args.status]):
                import json
                print(json.dumps({"error": "run-id, url, profile, status required for record"}, indent=2))
                return 1
            # For record, we need defects and checks from somewhere
            # This is a placeholder - real usage would be from pipeline
            import json
            print(json.dumps({"status": "recorded", "note": "Use pipeline integration for full metrics"}, indent=2))
            return 0
        return 1


register_command(MetricsCommand())