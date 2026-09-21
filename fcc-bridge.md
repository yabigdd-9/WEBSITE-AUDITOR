#!/usr/bin/env python3
"""
FCC Verification Script - Checks all FCC components and reports status.
"""

import subprocess
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

PROJECT = Path("/Users/dd/WEBSITE-AUDITOR")
FCC_URL = "http://127.0.0.1:8082"

def check(desc, ok, detail=""):
    icon = "✓" if ok else "✗"
    print(f"  [{icon}] {desc}" + (f": {detail}" if detail else ""))
    return ok

def main():
    print("=" * 60)
    print("  FCC Integration Verification")
    print("=" * 60)
    print()
    
    all_ok = True
    
    # ─── FCC Status ────────────────────────────────────
    print("[1] FCC Server Status")
    try:
        req = urllib.request.Request(f"{FCC_URL}/admin/api/status")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
            ok = resp.status == 200
            check("FCC API accessible", ok)
            check("Status", ok, data.get("status", "?"))
            check("Model", True, data.get("model", "?"))
            check("Provider", True, data.get("provider", "?"))
            
            cfg = sum(1 for p in data.get("provider_status", []) 
                     if p.get("status") == "configured")
            miss = sum(1 for p in data.get("provider_status", [])
                       if p.get("status") == "missing_key")
            total = cfg + miss
            check("API keys configured", cfg > 0, f"{cfg}/{total} providers")
            print(f"      → {cfg} configured, {miss} missing, {total} total")
    except Exception as e:
        check("FCC API accessible", False, str(e))
        data = None
    
    print()
    
    # ─── CLI Tools ─────────────────────────────────────
    print("[2] CLI Tools")
    tools = [
        ("Claude Code", "/Users/dd/.local/bin/claude"),
        ("Codex CLI", "/Users/dd/.local/bin/codex"),
        ("FCC-server", "/Users/dd/.local/bin/fcc-server"),
    ]
    
    for name, path in tools:
        exists = Path(path).exists()
        detail = ""
        if exists and path.suffix != ".app":
            try:
                r = subprocess.run([path, "--version"], 
                                  capture_output=True, text=True, timeout=5)
                detail = r.stdout.strip().split("\n")[0] if r.returncode == 0 else "?"
            except:
                detail = "installed"
        check(name, exists, detail)
    
    print()
    
    # ─── Bridge Scripts ────────────────────────────────
    print("[3] Bridge Scripts (money-machine/scripts/)")
    scripts = [
        "fcc-bridge.sh",
        "fcc-bridge.py", 
        "launch-fcc-all.sh",
        "fcc-bridge.md",
        "check-fcc-all.sh",
    ]
    
    for s in scripts:
        p = PROJECT / "money-machine" / "scripts" / s
        exists = p.exists()
        executable = p.stat().st_mode & 0o111 if exists else False
        detail = "executable" if (exists and executable) else ("exists" if exists else "MISSING")
        check(s, exists, detail)
    
    # Also check the docs at project root
    docs_path = PROJECT / "fcc-bridge.md"
    check("fcc-bridge.md (root)", docs_path.exists(), "documentation")
    
    print()
    
    # ─── Environment ───────────────────────────────────
    print("[4] Environment Files")
    for name in [".env", ".env.fcc"]:
        p = PROJECT / name
        exists = p.exists()
        size = p.stat().st_size if exists else 0
        check(name, exists, f"{size} bytes" if exists else "MISSING")
    
    print()
    
    # ─── Summary ───────────────────────────────────────
    print("=" * 60)
    issues = []
    if data is None:
        issues.append("FCC API not accessible")
    elif cfg == 0:
        issues.append("No API keys configured")
    
    for s in scripts:
        if not (PROJECT / "money-machine" / "scripts" / s).exists():
            issues.append(f"Missing script: {s}")
    
    if issues:
        print(f"\n{YELLOW}Issues to address:{NC}")
        for i in issues:
            print(f"  - {i}")
    else:
        print(f"\n{GREEN}All systems operational.{NC}")
    
    print("\nUsage:")
    print("  ./money-machine/scripts/launch-fcc-all.sh all    # Start everything")
    print("  ./money-machine/scripts/fcc-bridge.sh status     # Check status")
    print("  python money-machine/scripts/fcc-bridge.py start # Start via Python")
    print()
    
    return 0 if not issues else 1

if __name__ == "__main__":
    sys.exit(main())
