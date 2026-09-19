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

# Define Allowed Commands Explicitly
# Format: tool_id -> list of arguments
ALLOWED_COMMANDS = {
    "auditor_status": ["./mm", "--runtime"],
    "polish_status": ["./mm", "polish-status"],
    "email_shadow": ["./mm", "email-shadow"],
}

# Patterns that trigger immediate hard-stop regardless of allowlist
CRITICAL_DENY_PATTERNS = [
    r".*send.*",
    r".*deploy.*",
    r".*\brm\b.*",
    r".*\.env.*",
    r".*sudo.*",
    r".*chmod.*",
]

class SecurityViolation(Exception):
    pass

def validate_request(tool_id: str, params: dict) -> bool:
    """Check if the requested tool_id is explicitly allowed."""
    # Check critical deny patterns first (defense in depth)
    combined_str = f"{tool_id} {json.dumps(params)}"
    for pattern in CRITICAL_DENY_PATTERNS:
        if re.search(pattern, combined_str, re.IGNORECASE):
            raise SecurityViolation(f"Critical deny pattern matched: {pattern}")

    if tool_id not in ALLOWED_COMMANDS:
        raise SecurityViolation(f"Tool '{tool_id}' is not in the allowlist.")
    
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

        # 1. Validate Against Allowlist & Deny Lists
        validate_request(tool_id, request.get("params", {}))

        # 2. Construct Command Safely (List based, no shell string)
        cmd_list = ALLOWED_COMMANDS[tool_id].copy()
        
        # Handle parameter substitution if needed (basic implementation)
        # For complex cases, this should be expanded carefully
        if "{prospect_id}" in cmd_list:
            pid = request.get("params", {}).get("prospect_id")
            if not pid:
                 raise ValueError("prospect_id required for email_find")
            cmd_list = [c.replace("{prospect_id}", pid) for c in cmd_list]

        # 3. Execute Subprocess
        # Using shell=False is critical for security
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
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out"}
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
