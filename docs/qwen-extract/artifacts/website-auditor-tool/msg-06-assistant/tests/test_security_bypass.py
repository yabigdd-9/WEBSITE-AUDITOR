import unittest
import json
import subprocess
import os
from pathlib import Path

# Add parent dir to path to import wrapper
sys.path.append(str(Path(__file__).resolve().parent.parent))
from tools.mm_wrapper import execute_tool, SecurityViolation

class TestMMSecurityBridge(unittest.TestCase):

    def test_allowed_command_execution(self):
        """Verify that allowed commands like 'auditor_status' do not raise SecurityViolation."""
        request = {"id": "auditor_status", "params": {}}
        # Note: This will actually try to run ./mm. In a real CI, we'd mock subprocess.
        # Here we just check the logic flow doesn't crash on validation.
        try:
            # We expect it might fail due to missing ./mm in test env, 
            # but it should NOT fail due to SecurityViolation.
            result = execute_tool(request)
            self.assertNotIn("Security Violation", str(result.get("error", "")))
        except SecurityViolation:
            self.fail("Allowed command triggered SecurityViolation!")

    def test_forbidden_send_email_blocked(self):
        """Verify that 'send_email' is immediately rejected."""
        request = {"id": "send_email", "params": {"to": "test@example.com"}}
        result = execute_tool(request)
        self.assertFalse(result["success"])
        self.assertIn("not in the allowlist", result["error"])

    def test_forbidden_shell_injection_blocked(self):
        """Verify that attempts to inject shell commands via IDs are blocked."""
        request = {"id": "auditor_status; rm -rf /", "params": {}}
        result = execute_tool(request)
        self.assertFalse(result["success"])
        self.assertIn("not in the allowlist", result["error"])

    def test_missing_id_handled_gracefully(self):
        """Verify malformed requests don't crash the wrapper."""
        request = {"params": {}}
        result = execute_tool(request)
        self.assertFalse(result["success"])
        self.assertIn("Missing 'id'", result["error"])

if __name__ == '__main__':
    unittest.main()
