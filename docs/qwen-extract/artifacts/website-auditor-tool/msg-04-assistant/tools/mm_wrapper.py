import subprocess
import json
import sys
from pathlib import Path

ALLOWED_COMMANDS = {
    "auditor_status": ["./mm", "--runtime"],
    "polish_status": ["./mm", "polish-status"],
    # ... map other IDs to exact argv lists
}

def execute_tool(tool_id, params=None):
    if tool_id not in ALLOWED_COMMANDS:
        return {"error": f"Tool '{tool_id}' not permitted"}
    
    cmd = ALLOWED_COMMANDS[tool_id]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    # Simple CLI interface for the Harness to call
    args = json.loads(sys.stdin.read())
    print(json.dumps(execute_tool(args['id'], args.get('params'))))
