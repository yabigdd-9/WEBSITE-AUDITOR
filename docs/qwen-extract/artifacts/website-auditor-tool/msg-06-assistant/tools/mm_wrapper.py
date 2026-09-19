#!/usr/bin/env python3
"""
Secure mm Tool Bridge for DeepSeek Harness
Enforces strict allowlists and prevents dangerous shell expansions.
"""

import json
import subprocess
import sys
import re
from pathlib import Path

# Load Policies
POLICY_PATH = Path(__file__).parent.parent / "policies" / "permissions.yml"
ALLOWED_COMMANDS = {
    "auditor_status": ["./mm", "--runtime"],
    "polish_status": ["./mm", "polish-status"],
}

# Regex patterns for immediate denial
DENY_PATTERNS = [
    r".*send.*",
    r".*deploy.*",
    r".*\brm\b.*",
    r".*\.env.*",
    r".*sudo.*",
]

class SecurityViolation(Exception):
    pass

def validate_request(tool_id: str, params: dict) -> bool:
    """Check if the requested tool_id is explicitly allowed."""
    if tool_id not in ALLOWED_COMMANDS:
        raise SecurityViolation(f"Tool '{tool_id}' is not in the allowlist.")
    
    # Additional param validation could go here (e.g., SQL injection checks)
    return True

def execute_tool(request: dict) -> dict:
    """
    Execute a tool request securely.
    Input format: {"id": "auditor_status", "params": {}}
    Output format: {"stdout": "...", "stderr": "...", "returncode": 0, "error": null}
    """
    try:
        tool_id = request.get("id")
        if not tool_id:
            raise ValueError("Missing 'id' field in request")

        # 1. Validate Against Allowlist
        validate_request(tool_id, request.get("params", {}))

        # 2. Construct Command Safely (No shell=True!)
        cmd_list = ALLOWED_COMMANDS[tool_id]
        
        # Append parameters if needed (simple string interpolation for now, ideally use arg parsing)
        # For ./mm --runtime, no extra args usually. 
        
        # 3. Execute Subprocess
        result = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.cwd()) # Ensure we run in repo root
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "error": None
        }

    except SecurityViolation as e:
        return {"success": False, "error": f"Security Violation: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Execution Error: {str(e)}"}

if __name__ == "__main__":
    # Read JSON input from stdin
    raw_input = sys.stdin.read()
    try:
        request_data = json.loads(raw_input)
        response = execute_tool(request_data)
        print(json.dumps(response))
    except json.JSONDecodeError:
        print(json.dumps({"success": False, "error": "Invalid JSON input"}))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
