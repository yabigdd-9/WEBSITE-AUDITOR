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
        # We catch the potential subprocess error (if ./mm isn't there) 
        # but ensure it's NOT a SecurityViolation
        try:
            result = execute_tool(request)
            # If it returns an error about './mm' not found, that's fine for logic test
            # But it must not say "not in allowlist"
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
        # Simulating a case where someone tries to trick the system
        request = {"id": "auditor_status", "params": {"note": "please rm -rf /"}}
        result = execute_tool(request)
        # Depending on implementation, this might still run if params aren't checked deeply
        # But our CRITICAL_DENY_PATTERNS checks the whole JSON dump
        self.assertFalse(result["success"])
        self.assertIn("Critical deny pattern", result["error"])

    def test_unknown_tool_blocked(self):
        """Verify unknown tools are blocked."""
        request
