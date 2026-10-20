#!/usr/bin/env python3
"""
wa - WEBSITE-AUDITOR Master Command
Legacy 17-module workflow plus an explicit canonical toolkit command route.

Usage:
  python3 wa.py run <domain>     Run everything for one domain
  python3 wa.py run --all        Run everything for all clients
  python3 wa.py status           Quick system status
  python3 wa.py open             Open the command center
  python3 wa.py help             Show all commands
"""

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

MODULES = [
    {
        "name": "Single-Site Audit",
        "script": "website_auditor.py",
        "args": ["{domain}"],
        "phase": "AUDIT",
    },
    {
        "name": "Batch Remediation",
        "script": "remediation-engine.py",
        "args": ["--all", "--output-dir", "outputs/remediations"],
        "phase": "AUDIT",
    },
    {
        "name": "Dashboard",
        "script": "audit-dashboard.py",
        "args": ["--output", "report.html"],
        "phase": "AUDIT",
    },
    {"name": "Revenue Calculator", "script": "revenue_report.py", "args": [], "phase": "REVENUE"},
    {"name": "Monthly Reports", "script": "monthly_report.py", "args": [], "phase": "REVENUE"},
    {"name": "Prospect Scoring", "script": "generate_outreach.py", "args": [], "phase": "SALES"},
    {"name": "AI Sales Assistant", "script": "ai_sales.py", "args": ["{domain}"], "phase": "SALES"},
    {"name": "Approval Workflow", "script": "approval_workflow.py", "args": [], "phase": "CLIENT"},
    {"name": "Churn Predictor", "script": "churn_predictor.py", "args": [], "phase": "CLIENT"},
    {"name": "Nightly Watchdog", "script": "nightly_watchdog.py", "args": [], "phase": "MONITOR"},
    {
        "name": "SSL Monitor",
        "script": "ssl_monitor.py",
        "args": ["--days", "30"],
        "phase": "MONITOR",
    },
    {"name": "Uptime Monitor", "script": "uptime_monitor.py", "args": [], "phase": "MONITOR"},
    {"name": "SEO Tracker", "script": "seo_tracker.py", "args": [], "phase": "MONITOR"},
    {"name": "Backup Checker", "script": "backup_checker.py", "args": [], "phase": "MONITOR"},
    {"name": "Legal Shield", "script": "legal_shield.py", "args": [], "phase": "COMPLIANCE"},
    {
        "name": "CRM Export",
        "script": "crm_hub.py",
        "args": ["--format", "generic"],
        "phase": "EXPORT",
    },
    {"name": "Command Center", "script": "command_center.py", "args": [], "phase": "DASHBOARD"},
]


def run_module(module, domain=None):
    script = module["script"]
    if not (ROOT / script).is_file():
        return {"status": "skipped", "reason": script + " not found"}

    args = []
    for arg in module.get("args", []):
        if arg == "{domain}" and domain:
            args.append(domain)
        elif arg != "{domain}":
            args.append(arg)

    if "{domain}" in module.get("args", []) and not domain:
        return {"status": "skipped", "reason": "No domain specified"}

    cmd = [sys.executable, script] + args
    try:
        start = time.time()
        env = os.environ.copy()
        env.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")
        env.setdefault("REQUESTS_CA_BUNDLE", "/etc/ssl/cert.pem")
        result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
        elapsed = time.time() - start
        if result.returncode == 0:
            return {"status": "success", "time": round(elapsed, 1)}
        else:
            err = result.stderr.strip().split("\n")[-1][:80] if result.stderr else "Unknown"
            return {"status": "error", "reason": err, "time": round(elapsed, 1)}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "reason": "Exceeded 120s"}
    except Exception as e:
        return {"status": "error", "reason": str(e)[:80]}


