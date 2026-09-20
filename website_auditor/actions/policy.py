"""Policy engine for automatic actions."""
from __future__ import annotations

import json
from pathlib import Path

from ..models import Action, Mode, PolicyDecision
from .store import KillSwitch


DEFAULT_CONFIG = {
    "enabled": True,
    "execution_enabled": False,
    "mode": "dry_run",
    "allow_production_changes": False,
    "allow_external_emails": False,
    "allow_external_connectors": False,
    "auto_approve_risks": ["low"],
    "require_approval_risks": ["medium", "high", "critical"],
    "max_actions_per_hour": 20,
    "environments_allowed_for_auto": ["local", "staging"],
    "blocked_categories": ["dns_write", "tls_install", "production_deploy", "outreach_send"],
    "secret_env_allowlist": [],
}


class PolicyEngine:
    def __init__(
        self,
        path: str | Path = "action-policy.json",
        *,
        kill_switch: KillSwitch | None = None,
    ):
        self.path = Path(path)
        self.config = dict(DEFAULT_CONFIG)
        if self.path.exists():
            loaded = json.loads(self.path.read_text())
            if isinstance(loaded, dict):
                self.config.update(loaded)
        self.kill_switch = kill_switch or KillSwitch("outputs/actions/KILL_SWITCH")

    @property
    def mode(self) -> Mode:
        try:
            return Mode(str(self.config.get("mode", "dry_run")))
        except ValueError:
            return Mode.DISABLED

    def evaluate(
        self,
        action: Action,
        *,
        approved: bool = False,
        authorized: bool = False,
        compliance_ok: bool = False,
    ) -> PolicyDecision:
        if self.kill_switch.active or self.mode is Mode.EMERGENCY_STOP:
            return PolicyDecision(False, "blocked", "Emergency stop is active.")

        if not self.config.get("enabled", True) or self.mode is Mode.DISABLED:
            return PolicyDecision(False, "blocked", "Action engine is disabled.")

        # Dry-run is intentionally evaluated before live-effect gates: blocked/high-risk
        # actions may be simulated, but cannot cause external effects.
        if self.mode is Mode.DRY_RUN:
            return PolicyDecision(
                True,
                "dry_run",
                "Dry-run mode: plan/log only; no external or local execution.",
                requires_approval=action.requires_approval,
                requires_authorization=action.requires_authorization,
            )

        if not self.config.get("execution_enabled", False):
            return PolicyDecision(False, "blocked", "Execution is disabled by policy.")

        if action.environment == "production" and not self.config.get("allow_production_changes", False):
            return PolicyDecision(False, "blocked", "Production changes are disabled.")

        if action.category in set(self.config.get("blocked_categories", [])):
            return PolicyDecision(False, "blocked", f"Category '{action.category}' is blocked.")

        if action.connector == "esp" and not self.config.get("allow_external_emails", False):
            return PolicyDecision(False, "blocked", "External email sending is disabled.")

        if action.connector != "local" and not self.config.get("allow_external_connectors", False):
            return PolicyDecision(False, "blocked", "External connectors are disabled.")

        required_risks = set(self.config.get("require_approval_risks", []))
        if (action.requires_approval or action.risk.value in required_risks) and not approved:
            return PolicyDecision(
                False, "blocked", "Action requires explicit approval.", requires_approval=True
            )

        if action.requires_authorization and not authorized:
            return PolicyDecision(
                False, "blocked", "Domain/action scope is not authorized.", requires_authorization=True
            )

        if action.category == "outreach_send" and not compliance_ok:
            return PolicyDecision(False, "blocked", "Outreach compliance/suppression gate not satisfied.")

        if self.mode is Mode.AUTONOMOUS:
            allowed_envs = set(self.config.get("environments_allowed_for_auto", ["local"]))
            if action.environment not in allowed_envs:
                return PolicyDecision(False, "blocked", "Environment is not allowed for autonomous actions.")

        return PolicyDecision(True, "execute", "Policy gates passed.")
