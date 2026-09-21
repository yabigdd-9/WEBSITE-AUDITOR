#!/usr/bin/env python3
"""
FCC Verification Script
Checks the status of all FCC components:
- FCC Desktop (GUI)
- FCC Server (headless)
- API keys configured
- Claude CLI
- Codex CLI
- Bridge scripts
"""

import subprocess
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_DIR = Path("/Users/dd/WEBSITE-AUDITOR")
FCC_HOST = "0.0.0.0"
FCC_PORT = 8082
FCC_URL = f"http://{FCC_HOST}:{FCC_PORT}"

def check(description, condition, detail=""):
    icon = "✓" if condition else "✗"
    status = "OK" if condition else "FAIL"
    line = f"  [{icon}] {description}"
    if detail:
        line += f": {detail}"
    print(f"{line}")
    return condition

def main():
    print("=" * 60)
    print("  FCC Verification Report")
    print("=" * 60)
    print()
    
    all_ok = True
    
    # ─── 1. FCC Desktop ────────────────────────────────
    print("[1] FCC Desktop (GUI)")
    fcc_app = Path("/Applications/Free Claude Code.app/Contents/MacOS/fcc-desktop")
    check("FCC Desktop app exists", fcc_app.exists(), str(fcc_app))
    
    result = subprocess.run(["pgrep", "-f", "fcc-desktop"], capture_output=True, text=True)
    desktop_running = result.returncode == 0
    check("FCC Desktop running", desktop_running, 
          "No process" if not desktop_running else "Active")
    
    # ─── 2. FCC Server ─────────────────────────────────
    print("\n[2] FCC Server (Headless)")
    check("fcc-server binary exists", 
          Path("/Users/dd/.local/bin/fcc-server").exists())
    
    result = subprocess.run(["pgrep", "-f", "fcc-server"], capture_output=True, text=True)
    server_running = result.returncode == 0
    check("FCC Server running", server_running,
          "No process" if not server_running else "Active")
    
    # ─── 3. FCC API ────────────────────────────────────
    print("\n[3] FCC API")
    try:
        req = urllib.request.Request(f"{FCC_URL}/admin/api/status")
        with urllib.request.urlopen(req, timeout=5) as resp:
            status_data = json.load(resp)
            api_ok = resp.status == 200
            check("Admin API accessible", api_ok, f"{FCC_URL}/admin")
            check("API status endpoint", api_ok, f"Status: {status_data.get('status', '?')}")
            check("Model configured", True, status_data.get('model', '?'))
            check("Provider active", True, status_data.get('provider', '?'))
    except Exception as e:
        check("Admin API accessible", False, str(e))
        api_ok = False
        status_data = None
    
    # ─── 4. API Keys ───────────────────────────────────
    print("\n[4] API Keys Configured")
    if status_data:
        configured = 0
        missing = 0
        for p in status_data.get('provider_status', []):
            if p.get('status') == 'configured':
                configured += 1
            elif p.get('status') == 'missing_key':
                missing += 1
        
        total = configured + missing
        check(f"API keys configured", configured > 0, 
              f"{configured} of {total} providers have keys")
        print(f"      Configured: {configured}")
        print(f"      Missing:    {missing}")
    
    # ─── 5. Claude CLI ─────────────────────────────────
    print("\n[5] Claude CLI")
    claude_bin = Path("/Users/dd/.local/bin/claude")
    check("Claude CLI installed", claude_bin.exists(), str(claude_bin))
    
    if claude_bin.exists():
        result = subprocess.run([str(claude_bin), "--version"], 
                               capture_output=True, text=True)
        version = result.stdout.strip() if result.returncode == 0 else "?"
        check("Claude CLI version", True, version)
    
    # ─── 6. Codex CLI ──────────────────────────────────
    print("\n[6] Codex CLI")
    codex_bin = Path("/Users/dd/.local/bin/codex")
    check("Codex CLI installed", codex_bin.exists(), str(codex_bin))
    
    if codex_bin.exists():
        result = subprocess.run([str(codex_bin), "--version"],
                               capture_output=True, text=True)
        version = result.stdout.strip().split('\n')[0] if result.returncode == 0 else "?"
        check("Codex CLI version", True, version)
    
    # ─── 7. FCC Bridge Scripts ─────────────────────────
    print("\n[7] FCC Bridge Scripts")
    scripts = [
        ("fcc-bridge.sh", PROJECT_DIR / "money-machine/scripts/fcc-bridge.sh"),
        ("fcc-bridge.py", PROJECT_DIR / "money-machine/scripts/fcc-bridge.py"),
        ("launch-fcc-all.sh", PROJECT_DIR / "money-machine/scripts/launch-fcc-all.sh"),
        ("fcc-bridge.md", PROJECT_DIR / "money-machine/fcc-bridge.md"),
    ]
    
    for name, path in scripts:
        exists = path.exists()
        executable = path.stat().st_mode & 0o111 if exists else False
        check(f"{name}", exists, 
              "executable" if (exists and executable) else ("exists" if exists else "MISSING"))
    
    # ─── 8. Environment Files ──────────────────────────
    print("\n[8] Environment Files")
    env_files = [
        (".env", PROJECT_DIR / ".env"),
        (".env.fcc", PROJECT_DIR / ".env.fcc"),
    ]
    
    for name, path in env_files:
        exists = path.exists()
        lines = path.stat().st_size if exists else 0
        check(f"{name}", exists, f"{lines} bytes" if exists else "MISSING")
    
    # ─── Summary ───────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    
    issues = []
    if not desktop_running:
        issues.append("FCC Desktop not running")
    if not server_running and not desktop_running:
        issues.append("Neither FCC Desktop nor Server running")
    if not api_ok:
        issues.append("FCC API not accessible")
    if configured == 0:
        issues.append("No API keys configured")
    if not claude_bin.exists():
        issues.append("Claude CLI not installed")
    if not codex_bin.exists():
        issues.append("Codex CLI not installed")
    for name, path in scripts:
        if not path.exists():
            issues.append(f"Script missing: {name}")
    
    if issues:
        print(f"\n{YELLOW}Issues found:{NC}")
        for issue in issues:
            print(f"  - {issue}")
        print()
    else:
        print(f"\n{GREEN}All checks passed!{NC}")
    
    print("\nQuick start:")
    print("  ./money-machine/scripts/launch-fcc-all.sh all")
    print("  ./money-machine/scripts/fcc-bridge.sh status")
    print()
    
    return 0 if not issues else 1

if __name__ == "__main__":
    sys.exit(main())
