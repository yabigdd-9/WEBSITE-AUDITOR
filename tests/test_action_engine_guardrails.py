"""Action-engine safety regressions: approvals, stop switch, local previews.

All tests run entirely offline. They never write a remote PR, send a message,
or probe a real website. The executor's three connectors are explicitly mocked.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from website_auditor.actions.executor import ActionExecutor
from website_auditor.actions.policy import PolicyEngine
from website_auditor.actions.registry import action_from_defect
from website_auditor.models import ActionStatus


def action(issue="Missing HSTS", domain="example.co.nz", environment="local"):
    return action_from_defect(
        domain, {"issue": issue, "severity": "medium"}, environment=environment
    )


class TestPolicyGuardrails(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.policy = PolicyEngine(Path(self.temp.name) / "nonexistent-policy.json")

    def test_default_mode_only_plans_and_requires_human_approval(self):
        item = action()
        decision = self.policy.evaluate(item)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.effect, "dry_run")
        self.assertTrue(decision.requires_approval)

    def test_emergency_stop_outweighs_dry_run_and_approval(self):
        result = self.policy.evaluate(action(), approved=True, authorized=True, paused=True)
        self.assertFalse(result.allowed)
        self.assertEqual(result.effect, "blocked")
        self.assertIn("Emergency stop", result.reason)

    def test_disabled_configuration_blocks_everything(self):
        self.policy.config["enabled"] = False
        result = self.policy.evaluate(action(), approved=True, authorized=True)
        self.assertFalse(result.allowed)
        self.assertIn("disabled", result.reason.lower())

    def test_unauthorized_action_never_executes_in_non_dry_run_mode(self):
        self.policy.config["mode"] = "guarded"
        result = self.policy.evaluate(action(), approved=True, authorized=False)
        self.assertFalse(result.allowed)
        self.assertIn("Authorization required", result.reason)

    def test_blocked_category_wins_even_if_human_approved(self):
        self.policy.config["mode"] = "guarded"
        item = action()
        item.category = "outreach_send"
        result = self.policy.evaluate(item, approved=True, authorized=True)
        self.assertFalse(result.allowed)
        self.assertEqual(result.effect, "blocked")

    def test_production_requires_explicit_permission(self):
        self.policy.config["mode"] = "guarded"
        result = self.policy.evaluate(
            action(environment="production"), approved=True, authorized=True
        )
        self.assertFalse(result.allowed)
        self.assertIn("Production changes disabled", result.reason)

    def test_high_risk_requires_approval_before_any_execution(self):
        self.policy.config["mode"] = "guarded"
        result = self.policy.evaluate(action(), approved=False, authorized=True)
        self.assertFalse(result.allowed)
        self.assertTrue(result.requires_approval)
        self.assertEqual(result.effect, "pending_approval")

    def test_explicitly_authorized_approved_policy_allows_local_execution(self):
        self.policy.config["mode"] = "guarded"
        result = self.policy.evaluate(action(), approved=True, authorized=True)
        self.assertTrue(result.allowed)
        self.assertEqual(result.effect, "execute")

    def test_no_automatic_execute_path_without_explicit_approval(self):
        self.policy.config["mode"] = "guarded"
        item = action("Missing page title")
        result = self.policy.evaluate(item, authorized=True)
        self.assertFalse(result.allowed)
        self.assertEqual(result.effect, "blocked")


class TestOfflineExecutor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / "action-outputs")
        self.executor.policy = PolicyEngine(self.root / "missing-policy.json")

    def test_proposal_is_idempotent_and_status_round_trips(self):
        first = action()
        self.assertEqual(self.executor.add_actions([first, first]), 1)
        self.assertEqual(self.executor.add_actions([first]), 0)
        summary = self.executor.status_summary()
        self.assertEqual(summary["total_actions"], 1)
        self.assertEqual(summary["status_counts"], {"proposed": 1})
        persisted = self.executor._load_actions()[0]
        self.assertEqual(persisted.domain, "example.co.nz")
        self.assertEqual(persisted.status, ActionStatus.PROPOSED)

    def test_demo_proposals_are_internal_and_repeat_safe(self):
        self.assertEqual(self.executor.propose_demo("example.co.nz"), 2)
        self.assertEqual(self.executor.propose_demo("example.co.nz"), 0)

    def test_dry_run_writes_local_evidence_without_external_connector(self):
        self.executor.add_actions([action()])
        with patch(
            "website_auditor.connectors.git_connector.GitConnector.execute_local_patch",
            side_effect=AssertionError("No connector should be called in dry-run"),
        ):
            report = self.executor.dry_run_all()
        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual(report["total_actions"], 1)
        self.assertEqual(self.executor._load_actions()[0].status, ActionStatus.DRY_RUN)
        saved = json.loads(self.executor.dry_run_report_path.read_text())
        self.assertEqual(saved, report)
        audit_rows = self.executor.audit.path.read_text().splitlines()
        self.assertEqual(len(audit_rows), 1)
        self.assertEqual(json.loads(audit_rows[0])["event"], "action_dry_run")

    def test_emergency_stop_blocks_even_local_simulation(self):
        self.executor.add_actions([action()])
        (self.executor.output_dir / "CANCELLED").touch()
        with patch(
            "website_auditor.connectors.git_connector.GitConnector.execute_local_patch",
            side_effect=AssertionError("Stop switch must prevent connector call"),
        ):
            rows = self.executor.execute_simulated()
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["result"]["allowed"])
        self.assertEqual(self.executor._load_actions()[0].status, ActionStatus.PROPOSED)

    def test_guarded_mode_without_authorization_blocks_simulation(self):
        self.executor.policy.config["mode"] = "guarded"
        self.executor.add_actions([action()])
        with patch(
            "website_auditor.connectors.git_connector.GitConnector.execute_local_patch",
            side_effect=AssertionError("Missing approval must block execution"),
        ):
            rows = self.executor.execute_simulated()
        self.assertFalse(rows[0]["result"]["allowed"])
        self.assertEqual(rows[0]["result"]["effect"], "blocked")

    def test_approved_dry_run_generates_only_a_local_preview(self):
        self.executor.add_actions([action("Missing page title")])
        with patch(
            "website_auditor.connectors.git_connector.GitConnector.execute_local_patch",
            return_value={"status": "preview", "committed": False},
        ) as preview:
            rows = self.executor.execute_simulated()
        preview.assert_called_once()
        self.assertEqual(rows[0]["result"]["committed"], False)
        self.assertEqual(self.executor._load_actions()[0].status, ActionStatus.SIMULATED)

    def test_wordpress_instruction_preview_uses_mock_no_network(self):
        self.executor.add_actions([action("Missing page title")])
        with patch(
            "website_auditor.connectors.wordpress_connector.WordPressConnector.execute_wordpress_fix",
            return_value={"status": "instructions_generated"},
        ) as connector:
            rows = self.executor.execute_wordpress_fix()
        connector.assert_called_once()
        self.assertEqual(rows[0]["result"]["status"], "instructions_generated")
        self.assertEqual(self.executor._load_actions()[0].status, ActionStatus.SIMULATED)

    def test_github_connector_is_only_a_local_preview(self):
        self.executor.add_actions([action("Missing HSTS")])
        with patch(
            "website_auditor.connectors.github_connector.GitHubConnector.execute_action",
            return_value={"status": "preview", "external_dispatch": False},
        ) as connector:
            rows = self.executor.execute_github_pr()
        connector.assert_called_once()
        self.assertFalse(rows[0]["result"]["external_dispatch"])
        self.assertEqual(self.executor._load_actions()[0].status, ActionStatus.SIMULATED)

    def test_report_import_failures_are_atomic_and_reported_locally(self):
        folder = self.root / "imports"
        for name in ("good", "invalid"):
            target = folder / name
            target.mkdir(parents=True)
            (target / "report.json").write_text("{}", encoding="utf-8")

        def import_report(path):
            if Path(path).parent.name == "invalid":
                raise ValueError("Invalid fixture")
            return {"domain": "example.co.nz", "defects": [{"defect": "Missing HSTS"}]}

        with patch("auditor_toolkit.actions.import_report", side_effect=import_report):
            with self.assertRaisesRegex(ValueError, "1 invalid reports"):
                self.executor.propose_from_remediations(folder)
        self.assertEqual(self.executor._load_actions(), [])
        errors = json.loads((self.executor.output_dir / "import-errors.json").read_text())
        self.assertEqual(len(errors), 1)
        self.assertIn("Invalid fixture", errors[0]["error"])

    def test_valid_report_import_creates_internal_review_action(self):
        report = self.root / "report.json"
        report.write_text("{}", encoding="utf-8")
        with patch("auditor_toolkit.actions.import_report", return_value={
            "domain": "example.co.nz", "defects": [
                {"defect": "Missing HSTS"},
                {"defect": "Missing page title"},
            ],
        }):
            created = self.executor.propose_from_remediations(report)
        self.assertEqual(created, 2)
        self.assertEqual(self.executor.status_summary()["status_counts"], {"proposed": 2})


if __name__ == "__main__":
    unittest.main()
