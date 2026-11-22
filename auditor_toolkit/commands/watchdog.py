"""Watchdog command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
import os
from pathlib import Path

from auditor_toolkit.commands.base import Command, register_command
from auditor_toolkit.monitoring.watchdog import Watchdog
from auditor_toolkit.storage import History


class WatchdogCommand(Command):
    """Check for regressions."""

    name = "watchdog"
    help = "Check for regressions on a domain"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("domain", help="Domain to check for regressions")
        parser.add_argument("--output-root", default="outputs/toolkit", help="Root directory for audit outputs")
        parser.add_argument("--alert", action="store_true", help="Send alert if regressions are detected")
        parser.add_argument("--webhook-url", default=None, help="Override ALERT_WEBHOOK_URL for alert delivery")

    def execute(self, args: Namespace) -> int:
        root = Path(args.output_root)
        history = History(root)
        reports = history.list(args.domain, 1)
        if not reports:
            print(f"No audit found for domain {args.domain}")
            return 1
        latest = reports[0]
        defects = latest.get("defects", [])
        webhook = args.webhook_url or os.getenv("ALERT_WEBHOOK_URL", "")
        wd = Watchdog(output_root=root, webhook_url=webhook)
        result = wd.detect_regressions(args.domain, defects)
        wd.take_snapshot(args.domain, defects)
        import json
        print(json.dumps(result, indent=2))
        if args.alert and result.get("regressions"):
            if not webhook:
                print(json.dumps({"status": "skipped", "reason": "--alert requires --webhook-url or ALERT_WEBHOOK_URL"}, indent=2))
            else:
                alert_result = wd.send_alert(args.domain, result["regressions"])
                print(json.dumps(alert_result, indent=2))
        return 1 if result.get("regressions") else 0


register_command(WatchdogCommand())