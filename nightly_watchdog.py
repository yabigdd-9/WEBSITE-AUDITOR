#!/usr/bin/env python3
"""
Nightly Watchdog: Scans all clients, detects regressions, and saves snapshots.
"""
import subprocess, sys, json, os
from pathlib import Path
from datetime import datetime, timezone

os.environ.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")

def run_nightly():
    print("\n" + "="*60)
    print("🌙 NIGHTLY WATCHDOG STARTING")
    print("="*60 + "\n")
    
    clients_file = Path("clients.txt")
    if not clients_file.exists():
        print("❌ clients.txt not found!")
        return
        
    domains = [line.strip() for line in clients_file.read_text().splitlines() if line.strip()]
    
    # Ensure outputs folder exists
    Path("outputs/remediations").mkdir(parents=True, exist_ok=True)
    Path("outputs/snapshots").mkdir(parents=True, exist_ok=True)
    
    regressions_found = []
    
    for url in domains:
        clean_domain = url.replace("https://", "").replace("http://", "").split("/")[0]
        print(f"\n🔍 Scanning: {clean_domain}")
        
        # 1. Run Audit (Silent)
        subprocess.run([sys.executable, "website_auditor.py", url], capture_output=True)
        
        # 2. Run Remediation to get JSON
        subprocess.run([sys.executable, "remediation-engine.py", "--domain", clean_domain, "--output-dir", "outputs/remediations"], capture_output=True)
        
        # 3. Load defects and run Watchdog
        try:
            from website_auditor.monitoring.watchdog import Watchdog
            wd = Watchdog()
            
            rem_file = Path(f"outputs/remediations/{clean_domain}-remediation.json")
            defects = []
            if rem_file.exists():
                data = json.loads(rem_file.read_text())
                defects = data.get("defects", data.get("issues", []))
                
            result = wd.run_check(clean_domain, defects)
            
            if result.get("first_audit"):
                print(f"   📸 Baseline snapshot saved.")
            else:
                regs = result.get("regressions", [])
                resolved = result.get("resolved", [])
                if regs:
                    print(f"   🚨 REGRESSION DETECTED: {len(regs)} new issues!")
                    regressions_found.append({"domain": clean_domain, "regressions": regs})
                if resolved:
                    print(f"   ✅ IMPROVEMENT: {len(resolved)} issues fixed.")
                if not regs and not resolved:
                    print(f"   ⏸️  No changes since last scan.")
        except Exception as e:
            print(f"   ⚠️ Watchdog error: {e}")

    # 4. Generate Nightly Report
    print("\n" + "="*60)
    print("📊 NIGHTLY SUMMARY")
    print("="*60)
    if regressions_found:
        print(f"🚨 ALERT: {len(regressions_found)} site(s) have new regressions!")
        for r in regressions_found:
            print(f"   - {r['domain']}: {', '.join(r['regressions'][:3])}")
            
        # Save alert to JSON for the dashboard to pick up
        Path("outputs/nightly_alerts.json").write_text(json.dumps(regressions_found, indent=2))
    else:
        print("✅ All client sites are stable. No regressions detected.")
        if Path("outputs/nightly_alerts.json").exists():
            Path("outputs/nightly_alerts.json").unlink()

if __name__ == "__main__":
    run_nightly()
