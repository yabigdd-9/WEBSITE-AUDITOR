import pathlib

master = """#!/usr/bin/env python3
\"\"\"
wa - WEBSITE-AUDITOR Master Command
Runs the ENTIRE 18-module platform in one command.

Usage:
  python3 wa.py run <domain>     # Run everything for one domain
  python3 wa.py run --all        # Run everything for all clients
  python3 wa.py status           # Quick system status
  python3 wa.py open             # Open the command center
  python3 wa.py help             # Show all commands
\"\"\"
import subprocess, sys, os, time
from pathlib import Path
from datetime import datetime

os.environ.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")
os.environ.setdefault("REQUESTS_CA_BUNDLE", "/etc/ssl/cert.pem")

# All 18 modules in execution order
MODULES = [
    # Phase 1: Core Audit
    {"name": "Single-Site Audit",        "script": "website_auditor.py",        "args": ["{domain}"],     "phase": "AUDIT"},
    {"name": "Batch Remediation",        "script": "remediation-engine.py",     "args": ["--all", "--output-dir", "outputs/remediations"], "phase": "AUDIT"},
    {"name": "Dashboard",                "script": "audit-dashboard.py",        "args": ["--output", "report.html"], "phase": "AUDIT"},
    
    # Phase 2: Revenue Intelligence
    {"name": "Revenue Calculator",       "script": "revenue_report.py",         "args": [],               "phase": "REVENUE"},
    {"name": "Monthly Reports",          "script": "monthly_report.py",         "args": [],               "phase": "REVENUE"},
    
    # Phase 3: Sales & Outreach
    {"name": "Prospect Scoring",         "script": "generate_outreach.py",      "args": [],               "phase": "SALES"},
    {"name": "AI Sales Assistant",       "script": "ai_sales.py",               "args": ["{domain}"],     "phase": "SALES"},
    {"name": "Competitor Espionage",     "script": "competitor_spy.py",         "args": ["{domain}"],     "phase": "SALES", "optional": True},
    
    # Phase 4: Client Management
    {"name": "Client Onboarding",        "script": "onboard_client.py",         "args": ["{domain}"],     "phase": "CLIENT", "optional": True},
    {"name": "Approval Workflow",        "script": "approval_workflow.py",      "args": [],               "phase": "CLIENT"},
    {"name": "Churn Predictor",          "script": "churn_predictor.py",        "args": [],               "phase": "CLIENT"},
    
    # Phase 5: Monitoring & Compliance
    {"name": "Nightly Watchdog",         "script": "nightly_watchdog.py",       "args": [],               "phase": "MONITOR"},
    {"name": "SSL Monitor",              "script": "ssl_monitor.py",            "args": ["--days", "30"], "phase": "MONITOR"},
    {"name": "Uptime Monitor",           "script": "uptime_monitor.py",         "args": [],               "phase": "MONITOR"},
    {"name": "SEO Tracker",              "script": "seo_tracker.py",            "args": [],               "phase": "MONITOR"},
    {"name": "Backup Checker",           "script": "backup_checker.py",         "args": [],               "phase": "MONITOR"},
    
    # Phase 6: Compliance & Export
    {"name": "Legal Shield",             "script": "legal_shield.py",           "args": [],               "phase": "COMPLIANCE"},
    {"name": "CRM Export",               "script": "crm_hub.py",                "args": ["--format", "generic"], "phase": "EXPORT"},
    
    # Phase 7: Command Center
    {"name": "Command Center",           "script": "command_center.py",         "args": [],               "phase": "DASHBOARD"},
]


def run_module(module, domain=None):
    \"\"\"Run a single module and return success/failure.\"\"\"
    script = module["script"]
    
    if not Path(script).exists():
        return {"status": "skipped", "reason": f"{script} not found"}
    
    # Build args, replacing {domain} placeholder
    args = []
    for arg in module.get("args", []):
        if arg == "{domain}" and domain:
            args.append(domain)
        elif arg != "{domain}":
            args.append(arg)
    
    # Skip domain-specific modules if no domain provided
    if "{domain}" in module.get("args", []) and not domain:
        return {"status": "skipped", "reason": "No domain specified"}
    
    cmd = [sys.executable, script] + args
    
    try:
        start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        elapsed = time.time() - start
        
        if result.returncode == 0:
            return {"status": "success", "time": f"{elapsed:.1f}s"}
        else:
            error_msg = result.stderr.strip().split("\\n")[-1][:80] if result.stderr else "Unknown error"
            return {"status": "error", "reason": error_msg, "time": f"{elapsed:.1f}s"}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "reason": "Exceeded 120s limit"}
    except Exception as e:
        return {"status": "error", "reason": str(e)[:80]}


def run_all(domain=None):
    \"\"\"Run all 18 modules in sequence.\"\"\"
    print(f"\\n{'#'*70}")
    print(f"#  WEBSITE-AUDITOR — FULL PLATFORM EXECUTION")
    print(f"#  Target: {domain or 'All Clients'}")
    print(f"#  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*70}\\n")
    
    results = []
    current_phase = ""
    
    for module in MODULES:
        # Print phase header
        if module["phase"] != current_phase:
            current_phase = module["phase"]
            print(f"\\n{'='*70}")
            print(f"  PHASE: {current_phase}")
            print(f"{'='*70}")
        
        print(f"  Running: {module['name']:<35}", end=" ", flush=True)
        
        result = run_module(module, domain)
        results.append({"module": module["name"], **result})
        
        if result["status"] == "success":
            print(f"✅ ({result.get('time', '')})")
        elif result["status"] == "skipped":
            is_optional = module.get("optional", False)
            icon = "⏭️ " if is_optional else "⚠️ "
            print(f"{icon} Skipped: {result.get('reason', '')}")
        elif result["status"] == "timeout":
            print(f"⏰ Timeout")
        else:
            print(f"❌ {result.get('reason', 'Failed')[:50]}")
    
    # Final Summary
    success = len([r for r in results if r["status"] == "success"])
    skipped = len([r for r in results if r["status"] == "skipped"])
    failed = len([r for r in results if r["status"] in ["error", "timeout"]])
    
    print(f"\\n{'#'*70}")
    print(f"#  EXECUTION COMPLETE")
    print(f"#  ✅ Success: {success}  |  ⏭️  Skipped: {skipped}  |  ❌ Failed: {failed}")
    print(f"{'#'*70}\\n")
    
    # Quick stats
    rev_summary = Path("outputs/revenue/portfolio-summary.json")
    if rev_summary.exists():
        import json
        data = json.loads(rev_summary.read_text())
        print(f"  💰 Total Revenue at Risk: ${data.get('total_revenue_at_risk_nzd', 0):,.0f}/month")
        print(f"  🔧 Total Fix Investment:  ${data.get('total_fix_cost_nzd', 0):,.0f}")
        print(f"  📊 Sites Analysed:        {data.get('sites_analysed', 0)}")
    
    print(f"\\n  📁 Reports:    outputs/reports/")
    print(f"  📁 Revenue:    outputs/revenue/")
    print(f"  📁 CRM Export: outputs/crm/")
    print(f"  📁 Compliance: outputs/compliance/")
    print(f"\\n  🌐 Open Command Center: python3 wa.py open")
    print(f"{'#'*70}\\n")
    
    return results


def show_status():
    \"\"\"Quick system status check.\"\"\"
    print(f"\\n{'='*60}")
    print(f"  WEBSITE-AUDITOR SYSTEM STATUS")
    print(f"{'='*60}\\n")
    
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
        icon = "✅" if exists else "❌"
        print(f"  {icon} {name}")
    
    print(f"\\n{'='*60}\\n")


def open_command_center():
    \"\"\"Open the command center in the default browser.\"\"\"
    cc_path = Path("outputs/command_center.html")
    if cc_path.exists():
        import subprocess
        if sys.platform == "darwin":
            subprocess.run(["open", str(cc_path)])
        elif sys.platform == "linux":
            subprocess.run(["xdg-open", str(cc_path)])
        elif sys.platform == "win32":
            subprocess.run(["start", str(cc_path)], shell=True)
        print(f"  🌐 Opened: {cc_path}")
    else:
        print("  ❌ Command center not found. Run: python3 wa.py run")


def show_help():
    print(f"""
{'='*60}
  wa — WEBSITE-AUDITOR MASTER COMMAND
{'='*60}

  USAGE:
    python3 wa.py run <domain>      Run full platform for one domain
    python3 wa.py run --all         Run full platform for all clients
    python3 wa.py status            Show system status
    python3 wa.py open              Open command center in browser
    python3 wa.py help              Show this help

  EXAMPLES:
    python3 wa.py run clyne-bennie.co.nz
    python3 wa.py run --all
    python3 wa.py open

  WHAT IT RUNS (18 modules):
    Phase 1 - AUDIT:      Site audit, remediation, dashboard
    Phase 2 - REVENUE:    Revenue calculator, monthly reports
    Phase 3 - SALES:      Prospect scoring, AI sales, competitor spy
    Phase 4 - CLIENT:     Onboarding, approvals, churn predictor
    Phase 5 - MONITOR:    Watchdog, SSL, uptime, SEO, backups
    Phase 6 - COMPLIANCE: Legal shield, CRM export
    Phase 7 - DASHBOARD:  Command center generation

{'='*60}
""")


def main():
    if len(sys.argv) < 2:
        show_help()
        return
    
    cmd = sys.argv[1].lower()
    
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
        print(f"Unknown command: {cmd}")
        show_help()


if __name__ == "__main__":
    main()
"""
pathlib.Path("wa.py").write_text(master)
print("✅ wa.py master command created!")
print("   Usage: python3 wa.py run --all")
