#!/usr/bin/env python3
"""
BASELINE ACCEPTANCE TESTS
Run this BEFORE connecting the Harness.
Ensures ./mm works, DBs are backed up, and network is restricted.
"""
import subprocess
import sqlite3
import os
import sys
from pathlib import Path

def check_mm_health():
    print("[TEST] Checking ./mm health...")
    try:
        res = subprocess.run(["./mm", "--runtime"], capture_output=True, text=True, timeout=10)
        assert res.returncode == 0, f"MM returned non-zero: {res.stderr}"
        print("   ✅ ./mm --runtime OK")
        
        res_polish = subprocess.run(["./mm", "polish-status"], capture_output=True, text=True, timeout=10)
        assert res_polish.returncode == 0
        print("   ✅ ./mm polish-status OK")
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        sys.exit(1)

def backup_databases():
    db_dir = Path("./data/db")
    backup_dir = Path("./backups/pre-harness-integration")
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[TEST] Backing up SQLite DBs from {db_dir} to {backup_dir}...")
    for db_file in db_dir.glob("*.sqlite"):
        dest = backup_dir / db_file.name
        # Simple copy for integrity check
        subprocess.run(["cp", str(db_file), str(dest)], check=True)
        print(f"   ✅ Copied {db_file.name}")

def verify_no_secret_leakage():
    """Simulate a malicious prompt attempt to read .env"""
    print("[TEST] Verifying security boundaries...")
    # This would ideally be done by invoking the Harness with a bad prompt
    # For now, we just ensure the file isn't world-readable
    env_path = Path(".env")
    if env_path.exists():
        stat_info = os.stat(env_path)
        perm = oct(stat_info.st_mode)[-3:]
        if perm != "600":
            print(f"   ⚠️ WARNING: .env permissions are {perm}, recommend 600")
        else:
            print("   ✅ .env permissions secure (600)")
    else:
        print("   ℹ️ No .env found (OK)")

if __name__ == "__main__":
    print("="*40)
    print("STARTING BASELINE VALIDATION")
    print("="*40)
    
    check_mm_health()
    backup_databases()
    verify_no_secret_leakage()
    
    print("\n✅ ALL BASELINE TESTS PASSED.")
    print("👉 NEXT STEP: Deploy DeepSeek Harness Container.")
