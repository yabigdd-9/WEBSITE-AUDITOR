"""Interactive terminal control center for WEBSITE-AUDITOR."""
import json, os, sys
from pathlib import Path
from datetime import datetime, timezone

os.environ.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")

def clear():
    os.system("clear" if os.name != "nt" else "cls")

def get_system_data():
    data = {"sites": [], "actions": 0, "snapshots": 0, "drafts": 0, "ai": False}
    
    rem_dir = Path("outputs/remediations")
    if rem_dir.exists():
        for f in sorted(rem_dir.glob("*-remediation.json")):
            try:
                d = json.loads(f.read_text())
                data["sites"].append({
                    "domain": f.stem.replace("-remediation", ""),
                    "score": d.get("score", 0),
                    "defects": len(d.get("defects", d.get("issues", []))),
                })
            except: continue
    
    act_file = Path("outputs/actions/proposed_actions.jsonl")
    if act_file.exists():
        data["actions"] = len([l for l in act_file.read_text().splitlines() if l.strip()])
    
    snap_dir = Path("outputs/snapshots")
    if snap_dir.exists():
        data["snapshots"] = len(list(snap_dir.glob("*.json")))
    
    draft_dir = Path("outputs/outreach")
    if draft_dir.exists():
        data["drafts"] = len(list(draft_dir.glob("draft_*.json")))
    
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
        data["ai"] = True
    except: pass
    
    return data

def score_bar(score, width=20):
    filled = int(score / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    color = "\033[92m" if score >= 70 else "\033[93m" if score >= 40 else "\033[91m"
    return f"{color}{bar}\033[0m {score}/100"

def render():
    clear()
    data = get_system_data()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"""
\033[96m╔══════════════════════════════════════════════════════════════════╗
║          WEBSITE-AUDITOR — CONTROL CENTER                       ║
║          {now}                                    ║
╚══════════════════════════════════════════════════════════════════╝\033[0m

\033[93m┌─ SYSTEM ─────────────────────────────────────────────────────────┐\033[0m
│  🤖 Action Engine:  {data['actions']} proposed actions                       
│  🕵️  Watchdog:       {data['snapshots']} snapshots                            
│  📧 Outreach:       {data['drafts']} drafts (send: BLOCKED)                  
│  🧠 AI Engine:      {'✅ Ollama active' if data['ai'] else 'ℹ️  Template fallback'}                          
│  🔒 Policy:         dry_run (safe mode)                          
\033[93m└──────────────────────────────────────────────────────────────────┘\033[0m

\033[93m┌─ PORTFOLIO ({len(data['sites'])} sites) ────────────────────────────────────────────┐\033[0m""")
    
    if data["sites"]:
        print(f"│  {'Domain':<32} {'Score':<25} {'Defects':<10}│")
        print(f"│  {'─'*32} {'─'*25} {'─'*10}│")
        for site in data["sites"]:
            bar = score_bar(site["score"])
            print(f"│  {site['domain']:<32} {bar} {site['defects']:<10}│")
    else:
        print("│  No sites audited yet. Run: python3 wa.py run <url>             │")
    
    print(f"""\033[93m└──────────────────────────────────────────────────────────────────┘\033[0m

\033[93m┌─ QUICK ACTIONS ──────────────────────────────────────────────────┐\033[0m
│  [1] Run full pipeline    [2] Generate dashboard                 │
│  [3] List actions         [4] Run watchdog                       │
│  [5] AI summary           [6] Start portal                       │
│  [7] Outreach drafts      [8] System status                      │
│  [q] Quit                                                        │
\033[93m└──────────────────────────────────────────────────────────────────┘\033[0m
""")

def run_control_center():
    while True:
        render()
        choice = input("  \033[96mSelect [1-8/q]:\033[0m ").strip().lower()
        
        if choice == "q":
            print("\n  👋 Control center closed.")
            break
        elif choice == "1":
            url = input("  Enter URL: ").strip() or "https://example.co.nz"
            os.system(f"{sys.executable} run_all.py {url}")
        elif choice == "2":
            os.system(f"{sys.executable} audit-dashboard.py --output report.html")
            os.system("open report.html")
        elif choice == "3":
            os.system(f"{sys.executable} wa.py actions list")
            input("\n  Press Enter to continue...")
        elif choice == "4":
            os.system(f"{sys.executable} wa.py watchdog")
            input("\n  Press Enter to continue...")
        elif choice == "5":
            url = input("  Enter domain: ").strip() or "example.co.nz"
            os.system(f"{sys.executable} wa.py ai summary {url}")
            input("\n  Press Enter to continue...")
        elif choice == "6":
            print("\n  Starting portal at http://127.0.0.1:8080 (Ctrl+C to stop)")
            os.system(f"{sys.executable} -m website_auditor.portal.server")
        elif choice == "7":
            os.system(f"{sys.executable} wa.py outreach drafts")
            input("\n  Press Enter to continue...")
        elif choice == "8":
            os.system(f"{sys.executable} wa.py status")
            input("\n  Press Enter to continue...")

if __name__ == "__main__":
    run_control_center()
