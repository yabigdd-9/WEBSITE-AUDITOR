import argparse
import getpass
import importlib.util
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from website_auditor.monitoring.watchdog import Watchdog

from .agency_cli import add_commands, run_command
from .ai import generate_drafts, verify_model
from .common import workspace_path
from .external_tools import installed_tools
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
    history = sub.add_parser("history")
    history.add_argument("--query", default="")
    history.add_argument("--output-root", default="outputs/toolkit")
    history.add_argument("--retention-preview", type=int, metavar="KEEP_LAST")
    compare = sub.add_parser("compare", help="Compare saved canonical audits without fetching websites")
    compare.add_argument("target", type=Path)
    compare.add_argument("--against", type=Path, action="append", required=True)
    compare.add_argument("--output-dir", type=Path, required=True)

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
    secret_sub.add_parser("list", help="List secret names")
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
    remediate = sub.add_parser("remediate")
    remediate.add_argument("report", type=Path)
    remediate.add_argument("--output-dir", type=Path, required=True)
    demo_cmd = sub.add_parser("demo")
    demo_cmd.add_argument("report", type=Path)
    demo_cmd.add_argument("remediation", type=Path)
    demo_cmd.add_argument("--output-dir", type=Path, required=True)
    demo_cmd.add_argument("--render", action="store_true")
    implementation = sub.add_parser("implementation-demo", help="Apply an explicit patch to an isolated static copy and capture repeat audits")
    implementation.add_argument("source", type=Path)
    implementation.add_argument("patch_plan", type=Path)
    implementation.add_argument("--entrypoint", default="index.html")
    implementation.add_argument("--output-dir", type=Path, required=True)
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
    identity_review = sub.add_parser(
        "identity-review", help="Propose trading names from saved evidence for human review"
    )
    identity_review.add_argument("captures", type=Path)
    identity_review.add_argument("--output", type=Path, required=True)
    contact_review = sub.add_parser(
        "contact-review", help="Compare independent labels with a frozen contact frame"
    )
    contact_review.add_argument("frame", type=Path)
    contact_review.add_argument("captures", type=Path)
    contact_review.add_argument("review", type=Path)
    contact_review.add_argument("--dataset", type=Path, required=True)
    contact_review.add_argument("--output", type=Path, required=True)
    freeze_review = sub.add_parser(
        "freeze-contact-review", help="Bind saved predictions and evidence before independent review"
    )
    freeze_review.add_argument("frame", type=Path)
    freeze_review.add_argument("captures", type=Path)
    freeze_review.add_argument("--output", type=Path, required=True)
    actions = sub.add_parser("actions")
    actions.add_argument("operation", choices=["preview", "cancel"])
    actions.add_argument("report", type=Path)
    actions.add_argument("--output-dir", type=Path, default=Path("outputs/action-previews"))
    add_commands(sub)
    args = parser.parse_args(argv)
    if args.command == "audit" and args.competitor and (not args.url or args.batch):
        parser.error("Competitor comparison requires one target URL and no --batch")
    if args.command == "compare":
        from .comparison import write_comparison

        try:
            paths = [workspace_path(path, must_exist=True, file_only=True)
                     for path in [args.target, *args.against]]
            if not 2 <= len(paths) <= 100 or len(set(paths)) != len(paths):
                raise ValueError("Choose 2–100 distinct saved report files")
            sizes = [path.stat().st_size for path in paths]
            if max(sizes) > 10_000_000 or sum(sizes) > 20_000_000:
                raise ValueError("Comparison inputs exceed 10 MB per file / 20 MB total")
            output = workspace_path(args.output_dir)
            if output.exists() or any(output.is_relative_to(path.parent) for path in paths):
                raise ValueError("Choose a new comparison directory outside the input report folders")
            inputs = []
            total = 0
            for path in paths:
                with path.open("rb") as source:
                    raw = source.read(10_000_001)
                total += len(raw)
                if len(raw) > 10_000_000 or total > 20_000_000:
                    raise ValueError("Comparison inputs exceed 10 MB per file / 20 MB total")
                inputs.append(json.loads(raw))
            result = write_comparison(inputs, output)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "comparable" else 2
    if args.command == "freeze-contact-review":
        from .common import atomic_write_json
        from .contact_review import freeze_contact_dataset
        try:
            frame = workspace_path(args.frame, must_exist=True, file_only=True)
            captures = workspace_path(args.captures, must_exist=True)
            output = workspace_path(args.output)
            if output.exists() or output.is_relative_to(captures):
                raise ValueError("A new freeze artifact outside the input captures is required")
            result = freeze_contact_dataset(frame, captures)
            atomic_write_json(output, result)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            parser.error(str(exc))
        print(json.dumps({"case_count": len(result["cases"]), "output": str(output), "production_approved": False}, indent=2))
        return 0
    if args.command == "contact-review":
        from .common import atomic_write_json
        from .contact_review import compare_contact_review
        try:
            frame = workspace_path(args.frame, must_exist=True, file_only=True)
            captures = workspace_path(args.captures, must_exist=True)
            review = workspace_path(args.review, must_exist=True, file_only=True)
            dataset = workspace_path(args.dataset, must_exist=True, file_only=True)
            output = workspace_path(args.output)
            if output in {frame, review, dataset} or output.is_relative_to(captures):
                raise ValueError("Comparison output must not overwrite review inputs")
            result = compare_contact_review(frame, captures, review, dataset)
            atomic_write_json(output, result)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            parser.error(str(exc))
        print(json.dumps({"status": result["status"], "counts": result["counts"], "output": str(output), "production_approved": False}, indent=2))
        return 0
    if args.command == "identity-review":
        from .common import atomic_write_json
        from .identity_review import build_identity_review
        try:
            captures = workspace_path(args.captures, must_exist=True)
            output = workspace_path(args.output)
            if output.is_relative_to(captures):
                raise ValueError("Review output must be outside the input captures directory")
            result = build_identity_review(captures)
            atomic_write_json(output, result)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        print(json.dumps({"case_count": result["case_count"], "status_counts": result["status_counts"], "output": str(output), "production_applied": False}, indent=2))
        return 0
    if args.command in {"revenue", "monthly"}:
        try:
            return run_command(args)
        except (ValueError, OSError, KeyError) as exc:
            parser.error(str(exc))

    if args.command == "implementation-demo":
        from .implementation_demo import build_implementation_demo
        try:
            source = workspace_path(args.source, must_exist=True)
            plan_path = workspace_path(args.patch_plan, must_exist=True, file_only=True)
            output = workspace_path(args.output_dir)
            if output == plan_path or plan_path.is_relative_to(output):
                raise ValueError("Output must not contain or overwrite the input patch plan")
            result = build_implementation_demo(source, json.loads(plan_path.read_text()), output, entrypoint=args.entrypoint)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            parser.error(str(exc))
        print(json.dumps({"status": result["status"], "output": str(output), "source_unchanged": result["source_unchanged"], "production_changed": False, "removed_findings": result["removed_findings"], "new_findings": result["new_findings"]}, indent=2))
        return 0 if result["local_improvement_observed"] else 2
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

    if args.command == "eval":
        cmd = ["promptfoo", "eval", "--config", args.config]
        if args.quiet:
            cmd.append("--quiet")
        subprocess.run(cmd, check=True)
        return 0

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
    if args.competitor and len(urls) < 2:
        parser.error("Competitor comparison requires a distinct comparison URL")
    comparison = None
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        reports = list(pool.map(lambda url: run_audit(url, options), urls))
    if args.competitor:
        from .comparison import write_comparison

        comparison = write_comparison(reports, options.output_root / (reports[0]["run_id"] + "-comparison"))
        # Keep the existing list-shaped CLI output; audit run artifacts remain immutable.
        reports = [{**report, "artifacts": {**report["artifacts"],
                    "comparison_json": comparison["json"], "comparison_html": comparison["html"]}}
                   for report in reports]
    print(
        json.dumps(
            [
                {
                    "url": r["url"],
                    "run_id": r["run_id"],
                    "status": r["status"],
                    "health_score": r["health_score"],
                    "artifacts": r["artifacts"],
                    **({"comparison": comparison} if comparison else {}),
                }
                for r in reports
            ],
            indent=2,
        )
    )
    return 0 if (all(r["status"] == "complete" for r in reports)
                 and (comparison is None or comparison["status"] == "comparable")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
