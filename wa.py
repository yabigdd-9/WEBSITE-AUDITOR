#!/usr/bin/env python3
"""
wa - WEBSITE-AUDITOR Master Command
Runs the ENTIRE 18-module platform in one command.

Usage:
  python3 wa.py run <domain>     Run everything for one domain
  python3 wa.py run --all        Run everything for all clients
  python3 wa.py status           Quick system status
  python3 wa.py open             Open the command center
  python3 wa.py help             Show all commands
"""
import subprocess, sys, os, time
from pathlib import Path
from datetime import datetime

os.environ.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")
os.environ.setdefault("REQUESTS_CA_BUNDLE", "/etc/ssl/cert.pem")

MODULES = [
    {"name": "Single-Site Audit",    "script": "wa.py",    "args": ["audit", "{domain}"],  "phase": "AUDIT"},
    {"name": "Batch Remediation",    "script": "remediation-engine.py", "args": ["--all", "--output-dir", "outputs/remediations"], "phase": "AUDIT"},
    {"name": "Dashboard",            "script": "audit-dashboard.py",    "args": ["--output", "report.html"], "phase": "AUDIT"},
    {"name": "Revenue Calculator",   "script": "revenue_report.py",     "args": [],            "phase": "REVENUE"},
    {"name": "Monthly Reports",      "script": "monthly_report.py",     "args": [],            "phase": "REVENUE"},
    {"name": "Prospect Scoring",     "script": "generate_outreach.py",  "args": [],            "phase": "SALES"},
    {"name": "AI Sales Assistant",   "script": "ai_sales.py",           "args": ["{domain}"],  "phase": "SALES"},
    {"name": "Approval Workflow",    "script": "approval_workflow.py",  "args": [],            "phase": "CLIENT"},
    {"name": "Churn Predictor",      "script": "churn_predictor.py",    "args": [],            "phase": "CLIENT"},
    {"name": "Nightly Watchdog",     "script": "nightly_watchdog.py",   "args": [],            "phase": "MONITOR"},
    {"name": "SSL Monitor",          "script": "ssl_monitor.py",        "args": ["--days", "30"], "phase": "MONITOR"},
    {"name": "Uptime Monitor",       "script": "uptime_monitor.py",     "args": [],            "phase": "MONITOR"},
    {"name": "SEO Tracker",          "script": "seo_tracker.py",        "args": [],            "phase": "MONITOR"},
    {"name": "Backup Checker",       "script": "backup_checker.py",     "args": [],            "phase": "MONITOR"},
    {"name": "Legal Shield",         "script": "legal_shield.py",       "args": [],            "phase": "COMPLIANCE"},
    {"name": "CRM Export",           "script": "crm_hub.py",            "args": ["--format", "generic"], "phase": "EXPORT"},
    {"name": "Command Center",       "script": "command_center.py",     "args": [],            "phase": "DASHBOARD"},
]


def run_module(module, domain=None):
    script = module["script"]
    if not Path(script).exists():
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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
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
    print("#  EXECUTION COMPLETE")
    print("#  Success: " + str(success) + "  |  Skipped: " + str(skipped) + "  |  Failed: " + str(failed))
    print(sep + "\n")

    rev_summary = Path("outputs/revenue/portfolio-summary.json")
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
    print("  WEBSITE-AUDITOR SYSTEM STATUS")
    print(eq + "\n")

    checks = {
        "Audit Data": Path("outputs/remediations").exists(),
        "Revenue Data": Path("outputs/revenue").exists(),
        "Monthly Reports": Path("outputs/reports").exists(),
        "Outreach Pipeline": Path("outputs/outreach").exists(),
        "Snapshots": Path("outputs/snapshots").exists(),
        "Compliance": Path("outputs/compliance").exists(),
        "SSL Reports": Path("outputs/ssl").exists(),
        "Uptime Data": Path("outputs/uptime").exists(),
        "SEO Data": Path("outputs/seo").exists(),
        "CRM Export": Path("outputs/crm").exists(),
        "Command Center": Path("outputs/command_center.html").exists(),
    }

    for name, exists in checks.items():
        icon = "[OK]" if exists else "[--]"
        print("  " + icon + " " + name)

    print("\n" + eq + "\n")


def open_command_center():
    cc_path = Path("outputs/command_center.html")
    if cc_path.exists():
        if sys.platform == "darwin":
            subprocess.run(["open", str(cc_path)])
        elif sys.platform == "linux":
            subprocess.run(["xdg-open", str(cc_path)])
        elif sys.platform == "win32":
            subprocess.run(["start", str(cc_path)], shell=True)
        print("  Opened: " + str(cc_path))
    else:
        print("  Command center not found. Run: python3 wa.py run --all")


def show_help():
    eq = "=" * 60
    print("\n" + eq)
    print("  wa - WEBSITE-AUDITOR MASTER COMMAND")
    print(eq)
    print("")
    print("  USAGE:")
    print("    python3 wa.py run <domain>    Run full platform for one domain")
    print("    python3 wa.py run --all       Run full platform for all clients")
    print("    python3 wa.py status          Show system status")
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


def main():
    if len(sys.argv) < 2:
        show_help()
        return

    cmd = sys.argv[1].lower()

    if cmd == "audit":
        if len(sys.argv) > 2:
            import website_auditor as auditor
            auditor.run(sys.argv[2])
        else:
            print("Usage: python3 wa.py audit <domain>")
        return
    if cmd == "run":
        domain = None
        if len(sys.argv) > 2 and sys.argv[2] != "--all":
            domain = sys.argv[2]
        run_all(domain)
    elif cmd == "status":
        show_status()
    elif cmd == "open":
        open_command_center()
    elif cmd == "help":
        show_help()
    else:
        print("Unknown command: " + cmd)
        show_help()


if __name__ == "__main__":
    main()
