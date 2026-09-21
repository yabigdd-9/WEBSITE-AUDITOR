import argparse
import getpass
import importlib.util
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .ai import generate_drafts, verify_model
from .agency_cli import add_commands, run_command
from .pipeline import AuditOptions, run_audit
from .storage import History


def doctor(root, smoke=False):
    root = Path(root)
    result = {
        "interpreter": sys.executable,
        "dependencies": {
            name: importlib.util.find_spec(name) is not None
            for name in ("httpx", "bs4", "dns", "fastapi", "argon2", "playwright", "llama_cpp")
        },
        "model": verify_model(),
        "output_writable": os.access(root if root.exists() else root.parent, os.W_OK),
        "generation": {"status": "not_tested"},
        "browser": {"status": "not_tested"},
    }
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            result["browser"] = {
                "executable": p.chromium.executable_path,
                "installed": Path(p.chromium.executable_path).is_file(),
                "status": "not_launched",
            }
            if smoke:
                browser = p.chromium.launch(headless=True)
                browser.close()
                result["browser"]["status"] = "ok"
    except Exception as exc:
        result["browser"] = {"status": "error", "reason": str(exc)}
    if smoke:
        result["generation"] = generate_drafts(
            {"url": "https://example.com", "defects": []}, enabled=True
        )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(prog="wa")
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("url", nargs="?")
    audit.add_argument("--batch", type=Path, help="Text file with one explicit URL per line")
    audit.add_argument("--concurrency", type=int, default=2)
    audit.add_argument("--output-root", default="outputs/toolkit")
    audit.add_argument("--allow-private", action="store_true")
    audit.add_argument("--browser", action="store_true")
    audit.add_argument(
        "--profile",
        choices=["static", "rendered", "service", "ecommerce", "publishing", "nz"],
        default="static",
    )
    audit.add_argument("--no-tls", action="store_true")
    audit.add_argument("--deep", action="store_true")
    audit.add_argument("--max-pages", type=int, default=10)
    audit.add_argument("--max-depth", type=int, default=2)
    audit.add_argument("--cache", action="store_true")
    audit.add_argument("--ai", action="store_true")
    audit.add_argument("--ai-timeout", type=float, default=120)
    audit.add_argument("--brand", default="Website Auditor")
    audit.add_argument("--hourly-rate-nzd", type=float)
    audit.add_argument("--competitor", action="append", default=[])
    diag = sub.add_parser("doctor")
    diag.add_argument("--smoke", action="store_true")
    diag.add_argument("--output-root", default="outputs/toolkit")
    history = sub.add_parser("history")
    history.add_argument("--query", default="")
    history.add_argument("--output-root", default="outputs/toolkit")
    history.add_argument("--retention-preview", type=int, metavar="KEEP_LAST")
    dashboard = sub.add_parser("dashboard")
    dashboard.add_argument("--output-root", default="outputs/toolkit")
    dashboard.add_argument("--set-password", action="store_true")
    dashboard.add_argument("--port", type=int, default=8080)
    actions = sub.add_parser("actions")
    actions.add_argument("operation", choices=["preview", "cancel"])
    actions.add_argument("report", type=Path)
    actions.add_argument("--output-dir", type=Path, default=Path("outputs/action-previews"))
    add_commands(sub)
    args = parser.parse_args(argv)
    if args.command in {"revenue", "monthly"}:
        try:
            return run_command(args)
        except (ValueError, OSError, KeyError) as exc:
            parser.error(str(exc))

    if args.command == "doctor":
        result = doctor(args.output_root, args.smoke)
        print(json.dumps(result, indent=2))
        return (
            2
            if args.smoke
            and (result["browser"]["status"] != "ok" or result["generation"]["status"] != "ok")
            else 0
        )
    if args.command == "dashboard":
        from .portal import create_app, setup_password

        if args.set_password:
            setup_password(
                args.output_root, getpass.getpass("New portal password (12+ characters): ")
            )
            return 0
        import uvicorn

        uvicorn.run(create_app(args.output_root), host="127.0.0.1", port=args.port)
        return 0
    if args.command == "history":
        reports = History(args.output_root).list(args.query, 1000)
        if args.retention_preview is not None:
            if args.retention_preview < 1:
                parser.error("Retention must keep at least one run")
            print(
                json.dumps(
                    {
                        "mode": "preview",
                        "candidate_run_ids": [
                            r["run_id"] for r in reports[args.retention_preview :]
                        ],
                        "deleted": False,
                    }
                )
            )
        else:
            print(json.dumps(reports, indent=2))
        return 0
    if args.command == "actions":
        from .actions import import_report, preview_report

        report = import_report(args.report)
        directory = args.output_dir / report["run_id"]
        if args.operation == "cancel":
            from .common import atomic_write_text

            atomic_write_text(directory / "CANCELLED", "Cancelled by operator\n")
        print(json.dumps(preview_report(report, directory), indent=2))
        return 0
    if not args.url and not args.batch:
        parser.error("Provide a URL or --batch")
    if not 1 <= args.concurrency <= 4:
        parser.error("Concurrency must be between 1 and 4")
    if args.hourly_rate_nzd is not None and args.hourly_rate_nzd < 0:
        parser.error("Hourly rate must be non-negative")
    options = AuditOptions(
        output_root=Path(args.output_root),
        allow_private=args.allow_private,
        browser=args.browser,
        tls=not args.no_tls,
        profile=args.profile,
        deep=args.deep,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        cache=args.cache,
        ai=args.ai,
        ai_timeout=args.ai_timeout,
        brand=args.brand,
        hourly_rate_nzd=args.hourly_rate_nzd,
    )
    urls = (
        ([args.url] if args.url else [])
        + (
            [line.strip() for line in args.batch.read_text().splitlines() if line.strip()]
            if args.batch
            else []
        )
        + args.competitor
    )
    urls = list(dict.fromkeys(urls))
    if len(urls) > 100:
        parser.error("Maximum batch size is 100 URLs")
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        reports = list(pool.map(lambda url: run_audit(url, options), urls))
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


if __name__ == "__main__":
    raise SystemExit(main())
