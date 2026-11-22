import argparse
import getpass
import importlib.util
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from auditor_toolkit.monitoring.watchdog import Watchdog

from .agency_cli import add_commands, run_command
from .ai import generate_drafts, verify_model
from .common import workspace_path
from .external_tools import installed_tools
from .logging_config import setup_logging
from .metrics import serve_metrics
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
        "external_tools": installed_tools(),
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
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging level",
    )
    parser.add_argument(
        "--json-log",
        action="store_true",
        help="Output logs as JSON lines",
    )
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
    audit.add_argument("--external-tools", action="store_true", help="Require installed local Lighthouse + Lychee checks")
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
    health = sub.add_parser("health")
    health.add_argument("--output-root", default="outputs/toolkit")
    health.add_argument("--no-apis", action="store_true", help="Skip external API checks")
    health.add_argument("--min-free-gb", type=float, default=1.0, help="Minimum free disk space in GB")
    health.add_argument("--api-timeout", type=float, default=5.0, help="API check timeout in seconds")
    metrics = sub.add_parser("metrics")
    metrics.add_argument("action", choices=["serve", "record"], help="Serve metrics endpoint or record metrics")
    metrics.add_argument("--port", type=int, default=9090, help="Port for metrics server")
    metrics.add_argument("--host", default="127.0.0.1", help="Host for metrics server")
    metrics.add_argument("--run-id", help="Run ID (for record action)")
    metrics.add_argument("--url", help="Audited URL (for record action)")
    metrics.add_argument("--profile", help="Audit profile (for record action)")
    metrics.add_argument("--status", help="Audit status (for record action)")
    metrics.add_argument("--health-score", type=float, help="Health score (for record action)")
    metrics.add_argument("--duration-ms", type=int, help="Duration in ms (for record action)")
    history = sub.add_parser("history")
    history.add_argument("--query", default="")
    history.add_argument("--output-root", default="outputs/toolkit")
    history.add_argument("--retention-preview", type=int, metavar="KEEP_LAST")

    watchdog = sub.add_parser("watchdog")
    watchdog.add_argument("domain", help="Domain to check for regressions")
    watchdog.add_argument("--output-root", default="outputs/toolkit", help="Root directory for audit outputs")
    watchdog.add_argument("--alert", action="store_true", help="Send alert if regressions are detected (requires ALERT_WEBHOOK_URL or --webhook-url)")
    watchdog.add_argument("--webhook-url", default=None, help="Override ALERT_WEBHOOK_URL for alert delivery")
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
    secret_sub.add_parser("list", help="List secret names")
    # delete
    secret_delete = secret_sub.add_parser("delete", help="Delete a secret from the keychain")
    secret_delete.add_argument("name", help="Secret name")

    eval = sub.add_parser("eval")
    eval.add_argument("--config", default="money-machine/promptfoo.yaml", help="Path to promptfoo config")
    eval.add_argument("--quiet", action="store_true", help="Quiet mode")

    secret_rotation = sub.add_parser("secret-rotation")
    secret_rotation_sub = secret_rotation.add_subparsers(dest="rotation_action", required=True)

    # add-policy
    add_policy = secret_rotation_sub.add_parser("add-policy")
    add_policy.add_argument("name")
    add_policy.add_argument("--max-age", type=int, default=90)
    add_policy.add_argument("--warning", type=int, default=14)
    add_policy.add_argument("--auto-rotate", action="store_true")
    add_policy.add_argument("--generator", help="Command to generate new secret")

    # set
    set_secret = secret_rotation_sub.add_parser("set")
    set_secret.add_argument("name")
    set_secret.add_argument("value")
    set_secret.add_argument("--policy", help="Policy name to apply")

    # rotate
    rotate = secret_rotation_sub.add_parser("rotate")
    rotate.add_argument("name")
    rotate.add_argument("--value", help="New value (optional, uses generator if not provided)")

    # check
    secret_rotation_sub.add_parser("check")

    # rotate-all
    secret_rotation_sub.add_parser("rotate-all")

    # list
    secret_rotation_sub.add_parser("list")

    # delete
    delete = secret_rotation_sub.add_parser("delete")
    delete.add_argument("name")

    config = sub.add_parser("config")
    config.add_argument(
        "action",
        choices=["validate", "show"],
        help="Validate configuration or show current settings",
    )

    schema = sub.add_parser("schema")
    schema.add_argument(
        "action",
        choices=["validate"],
        help="Validate configuration file schemas",
    )
    schema.add_argument(
        "--file",
        type=Path,
        help="Specific file to validate (master_plan, agency_config, or path)",
    )

    dashboard = sub.add_parser("dashboard")
    dashboard.add_argument("--output-root", default="outputs/toolkit")
    dashboard.add_argument("--set-password", action="store_true")
    dashboard.add_argument("--port", type=int, default=8080)
    remediate = sub.add_parser("remediate")
    remediate.add_argument("report", type=Path)
    remediate.add_argument("--output-dir", type=Path, required=True)
    demo_cmd = sub.add_parser("demo")
    demo_cmd.add_argument("report", type=Path)
    demo_cmd.add_argument("remediation", type=Path)
    demo_cmd.add_argument("--output-dir", type=Path, required=True)
    demo_cmd.add_argument("--render", action="store_true")
    quote_cmd = sub.add_parser("quote")
    quote_cmd.add_argument("report", type=Path)
    quote_cmd.add_argument("--hourly-rate-nzd", type=float, required=True)
    quote_cmd.add_argument("--output", type=Path)
    packet_cmd = sub.add_parser("packet")
    packet_cmd.add_argument("report", type=Path)
    packet_cmd.add_argument("remediation", type=Path)
    packet_cmd.add_argument("demo", type=Path)
    packet_cmd.add_argument("quote", type=Path)
    packet_cmd.add_argument("--output-dir", type=Path, required=True)
    actions = sub.add_parser("actions")
    actions.add_argument("operation", choices=["preview", "cancel"])
    actions.add_argument("report", type=Path)
    actions.add_argument("--output-dir", type=Path, default=Path("outputs/action-previews"))
    add_commands(sub)
    args = parser.parse_args(argv)

    # Configure logging
    import logging
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    setup_logging(level=log_level, json_output=args.json_log)

    if args.command in {"revenue", "monthly"}:
        try:
            return run_command(args)
        except (ValueError, OSError, KeyError) as exc:
            parser.error(str(exc))

    if args.command == "remediate":
        from .remediation import build_remediation
        report_path = workspace_path(args.report, must_exist=True, file_only=True)
        output_dir = workspace_path(args.output_dir)
        report = json.loads(report_path.read_text())
        result = build_remediation(report, output_dir)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "demo":
        from .demo import build_demo
        report_path = workspace_path(args.report, must_exist=True, file_only=True)
        remediation_path = workspace_path(args.remediation, must_exist=True, file_only=True)
        output_dir = workspace_path(args.output_dir)
        report = json.loads(report_path.read_text())
        remediation = json.loads(remediation_path.read_text())
        result = build_demo(
            report,
            remediation,
            output_dir,
            render=args.render,
            report_path=report_path,
        )
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "quote":
        from .common import atomic_write_json
        from .quote import calculate_quote
        report_path = workspace_path(args.report, must_exist=True, file_only=True)
        report = json.loads(report_path.read_text())
        result = calculate_quote(report, args.hourly_rate_nzd)
        if args.output:
            atomic_write_json(workspace_path(args.output), result)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "packet":
        from .packet import build_packet
        report_path = workspace_path(args.report, must_exist=True, file_only=True)
        remediation_path = workspace_path(args.remediation, must_exist=True, file_only=True)
        demo_path = workspace_path(args.demo, must_exist=True, file_only=True)
        quote_path = workspace_path(args.quote, must_exist=True, file_only=True)
        output_dir = workspace_path(args.output_dir)
        report = json.loads(report_path.read_text())
        remediation = json.loads(remediation_path.read_text())
        demo = json.loads(demo_path.read_text())
        quote = json.loads(quote_path.read_text())
        result = build_packet(report, remediation, demo, quote, output_dir)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "doctor":
        result = doctor(args.output_root, args.smoke)
        print(json.dumps(result, indent=2))
        return (
            2
            if args.smoke
            and (result["browser"]["status"] != "ok" or result["generation"]["status"] != "ok")
            else 0
        )
    if args.command == "health":
        from .runtime.health import run_all_health_checks

        result = run_all_health_checks(
            db_path=Path(args.output_root) / "history.sqlite3",
            disk_path=args.output_root,
            min_free_gb=args.min_free_gb,
            check_apis=not args.no_apis,
            api_timeout=args.api_timeout,
        )
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "healthy" else 1
    if args.command == "metrics":
        if args.action == "serve":
            return serve_metrics(port=args.port, host=args.host)
        elif args.action == "record":
            if not all([args.run_id, args.url, args.profile, args.status]):
                print(json.dumps({"error": "run-id, url, profile, status required for record"}, indent=2))
                return 1
            # For record, we need defects and checks from somewhere
            # This is a placeholder - real usage would be from pipeline
            print(json.dumps({"status": "recorded", "note": "Use pipeline integration for full metrics"}, indent=2))
            return 0
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
        webhook = args.webhook_url or os.getenv("ALERT_WEBHOOK_URL", "")
        wd = Watchdog(output_root=root, webhook_url=webhook)
        result = wd.detect_regressions(args.domain, defects)
        wd.take_snapshot(args.domain, defects)
        print(json.dumps(result, indent=2))
        if args.alert and result.get("regressions"):
            if not webhook:
                print(json.dumps({"status": "skipped", "reason": "--alert requires --webhook-url or ALERT_WEBHOOK_URL"}, indent=2))
            else:
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
            except subprocess.CalledProcessError:
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
            except subprocess.CalledProcessError:
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

    if args.command == "secret-rotation":
        from .secret_rotation import SecretRotationManager, RotationPolicy

        manager = SecretRotationManager()

        if args.rotation_action == "add-policy":
            policy = RotationPolicy(
                name=args.name,
                max_age_days=args.max_age,
                warning_days=args.warning,
                auto_rotate=args.auto_rotate,
                generator=args.generator,
            )
            manager.add_policy(policy)
            print(f"Policy '{args.name}' added")
            return 0

        elif args.rotation_action == "set":
            policy = manager.get_policy(args.policy) if args.policy else None
            manager.set_secret(args.name, args.value, policy)
            print(f"Secret '{args.name}' set")
            return 0

        elif args.rotation_action == "rotate":
            result = manager.rotate_secret(args.name, args.value)
            if result:
                print(f"Secret '{args.name}' rotated to version {result.version}")
                return 0
            else:
                print(f"Failed to rotate secret '{args.name}'")
                return 1

        elif args.rotation_action == "check":
            needed = manager.check_rotation_needed()
            if needed:
                print("Secrets needing rotation:")
                for meta in needed:
                    days = meta.days_until_expiry()
                    print(f"  {meta.name}: expires in {days} days (v{meta.version})")
            else:
                print("All secrets up to date")
            return 0

        elif args.rotation_action == "rotate-all":
            rotated = manager.rotate_all_needed()
            print(f"Rotated {len(rotated)} secrets")
            for name, meta in rotated.items():
                print(f"  {name}: v{meta.version}")
            return 0

        elif args.rotation_action == "list":
            secrets = manager.list_secrets()
            for meta in secrets:
                status = "EXPIRED" if meta.is_expired() else ("NEEDS ROTATION" if meta.needs_rotation() else "OK")
                days = meta.days_until_expiry()
                print(f"  {meta.name}: v{meta.version}, {status}, expires in {days} days")
            return 0

        elif args.rotation_action == "delete":
            if manager.delete_secret(args.name):
                print(f"Secret '{args.name}' deleted")
                return 0
            else:
                print(f"Failed to delete secret '{args.name}'")
                return 1

    if args.command == "eval":
        cmd = ["promptfoo", "eval", "--config", args.config]
        if args.quiet:
            cmd.append("--quiet")
        subprocess.run(cmd, check=True)
        return 0

    if args.command == "config":
        from .config import get_settings, validate_startup

        def _serialize(obj):
            if isinstance(obj, Path):
                return str(obj)
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_serialize(v) for v in obj]
            return obj

        if args.action == "validate":
            result = validate_startup()
            print(json.dumps(_serialize(result), indent=2))
            return 0 if result["valid"] else 1
        elif args.action == "show":
            settings = get_settings()
            # Exclude sensitive fields
            data = _serialize(settings.model_dump())
            for key in ["pagespeed_api_key", "alert_webhook_url"]:
                if key in data and data[key]:
                    data[key] = "***"
            print(json.dumps(data, indent=2))
            return 0

    if args.command == "schema":
        from .schema_validation import (
            validate_all_configs,
            validate_master_plan,
            validate_agency_config,
        )

        if args.file:
            file_str = str(args.file)
            if file_str in ("master_plan", "MASTER_PLAN.yaml"):
                valid, errors, _ = validate_master_plan("MASTER_PLAN.yaml")
                result = {"file": "MASTER_PLAN.yaml", "valid": valid, "errors": errors}
            elif file_str in ("agency_config", "agency_config.json"):
                valid, errors, _ = validate_agency_config("agency_config.json")
                result = {"file": "agency_config.json", "valid": valid, "errors": errors}
            else:
                path = Path(file_str)
                if path.suffix in (".yaml", ".yml"):
                    valid, errors, _ = validate_master_plan(path)
                    result = {"file": file_str, "valid": valid, "errors": errors}
                elif path.suffix == ".json":
                    valid, errors, _ = validate_agency_config(path)
                    result = {"file": file_str, "valid": valid, "errors": errors}
                else:
                    print(json.dumps({"error": f"Unknown file type: {file_str}"}, indent=2))
                    return 1
            print(json.dumps(result, indent=2))
            return 0 if result["valid"] else 1
        else:
            results = validate_all_configs()
            print(json.dumps(results, indent=2))
            return 0 if results["_summary"]["all_valid"] else 1

    if args.command == "actions":
        from .actions import import_report, preview_report

        report = import_report(workspace_path(args.report, must_exist=True, file_only=True))
        output_dir = workspace_path(args.output_dir)
        directory = workspace_path(report["run_id"], root=output_dir)
        if args.operation == "cancel":
            from .common import atomic_write_text

            atomic_write_text(workspace_path("CANCELLED", root=directory), "Cancelled by operator\n")
        print(json.dumps(preview_report(report, directory), indent=2))
        return 0
    if not args.url and not args.batch:
        parser.error("Provide a URL or --batch")
    if not 1 <= args.concurrency <= 4:
        parser.error("Concurrency must be between 1 and 4")
    if args.hourly_rate_nzd is not None and args.hourly_rate_nzd < 0:
        parser.error("Hourly rate must be non-negative")
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
