#!/usr/bin/env python3
"""
wa — WEBSITE-AUDITOR CLI
Usage: python3 wa.py <command> [options]
"""
import sys, os, json, subprocess
from pathlib import Path
from datetime import datetime, timezone

os.environ.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")
os.environ.setdefault("REQUESTS_CA_BUNDLE", "/etc/ssl/cert.pem")

HELP = """
╔══════════════════════════════════════════════════════════╗
║  wa — WEBSITE-AUDITOR Command Center                    ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  AUDIT                                                   ║
║    wa audit <url>          Audit a single site           ║
║    wa batch                Run batch remediation         ║
║    wa dashboard            Generate HTML dashboard       ║
║                                                          ║
║  ACTIONS                                                 ║
║    wa actions status       Show action engine status     ║
║    wa actions list         List proposed actions         ║
║    wa actions dry-run      Evaluate all actions          ║
║    wa actions approve <id> Approve an action             ║
║                                                          ║
║  MONITOR                                                 ║
║    wa watchdog             Run regression check          ║
║    wa watchdog history     Show snapshot history         ║
║                                                          ║
║  OUTREACH                                                ║
║    wa outreach drafts      List generated drafts         ║
║    wa outreach compliance  Check compliance status       ║
║                                                          ║
║  AI                                                      ║
║    wa ai summary <url>     Generate AI summary           ║
║    wa ai status            Check Ollama availability     ║
║                                                          ║
║  PORTAL                                                  ║
║    wa portal               Start client portal           ║
║                                                          ║
║  PIPELINE                                                ║
║    wa run <url>            Run FULL pipeline             ║
║    wa status               Show system status            ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""

def cmd_audit(url):
    print(f"\n🔍 Auditing: {url}")
    subprocess.run([sys.executable, "website_auditor.py", url])

def cmd_batch():
    print("\n🔧 Running batch remediation...")
    subprocess.run([sys.executable, "remediation-engine.py", "--all", "--output-dir", "outputs/remediations"])

def cmd_dashboard():
    print("\n📊 Generating dashboard...")
    subprocess.run([sys.executable, "audit-dashboard.py", "--output", "report.html"])
    print("   Open: open report.html")

def cmd_run(url):
    print(f"\n🚀 Running full pipeline for: {url}")
    subprocess.run([sys.executable, "run_all.py", url])

def cmd_actions_status():
    try:
        from website_auditor.actions.executor import ActionExecutor
        ex = ActionExecutor()
        summary = ex.status_summary()
        print(json.dumps(summary, indent=2))
    except Exception as e:
        print(f"⚠️  {e}")

def cmd_actions_list():
    path = Path("outputs/actions/proposed_actions.jsonl")
    if not path.exists():
        print("No actions found. Run: wa run <url>")
        return
    for line in path.read_text().splitlines():
        if line.strip():
            a = json.loads(line)
            print(f"  {a['action_id'][:16]} | {a['domain']:<30} | {a['name']:<35} | {a['risk']:<8} | {a['status']}")

def cmd_actions_dry_run():
    try:
        from website_auditor.actions.executor import ActionExecutor
        ex = ActionExecutor()
        result = ex.dry_run_all()
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"⚠️  {e}")

def cmd_watchdog():
    try:
        from website_auditor.monitoring.watchdog import Watchdog
        wd = Watchdog()
        rem_dir = Path("outputs/remediations")
        if not rem_dir.exists():
            print("No remediation data. Run: wa batch")
            return
        for f in rem_dir.glob("*.json"):
            if "summary" in f.name: continue
            data = json.loads(f.read_text())
            domain = f.stem.replace("-remediation", "")
            defects = data.get("defects", data.get("issues", []))
            result = wd.run_check(domain, defects)
            status = "baseline" if result.get("first_audit") else f"{len(result.get('regressions', []))} regressions"
            print(f"  {domain}: {status}")
    except Exception as e:
        print(f"⚠️  {e}")

def cmd_watchdog_history():
    snap_dir = Path("outputs/snapshots")
    if not snap_dir.exists():
        print("No snapshots yet. Run: wa watchdog")
        return
    for f in sorted(snap_dir.glob("*.json")):
        data = json.loads(f.read_text())
        print(f"  {data.get('domain', '?'):<30} | {data.get('timestamp', '?')} | {data.get('count', 0)} defects")

def cmd_outreach_drafts():
    draft_dir = Path("outputs/outreach")
    if not draft_dir.exists():
        print("No drafts. Run: wa run <url>")
        return
    for f in draft_dir.glob("draft_*.json"):
        d = json.loads(f.read_text())
        comp = d.get("compliance", {})
        print(f"  {d.get('domain', '?'):<30} | to: {d.get('to', '?'):<30} | compliance: {'✅' if comp.get('passed') else '❌'}")

def cmd_ai_status():
    import urllib.request
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2) as resp:
            models = json.loads(resp.read()).get("models", [])
            print(f"  ✅ Ollama running | Models: {[m['name'] for m in models]}")
    except Exception:
        print("  ℹ️  Ollama not running — using template fallback")

def cmd_ai_summary(url):
    try:
        from website_auditor.ai.summarizer import AISummarizer
        ai = AISummarizer()
        clean = url.replace("https://", "").replace("http://", "").split("/")[0]
        defects = []
        score = 0
        for f in Path("outputs/remediations").glob("*.json"):
            if "summary" in f.name: continue
            try:
                data = json.loads(f.read_text())
                defects = data.get("defects", data.get("issues", []))
                score = data.get("score", 0)
                break
            except: continue
        result = ai.generate_summary(clean, defects, score)
        print(f"\n  [{result['source']}]")
        print(f"  {result['summary']}")
    except Exception as e:
        print(f"⚠️  {e}")

def cmd_portal():
    subprocess.run([sys.executable, "-m", "website_auditor.portal.server"])

def cmd_status():
    print("\n╔══════════════════════════════════════════╗")
    print("║  SYSTEM STATUS                           ║")
    print("╠══════════════════════════════════════════╣")
    
    # Audit outputs
    rem_dir = Path("outputs/remediations")
    site_count = len(list(rem_dir.glob("*-remediation.json"))) if rem_dir.exists() else 0
    print(f"║  Sites audited:    {site_count:<25}║")
    
    # Actions
    act_file = Path("outputs/actions/proposed_actions.jsonl")
    act_count = len(act_file.read_text().splitlines()) if act_file.exists() else 0
    print(f"║  Proposed actions: {act_count:<25}║")
    
    # Snapshots
    snap_dir = Path("outputs/snapshots")
    snap_count = len(list(snap_dir.glob("*.json"))) if snap_dir.exists() else 0
    print(f"║  Snapshots:        {snap_count:<25}║")
    
    # Drafts
    draft_dir = Path("outputs/outreach")
    draft_count = len(list(draft_dir.glob("draft_*.json"))) if draft_dir.exists() else 0
    print(f"║  Outreach drafts:  {draft_count:<25}║")
    
    # AI
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
        ai_status = "✅ Ollama active"
    except:
        ai_status = "ℹ️  Template fallback"
    print(f"║  AI engine:        {ai_status:<25}║")
    
    # Portal
    print(f"║  Portal:           python3 wa.py portal  ║")
    print("╚══════════════════════════════════════════╝")

def main():
    if len(sys.argv) < 2:
        print(HELP)
        return
    
    cmd = sys.argv[1]
    args = sys.argv[2:]
    
    commands = {
        "audit": lambda: cmd_audit(args[0] if args else "https://example.co.nz"),
        "batch": cmd_batch,
        "dashboard": cmd_dashboard,
        "run": lambda: cmd_run(args[0] if args else "https://example.co.nz"),
        "status": cmd_status,
        "portal": cmd_portal,
        "help": lambda: print(HELP),
    }
    
    # Nested commands
    if cmd == "actions" and args:
        sub = args[0]
        if sub == "status": cmd_actions_status()
        elif sub == "list": cmd_actions_list()
        elif sub == "dry-run": cmd_actions_dry_run()
        else: print(f"Unknown actions command: {sub}")
    elif cmd == "watchdog":
        if args and args[0] == "history": cmd_watchdog_history()
        else: cmd_watchdog()
    elif cmd == "outreach":
        if args and args[0] == "drafts": cmd_outreach_drafts()
        else: cmd_outreach_drafts()
    elif cmd == "ai":
        if args and args[0] == "status": cmd_ai_status()
        elif args and args[0] == "summary": cmd_ai_summary(args[1] if len(args) > 1 else "example.co.nz")
        else: cmd_ai_status()
    elif cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(HELP)

if __name__ == "__main__":
    main()
