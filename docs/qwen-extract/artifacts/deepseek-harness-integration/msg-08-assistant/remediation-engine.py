cat << 'EOF' > integrations/deepseek-harness/tools/mm_bridge.py
"""
Safe MM Bridge for DeepSeek Harness
Purpose: Provide narrow, validated interfaces to existing WEBSITE-AUDITOR scripts.
Security: Input sanitization, timeout enforcement, no raw shell passthrough.
"""

import subprocess
import json
import os
import sys
from typing import Dict, Any, Optional

# Paths relative to repo root
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
AUDIT_SCRIPT = os.path.join(ROOT_DIR, 'website_auditor.py')
PIPELINE_SCRIPT = os.path.join(ROOT_DIR, 'full-pipeline.py')
REMEDIATION_SCRIPT = os.path.join(ROOT_DIR, 'remediation-engine.py')

class MMBridgeError(Exception):
    pass

def _run_script(script_path: str, args: list, timeout: int = 300) -> Dict[str, Any]:
    """Securely executes a Python script and returns structured output."""
    if not os.path.exists(script_path):
        raise MMBridgeError(f"Script not found: {script_path}")
    
    cmd = ['python3', script_path] + args
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=ROOT_DIR
        )
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr.strip(),
                "exit_code": result.returncode
            }
            
        return {
            "success": True,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip() # Capture warnings but don't fail
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "TIMEOUT_EXPIRED"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- Tool Definitions for Harness Registration ---

def tool_get_audit_status(prospect_url: str) -> Dict[str, Any]:
    """
    Runs website_auditor.py on a single URL.
    Access: Read Only (writes to audits/)
    """
    if not prospect_url.startswith(('http://', 'https://')):
        return {"success": False, "error": "INVALID_URL_FORMAT"}
        
    print(f"[BRIDGE] Auditing: {prospect_url}", file=sys.stderr)
    return _run_script(AUDIT_SCRIPT, [prospect_url])

def tool_run_full_pipeline(brief_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Runs full-pipeline.py. 
    Note: In Shadow mode, this might be dry-run or limited scope.
    """
    args = ['--all'] # Default behavior from KB
    if brief_path:
        # Assuming pipeline accepts a specific input file flag
        args.extend(['--input-file', brief_path])
        
    print(f"[BRIDGE] Running Full Pipeline...", file=sys.stderr)
    return _run_script(PIPELINE_SCRIPT, args, timeout=600)

def tool_generate_remediations(domain_filter: Optional[str] = None) -> Dict[str, Any]:
    """
    Generates fix suggestions based on existing audits.
    """
    args = ['--all', '--output-dir', 'outputs/remediations']
    if domain_filter:
        args.extend(['--domain', domain_filter])
        
    print(f"[BRIDGE] Generating Remediations...", file=sys.stderr)
    return _run_script(REMEDIATION_SCRIPT, args)

def tool_list_pending_outreach() -> Dict[str, Any]:
    """
    Reads outreach-ranking.csv to show what's ready for human review.
    Access: Read Only
    """
    csv_path = os.path.join(ROOT_DIR, 'outputs', 'outreach-ranking.csv')
    if not os.path.exists(csv_path):
        return {"success": True, "data": [], "message": "No outreach list generated yet."}
        
    try:
        with open(csv_path, 'r') as f:
            lines = f.readlines()[:50] # Limit context size
        return {"success": True, "data_preview": lines}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Export tools for Harness loader
TOOLS_EXPORT = {
    "get_audit_status": tool_get_audit_status,
    "run_full_pipeline": tool_run_full_pipeline,
    "generate_remediations": tool_generate_remediations,
    "list_pending_outreach": tool_list_pending_outreach
}
EOF
