from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from ..models import Action, Risk

DEFAULT_POLICY: dict[str, Any] = {"enabled": True, "mode": "dry_run", "allow_production_changes": False, "allow_external_emails": False, "allow_external_connectors": False, "auto_approve_risks": ["low"], "require_approval_risks": ["medium", "high", "critical"], "environments_allowed_for_auto": ["local", "staging"], "blocked_categories": ["dns_write", "tls_install", "production_deploy", "outreach_send"]}

@dataclass
class Decision:
    allowed: bool; effect: str; reason: str; requires_approval: bool = False
    def to_dict(self) -> dict[str, Any]: return {"allowed": self.allowed, "effect": self.effect, "reason": self.reason, "requires_approval": self.requires_approval}

class PolicyEngine:
    def __init__(self, path: Path | str = "config/actions.json") -> None:
        self.path = Path(path)
        self.config = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else dict(DEFAULT_POLICY)

    def evaluate(self, action: Action, *, approved: bool = False, authorized: bool = False, paused: bool = False) -> Decision:
        if paused: return Decision(False, "blocked", "Emergency stop is active.")
        if not self.config.get("enabled", False): return Decision(False, "blocked", "Actions are disabled.")
        if self.config.get("mode") == "dry_run": return Decision(True, "dry_run", "Dry-run mode: plan and log only.", requires_approval=action.requires_approval)
        if action.requires_authorization and not authorized: return Decision(False, "blocked", "Authorization required.")
        if action.category in self.config.get("blocked_categories", []): return Decision(False, "blocked", f"Category '{action.category}' blocked.")
        if action.environment == "production" and not self.config.get("allow_production_changes", False): return Decision(False, "blocked", "Production changes disabled.")
        if action.risk.value in self.config.get("require_approval_risks", []) and not approved: return Decision(False, "pending_approval", f"Risk '{action.risk.value}' requires approval.", requires_approval=True)
        if approved: return Decision(True, "execute", "Approved action allowed.")
        return Decision(False, "blocked", "No policy path allows execution.")
