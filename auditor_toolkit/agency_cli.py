"""CLI adapters for the first two agency deliverables."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .actions import import_report
from .agency_config import get_client, load_config, site_url
from .common import atomic_write_json, atomic_write_text, workspace_path
from .monthly import due_monthly, generate_monthly
from .revenue import calculate_revenue, roi_csv


def add_commands(sub):
    revenue = sub.add_parser("revenue", help="Create a reviewed-input NZD scenario and ROI CSV")
    revenue.add_argument("report", type=Path)
    revenue.add_argument("--config", type=Path, required=True)
    revenue.add_argument("--client", required=True)
    revenue.add_argument("--output-dir", type=Path, default=Path("outputs/revenue-scenarios"))
    monthly = sub.add_parser("monthly", help="Generate monthly reports and unsent email drafts")
    monthly.add_argument("--config", type=Path, required=True)
    target = monthly.add_mutually_exclusive_group()
    target.add_argument("--client")
    target.add_argument("--all", action="store_true")
    monthly.add_argument(
        "--month", help="YYYY-MM; defaults to previous month in configured timezone"
    )
    monthly.add_argument("--output-root", type=Path, default=Path("outputs/toolkit"))
    monthly.add_argument("--html-only", action="store_true")
    monthly.add_argument(
        "--due-preview", action="store_true", help="List due draft jobs; never installs a schedule"
    )


def run_command(args):
    config = load_config(workspace_path(args.config, must_exist=True, file_only=True))
    if args.command == "revenue":
        client = get_client(config, args.client)
        report = import_report(workspace_path(args.report, must_exist=True, file_only=True))
        if site_url(report["url"]) != client["url"] or report.get("profile") != client["profile"]:
            raise ValueError("Report URL/profile does not match the configured client")
        result = calculate_revenue(report, client.get("revenue"))
        import uuid

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        output_dir = workspace_path(args.output_dir)
        directory = workspace_path(Path(client["id"]) / stamp, root=output_dir)
        atomic_write_json(directory / "revenue.json", result)
        atomic_write_text(directory / "roi.csv", roi_csv(result))
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "coverage": result["coverage"],
                    "revenue": str(directory / "revenue.json"),
                    "roi": str(directory / "roi.csv"),
                },
                indent=2,
            )
        )
        return 0 if result["status"] == "scenario" else 2
    output_root = workspace_path(args.output_root)
    if args.due_preview:
        print(
            json.dumps({"mode": "draft", "jobs": due_monthly(output_root, config)}, indent=2)
        )
        return 0
    if not args.client and not args.all:
        raise ValueError("Choose --client ID or --all; clients are never inferred from filenames")
    clients = [get_client(config, args.client)] if args.client else config["clients"]
    reports = []
    for client in clients:
        try:
            result = generate_monthly(
                output_root, config, client["id"], args.month, not args.html_only
            )
            reports.append(result)
        except (ValueError, OSError, KeyError) as exc:
            reports.append({"client_id": client["id"], "status": "error", "reason": str(exc)})
    print(json.dumps(reports, indent=2))
    return 0 if all(r["status"] == "ready" for r in reports) else 2
