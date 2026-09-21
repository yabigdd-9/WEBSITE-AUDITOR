import argparse
import getpass
import importlib.util
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .ai import generate_drafts, verify_model
from .pipeline import AuditOptions, run_audit
from .storage import History
from website_auditor.monitoring.watchdog import Watchdog


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

    watchdog = sub.add_parser("watchdog")
    watchdog.add_argument("domain", help="Domain to check for regressions")
    watchdog.add_argument("--output-root", default="outputs/toolkit", help="Root directory for audit outputs")
    watchdog.add_argument("--alert", action="store_true", help="Send alert if regressions are detected")
    secret = sub.add_parser("secret")
    secret_sub = secret.add_subparsers(dest="secret_command", required=True)
    # set
    secret_set = secret_sub.add_parser("set", help="Store a secret in the keychain")
    secret_set.add_argument("name", help="Secret name")
    secret_set.add_argument("value", help="Secret value")
    # get
    secret_get = secret_sub.add_parser("get", help="Retrieve a secret from the keychain")
    secret_get.add_argument("name", help="Secret name")
    # list
    secret_list = secret_sub.add_parser("list", help="List secret names")
    # delete
    secret_delete = secret_sub.add_parser("delete", help="Delete a secret from the keychain")
    secret_delete.add_argument("name", help="Secret name")

    eval = sub.add_parser("eval")
    eval.add_argument("--config", default="money-machine/promptfoo.yaml", help="Path to promptfoo config")
    eval.add_argument("--quiet", action="store_true", help="Quiet mode")

    dashboard = sub.add_parser("dashboard")
    dashboard.add_argument("--output-root", default="outputs/toolkit")
    dashboard.add_argument("--set-password", action="store_true")
    dashboard.add_argument("--port", type=int, default=8080)
    actions = sub.add_parser("actions")
    actions.add_argument("operation", choices=["preview", "cancel"])
    actions.add_argument("report", type=Path)
    actions.add_argument("--output-dir", type=Path, default=Path("outputs/action-previews"))
    args = parser.parse_args(argv)
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

    if args.command == "watchdog":
        root = Path(args.output_root)
        history = History(root)
        reports = history.list(args.domain, 1)
        if not reports:
            print(f"No audit found for domain {args.domain}")
            return 1
        latest = reports[0]
        defects = latest.get("defects", [])
        wd = Watchdog(output_root=root)
        result = wd.detect_regressions(args.domain, defects)
        wd.take_snapshot(args.domain, defects)
        print(json.dumps(result, indent=2))
        if args.alert and result.get("regressions"):
            alert_result = wd.send_alert(args.domain, result["regressions"])
            print(json.dumps(alert_result, indent=2))
        return 1 if result.get("regressions") else 0

    if args.command == "secret":
        root = Path(args.output_root)
        if args.secret_command == "set":
            subprocess.run([
                "security", "add-generic-password",
                "-s", "website-auditor",
                "-a", args.name,
                "-w", args.value,
                "-U"
            ], check=True)
            print(f"Secret '{args.name}' stored.")
        elif args.secret_command == "get":
            try:
                result = subprocess.run([
                    "security", "find-generic-password",
                    "-s", "website-auditor",
                    "-a", args.name,
                    "-w"
                ], capture_output=True, text=True, check=True)
                print(result.stdout.strip())
            except subprocess.CalledProcessError as e:
                print(f"Error: Secret '{args.name}' not found.", file=sys.stderr)
                return 1
        elif args.secret_command == "list":
            # List all secrets for the service
            try:
                result = subprocess.run([
                    "security", "find-generic-password", "-s", "website-auditor", "-g"
                ], capture_output=True, text=True, check=True)
                # The `-g` flag gets the password, but we don't want that for listing.
                # Instead, we can try to get the list of accounts by parsing the output of
                # `security find-generic-password -s website-auditor` without `-g` and `-w`.
                # However, the output is intended for humans. For simplicity, we'll just note
                # that listing is not implemented in this version.
                print("Listing secrets is not yet implemented in this version.")
            except subprocess.CalledProcessError as e:
                print("No secrets found.")
        elif args.secret_command == "delete":
            subprocess.run([
                "security", "delete-generic-password",
                "-s", "website-auditor",
                "-a", args.name
            ], check=True)
            print(f"Secret '{args.name}' deleted.")
        else:
            parser.error("Invalid secret command")
        return 0

    if args.command == "eval":
        cmd = ["promptfoo", "eval", "--config", args.config]
        if args.quiet:
            cmd.append("--quiet")
        subprocess.run(cmd, check=True)
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
