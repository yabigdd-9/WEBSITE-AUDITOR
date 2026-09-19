#!/bin/bash
set -e # Stop if any command fails

echo "🚀 Starting DeepSeek Harness Integration Setup..."

# 1. Git Branch Management
BRANCH_NAME="integration/deepseek-harness"
if git show-ref --verify --quiet refs/heads/$BRANCH_NAME; then
    echo "⚠️  Branch '$BRANCH_NAME' already exists. Switching to it."
    git checkout $BRANCH_NAME
else
    echo "✅ Creating new branch '$BRANCH_NAME' from current HEAD."
    git checkout -b $BRANCH_NAME
fi

# 2. Directory Structure
BASE_DIR="integrations/deepseek-harness"
echo "📁 Creating directory structure in $BASE_DIR..."
mkdir -p "$BASE_DIR"/{tools,policies,workflows,tests}

# 3. File Generation

# --- A. Policies ---
cat > "$BASE_DIR/policies/permissions.yml" << 'EOL'
version: "1.0"
policy_name: "safe_mm_bridge_v1"

allowed_operations:
  - id: auditor_status
    type: subprocess
    command_template: "./mm --runtime"
    timeout_seconds: 30
    output_format: json
    
  - id: polish_status
    type: subprocess
    command_template: "./mm polish-status"
    timeout_seconds: 30
    output_format: text

  - id: prospect_read
    type: sqlite_query
    database_path: "db/master_opportunity_database.db"
    allowed_tables: ["prospects", "audit_history"]
    write_access: false
    note: "Agents may query but never modify the master DB directly."

  - id: email_find
    type: subprocess
    command_template: "./mm email-find {prospect_id}"
    parameters:
      prospect_id: 
        type: string
        regex: "^PROS-[A-Z0-9]+$"
    timeout_seconds: 60
    network_scope: "allowlist_only"

  - id: outreach_plan_draft
    type: file_write
    base_directory: "outputs/drafts/"
    allowed_extensions: [".md", ".json"]
    max_file_size_kb: 512
    note: "Only draft generation. No sending."

forbidden_operations:
  - pattern: "*send*"
    reason: "External communication blocked in Phase A/B/C"
  - pattern: "*deploy*"
    reason: "Production writes prohibited"
  - pattern: "*.env*"
    reason: "Secret exposure prohibited"
  - pattern: "rm *"
    reason: "Destructive filesystem operations prohibited"
  - pattern: "curl * | sh"
    reason: "Remote code execution prohibited"
EOL

# --- B. Secure Wrapper Tool ---
cat > "$BASE_DIR/tools/mm_wrapper.py" << 'EOL'
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
EOL

# Make wrapper executable
chmod +x "$BASE_DIR/tools/mm_wrapper.py"

# --- C. Test Suite ---
cat > "$BASE_DIR/tests/test_security_bypass.py" << 'EOL'
import unittest
import json
import sys
from pathlib import Path

# Add parent dir to path to import wrapper
sys.path.append(str(Path(__file__).resolve().parent.parent))
from tools.mm_wrapper import execute_tool, SecurityViolation

class TestMMSecurityBridge(unittest.TestCase):

    def test_allowed_command_logic(self):
        """Verify that allowed commands pass validation logic."""
        request = {"id": "auditor_status", "params": {}}
        try:
            result = execute_tool(request)
            # If ./mm doesn't exist, it returns an error, but NOT a SecurityViolation
            if result.get("error"):
                self.assertNotIn("not in the allowlist", result["error"])
                self.assertNotIn("Security Violation", result["error"])
        except SecurityViolation:
            self.fail("Allowed command triggered SecurityViolation!")

    def test_forbidden_send_email_blocked(self):
        """Verify that 'send_email' is immediately rejected."""
        request = {"id": "send_email", "params": {"to": "test@example.com"}}
        result = execute_tool(request)
        self.assertFalse(result["success"])
        self.assertIn("not in the allowlist", result["error"])

    def test_critical_deny_pattern_blocked(self):
        """Verify that even if a tool was somehow added, critical strings block it."""
        request = {"id": "auditor_status", "params": {"note": "please rm -rf /"}}
        result = execute_tool(request)
        self.assertFalse(result["success"])
        self.assertIn("Critical deny pattern", result["error"])

    def test_unknown_tool_blocked(self):
        """Verify unknown tools are blocked."""
        request = {"id": "delete_database", "params": {}}
        result = execute_tool(request)
        self.assertFalse(result["success"])
        self.assertIn("not in the allowlist", result["error"])

if __name__ == '__main__':
    unittest.main()
EOL

# --- D. Documentation ---
cat > "$BASE_DIR/README.md" << 'EOL'
# DeepSeek Harness Integration

This module provides a secure, parallel reasoning layer for the WEBSITE-AUDITOR project.

## Core Components
1. **Policies**: `policies/permissions.yml` defines strictly bounded capabilities.
2. **Wrapper**: `tools/mm_wrapper.py` acts as the sole interface between LLM agents and the host system.
3. **Tests**: `tests/test_security_bypass.py` verifies that forbidden actions are blocked.

## Usage
Agents should invoke tools via the wrapper:
```python
from tools.mm_wrapper import execute_tool
result = execute_tool({"id": "auditor_status"})