def run_all(domain=None):
    sep = "#" * 70
    eq = "=" * 70
    print("\n" + sep)
    print("#  WEBSITE-AUDITOR - FULL PLATFORM EXECUTION")
    print("#  Target: " + (domain or "All Clients"))
    print("#  Started: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print(sep + "\n")

    results = []
    current_phase = ""

    for module in MODULES:
        if module["phase"] != current_phase:
            current_phase = module["phase"]
            print("\n" + eq)
            print("  PHASE: " + current_phase)
            print(eq)

        print("  Running: " + module["name"].ljust(35), end=" ", flush=True)
        result = run_module(module, domain)
        results.append({"module": module["name"], **result})

        if result["status"] == "success":
            print("OK (" + str(result.get("time", "")) + "s)")
        elif result["status"] == "skipped":
            print("SKIP: " + result.get("reason", ""))
        elif result["status"] == "timeout":
            print("TIMEOUT")
        else:
            print("FAIL: " + result.get("reason", "")[:50])

    success = len([r for r in results if r["status"] == "success"])
    skipped = len([r for r in results if r["status"] == "skipped"])
    failed = len([r for r in results if r["status"] in ["error", "timeout"]])

    print("\n" + sep)
    print("#  WORKFLOW INCOMPLETE" if skipped or failed else "#  ALL MODULES COMPLETED")
    print(
        "#  Success: "
        + str(success)
        + "  |  Skipped: "
        + str(skipped)
        + "  |  Failed: "
        + str(failed)
    )
    print(sep + "\n")

    rev_summary = ROOT / Path("outputs/revenue/portfolio-summary.json")
    if rev_summary.exists():
        import json

        data = json.loads(rev_summary.read_text())
        risk = data.get("total_revenue_at_risk_nzd", 0)
        cost = data.get("total_fix_cost_nzd", 0)
        sites = data.get("sites_analysed", 0)
        print("  Revenue at Risk: $" + format(risk, ",") + "/month")
        print("  Fix Investment:  $" + format(cost, ","))
        print("  Sites Analysed:  " + str(sites))

    print("\n  Reports:    outputs/reports/")
    print("  Revenue:    outputs/revenue/")
    print("  CRM Export: outputs/crm/")
    print("  Compliance: outputs/compliance/")
    print("\n  Open Command Center: python3 wa.py open")
    print(sep + "\n")
    return results


def show_status():
    eq = "=" * 60
    print("\n" + eq)
    print("  SAVED LEGACY OUTPUT INVENTORY")
    print(eq + "\n")

    print("Folder presence does not verify freshness, runtime health or acceptance.\n")
    checks = {
        "Audit Data": (ROOT / Path("outputs/remediations")).exists(),
        "Revenue Data": (ROOT / Path("outputs/revenue")).exists(),
        "Monthly Reports": (ROOT / Path("outputs/reports")).exists(),
        "Outreach Pipeline": (ROOT / Path("outputs/outreach")).exists(),
        "Snapshots": (ROOT / Path("outputs/snapshots")).exists(),
        "Compliance": (ROOT / Path("outputs/compliance")).exists(),
        "SSL Reports": (ROOT / Path("outputs/ssl")).exists(),
        "Uptime Data": (ROOT / Path("outputs/uptime")).exists(),
        "SEO Data": (ROOT / Path("outputs/seo")).exists(),
        "CRM Export": (ROOT / Path("outputs/crm")).exists(),
        "Command Center": (ROOT / Path("outputs/command_center.html")).exists(),
    }

    for name, exists in checks.items():
        icon = "[PRESENT]" if exists else "[MISSING]"
        print("  " + icon + " " + name)

    print("\n" + eq + "\n")


def open_command_center():
    cc_path = ROOT / "outputs/command_center.html"
    if not cc_path.is_file():
        print("Command center not found. The saved output has not been verified.", file=sys.stderr)
        return 1
    try:
        if sys.platform == "darwin":
            result = subprocess.run(["open", str(cc_path)], check=False)
        elif sys.platform == "linux":
            result = subprocess.run(["xdg-open", str(cc_path)], check=False)
        elif sys.platform == "win32":
            os.startfile(str(cc_path))
            result = None
        else:
            print("No supported viewer for this platform.", file=sys.stderr)
            return 1
    except OSError as exc:
        print("Could not open saved command center: " + str(exc), file=sys.stderr)
        return 1
    if result is not None and result.returncode:
        print("The command-center viewer failed.", file=sys.stderr)
        return 1
    print("Opened saved file: " + str(cc_path))
    return 0


def show_help():
    eq = "=" * 60
    print("\n" + eq)
    print("  wa - WEBSITE-AUDITOR MASTER COMMAND")
    print(eq)
    print("")
    print("  USAGE:")
    print("    python3 wa.py run <domain>    Run full platform for one domain")
    print("    python3 wa.py run --all       Run full platform for all clients")
    print("    python3 wa.py status          List saved legacy output paths")
    print("    python3 wa.py toolkit <args>  Use the canonical audit commands")
    print("    python3 wa.py toolkit --help  Canonical command reference")
    print("    python3 wa.py open            Open command center in browser")
    print("    python3 wa.py help            Show this help")
    print("")
    print("  EXAMPLES:")
    print("    python3 wa.py run clyne-bennie.co.nz")
    print("    python3 wa.py run --all")
    print("    python3 wa.py open")
    print("")
    print("  PHASES (17 modules):")
    print("    AUDIT      Site audit, remediation, dashboard")
    print("    REVENUE    Revenue calculator, monthly reports")
    print("    SALES      Prospect scoring, AI sales assistant")
    print("    CLIENT     Approval workflow, churn predictor")
    print("    MONITOR    Watchdog, SSL, uptime, SEO, backups")
    print("    COMPLIANCE Legal shield")
    print("    EXPORT     CRM export")
    print("    DASHBOARD  Command center generation")
    print("")
    print(eq + "\n")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        show_help()
        return 0
    cmd = args[0].lower()
    if cmd == "toolkit":
        from auditor_toolkit.cli import main as toolkit_main

        return toolkit_main(args[1:])
    if cmd == "run":
        if len(args) != 2 or (args[1].startswith("-") and args[1] != "--all"):
            print("Usage: python3 wa.py run <domain> | --all", file=sys.stderr)
            return 2
        results = run_all(None if args[1] == "--all" else args[1])
        return 0 if results and all(r["status"] == "success" for r in results) else 1
    if cmd not in {"status", "open", "help"}:
        print(
            "Unknown command: " + cmd + ". Use 'toolkit --help' for canonical commands.",
            file=sys.stderr,
        )
        return 2
    if len(args) != 1:
        print("Unexpected arguments for " + cmd, file=sys.stderr)
        return 2
    if cmd == "status":
        show_status()
        return 0
    if cmd == "open":
        return open_command_center()
    show_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
