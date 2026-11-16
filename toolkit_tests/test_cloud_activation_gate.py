"""Fail-closed activation gate regression tests; no keys or network used."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/cloud-prospect-pipeline.yml"


def configuration_script() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = doc["jobs"]["configuration"]["steps"]
    matching = [step["run"] for step in steps
                if step.get("name") == "Report actual activation separately from offline tests"]
    if len(matching) != 1:
        raise AssertionError("Exactly one activation configuration gate required")
    return matching[0]


class TestActivationBranchGate(unittest.TestCase):
    def check_gate(self, *, ref, event, enabled, key):
        with tempfile.TemporaryDirectory() as temp:
            summary = Path(temp) / "summary.md"
            env = dict(os.environ)
            env.update({
                "GITHUB_REF": ref,
                "GITHUB_EVENT_NAME": event,
                "PIPELINE_ENABLED": enabled,
                "STATE_KEY_CONFIGURED": key,
                "GITHUB_STEP_SUMMARY": str(summary),
            })
            result = subprocess.run(
                ["bash", "-e", "-c", configuration_script()],
                env=env, text=True, capture_output=True, timeout=5, check=False,
            )
            return result.returncode, result.stdout, summary.read_text() if summary.exists() else ""

    def test_manual_dispatch_feature_branch_fails_even_with_valid_config(self):
        code, output, summary = self.check_gate(
            ref="refs/heads/feature", event="workflow_dispatch",
            enabled="true", key="true",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("Run this workflow on master", output)
        self.assertIn("wrong branch", summary)

    def test_master_manual_dispatch_refuses_disabled_worker(self):
        code, output, summary = self.check_gate(
            ref="refs/heads/master", event="workflow_dispatch",
            enabled="false", key="true",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("WA_PIPELINE_ENABLED is not true", output)
        self.assertIn("DISABLED", summary)

    def test_master_schedule_disabled_is_not_reported_as_active(self):
        code, output, summary = self.check_gate(
            ref="refs/heads/master", event="schedule",
            enabled="false", key="true",
        )
        self.assertEqual(code, 0)
        self.assertIn("DISABLED", summary)
        self.assertNotIn("configured; verify", summary)

    def test_master_manual_dispatch_refuses_missing_key(self):
        code, output, summary = self.check_gate(
            ref="refs/heads/master", event="workflow_dispatch",
            enabled="true", key="false",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("WA_PIPELINE_STATE_KEY must be configured", output)
        self.assertIn("BLOCKED", summary)

    def test_master_configured_only_claims_configuration_not_worker_success(self):
        code, output, summary = self.check_gate(
            ref="refs/heads/master", event="workflow_dispatch",
            enabled="true", key="true",
        )
        self.assertEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("verify worker steps and checkpoint upload", summary)
        self.assertNotIn("worker: ACTIVE", summary)

    def test_master_push_requires_enabled_worker(self):
        code, output, summary = self.check_gate(
            ref="refs/heads/master", event="push", enabled="false", key="true",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("WA_PIPELINE_ENABLED is not true", output)
        self.assertIn("DISABLED", summary)

    def test_master_configured_push_can_continue_checkpoint(self):
        code, output, summary = self.check_gate(
            ref="refs/heads/master", event="push", enabled="true", key="true",
        )
        self.assertEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("verify worker steps and checkpoint upload", summary)


if __name__ == "__main__":
    unittest.main()
