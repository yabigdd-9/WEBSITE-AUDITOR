"""Audit command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from auditor_toolkit.commands.base import Command, register_command
from auditor_toolkit.common import workspace_path
from auditor_toolkit.pipeline import AuditOptions, run_audit


class AuditCommand(Command):
    """Run website audits."""

    name = "audit"
    help = "Run website audit on one or more URLs"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("url", nargs="?", help="URL to audit")
        parser.add_argument("--batch", type=Path, help="Text file with one explicit URL per line")
        parser.add_argument("--concurrency", type=int, default=2, help="Number of concurrent audits (1-4)")
        parser.add_argument("--output-root", default="outputs/toolkit", help="Output directory root")
        parser.add_argument("--allow-private", action="store_true", help="Allow auditing private/non-global IP addresses")
        parser.add_argument("--browser", action="store_true", help="Enable browser-based checks")
        parser.add_argument(
            "--profile",
            choices=["static", "rendered", "service", "ecommerce", "publishing", "nz"],
            default="static",
            help="Audit profile",
        )
        parser.add_argument("--no-tls", action="store_true", help="Disable TLS certificate inspection")
        parser.add_argument("--deep", action="store_true", help="Enable deep checks (link validation, DNS, crawl)")
        parser.add_argument("--external-tools", action="store_true", help="Require installed local Lighthouse + Lychee checks")
        parser.add_argument("--max-bytes", type=int, default=2_000_000, help="Maximum decoded bytes per HTTP response (1024 to 10000000)")
        parser.add_argument("--max-pages", type=int, default=10, help="Maximum pages to crawl (1-100)")
        parser.add_argument("--max-depth", type=int, default=2, help="Maximum crawl depth (0-5)")
        parser.add_argument("--cache", action="store_true", help="Enable HTTP response caching")
        parser.add_argument("--ai", action="store_true", help="Enable AI-powered draft generation")
        parser.add_argument("--ai-timeout", type=float, default=120, help="Timeout for AI generation in seconds")
        parser.add_argument("--brand", default="Website Auditor", help="Brand name for report headers")
        parser.add_argument("--hourly-rate-nzd", type=float, help="Hourly rate in NZD for cost estimates")
        parser.add_argument("--competitor", action="append", default=[], help="Competitor URL to audit (can be repeated)")

    def execute(self, args: Namespace) -> int:
        if not args.url and not args.batch:
            parser.error("Provide a URL or --batch")
            return 1
        if not 1 <= args.concurrency <= 4:
            parser.error("Concurrency must be between 1 and 4")
            return 1
        if args.hourly_rate_nzd is not None and args.hourly_rate_nzd < 0:
            parser.error("Hourly rate must be non-negative")
            return 1

        batch_path = workspace_path(args.batch, must_exist=True, file_only=True) if args.batch else None
        options = AuditOptions(
            output_root=Path(args.output_root),
            allow_private=args.allow_private,
            browser=args.browser,
            tls=not args.no_tls,
            profile=args.profile,
            deep=args.deep,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            max_bytes=args.max_bytes,
            cache=args.cache,
            ai=args.ai,
            ai_timeout=args.ai_timeout,
            brand=args.brand,
            hourly_rate_nzd=args.hourly_rate_nzd,
            external_tools=args.external_tools,
        )
        urls = (
            ([args.url] if args.url else [])
            + (
                [line.strip() for line in batch_path.read_text().splitlines() if line.strip()]
                if batch_path
                else []
            )
            + args.competitor
        )
        urls = list(dict.fromkeys(urls))
        if len(urls) > 100:
            parser.error("Maximum batch size is 100 URLs")
            return 1

        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            reports = list(pool.map(lambda url: run_audit(url, options), urls))

        import json
        print(
            json.dumps(
                [
                    {
                        "url": r["url"],
                        "run_id": r["run_id"],
                        "status": r["status"],
                        "health_score": r["health_score"],
                        "artifacts": r["artifacts"],
                    }
                    for r in reports
                ],
                indent=2,
            )
        )
        return 0 if all(r["status"] == "complete" for r in reports) else 2


register_command(AuditCommand())