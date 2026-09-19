import subprocess
import sys
import os
import json
from typing import Dict, Any, Optional

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
AUDIT_SCRIPT = os.path.join(ROOT_DIR, 'website_auditor.py')
PIPELINE_SCRIPT = os.path.join(ROOT_DIR, 'full-pipeline.py')
REMEDIATION_SCRIPT = os.path.join(ROOT_DIR, 'remediation-engine.py')

class MMBridgeError(Exception):
    pass

def _execute_python_script(script_path: str, args: list, timeout_sec: int = 300) -> Dict[str, Any]:
    """
    Safely executes a Python script in the repo root.
    Captures stdout/stderr. Returns structured result.
    """
    if not os.path.exists(script_path):
        raise MMBridgeError(f"Script not found: {script_path}")
    
    cmd = [sys.executable, script_path] + args
    
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=ROOT_DIR
        )
        
        success = proc.returncode == 0
        return {
            "success": success,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "TIMEOUT", "stdout": "", "stderr": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "stdout": "", "stderr": ""}

# --- Public Tools for Harness ---

def tool_audit_site(url: str) -> Dict[str, Any]:
    """
    Runs single-site audit.
    Maps to: python3 website_auditor.py <url>
    """
    if not url.startswith(('http://', 'https://')):
        return {"success": False, "error": "INVALID_URL"}
        
    res = _execute_python_script(AUDIT_SCRIPT, [url])
    if res['success']:
        # Try to locate the generated JSON in audits/ folder based on URL hash/name convention
        # For simplicity in this bridge, we assume the script prints the path or we scan latest
        return {"success": True, "message": "Audit completed", "raw_output": res['stdout']}
    return res

def tool_run_remediation(domain_filter: Optional[str] = None) -> Dict[str, Any]:
    """
    Generates fix suggestions.
    Maps to: python3 remediation-engine.py --all [--domain X]
    """
    args = ['--all']
    if domain_filter:
        args.extend(['--domain', domain_filter])
        
    return _execute_python_script(REMEDIATION_SCRIPT, args, timeout_sec=600)

def tool_get_latest_audit_json(domain: str) -> Dict[str, Any]:
    """
    Reads the audit JSON for a specific domain.
    Security: Sanitizes domain input to prevent path traversal.
    """
    # Basic sanitization
    safe_domain = "".join(c for c in domain if c.isalnum() or c in ('.', '-', '_')).lower()
    audit_path = os.path.join(ROOT_DIR, 'audits', f"{safe_domain}.json")
    
    if not os.path.exists(audit_path):
        return {"success": False, "error": "AUDIT_NOT_FOUND"}
        
    try:
        with open(audit_path, 'r') as f:
            data = json.load(f)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

TOOLS_EXPORT = {
    "audit_site": tool_audit_site,
    "run_remediation": tool_run_remediation,
    "get_latest_audit_json": tool_get_latest_audit_json
}
