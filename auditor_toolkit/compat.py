"""Preserve common URL/format/output arguments without running legacy subprocess pipelines."""

import argparse
import json
from pathlib import Path

from .common import atomic_write_text
from .pipeline import AuditOptions, run_audit
from .reporting import render_html_report


def legacy_main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compatibility entrypoint; use wa for advanced options"
    )
    parser.add_argument("url")
    parser.add_argument("--format", choices=["json", "html", "md"], default="json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("outputs/toolkit"))
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--allow-private", action="store_true")
    parser.add_argument("--no-tls", action="store_true")
    args, remaining = parser.parse_known_args(argv)
    if remaining:
        parser.error(
            "Unsupported legacy options: " + " ".join(remaining) + ". Use wa audit --help."
        )
    report = run_audit(
        args.url,
        AuditOptions(
            output_root=args.output_root,
            browser=args.browser,
            allow_private=args.allow_private,
            tls=not args.no_tls,
        ),
    )
    text = json.dumps(report, indent=2)
    if args.format == "html":
        text = render_html_report(report)
    elif args.format == "md":
        text = "# Website audit\n\n```json\n" + text + "\n```\n"
    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 0 if report["status"] == "complete" else 2
