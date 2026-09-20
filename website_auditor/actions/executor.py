"""Action proposal, dry-run, approval, execution, verification and rollback."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..connectors.local import LocalConnector, UnavailableConnector
from ..models import Action, ActionStatus
from .audit_log import AuditLog
from .policy import PolicyEngine
from .registry import action_from_finding, build_action
from .store import (
    ActionStore,
    ApprovalStore,
    AuthorizationStore,
    IdempotencyStore,
    KillSwitch,
    RateLimitStore,
)


class ActionExecutor:
    def __init__(
        self,
        output_dir: str | Path = "outputs/actions",
        *,
        config_path: str | Path = "action-policy.json",
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.actions = ActionStore(self.output_dir / "actions.json")
        self.approvals = ApprovalStore(self.output_dir / "approvals.json")
        self.authorizations = AuthorizationStore(self.output_dir / "authorizations.json")
        self.idempotency = IdempotencyStore(self.output_dir / "idempotency.json")
        self.rate_limit = RateLimitStore(self.output_dir / "rate_limit.json")
        self.kill_switch = KillSwitch(self.output_dir / "KILL_SWITCH")
        self.audit_log = AuditLog(self.output_dir / "audit.ndjson")
        self.policy = PolicyEngine(config_path, kill_switch=self.kill_switch)

    def _connector(self, name: str):
        if name == "local":
            return LocalConnector(self.output_dir / "local")
        return UnavailableConnector(name)

    def propose(self, action: Action) -> Action:
        existing = self.actions.get(action.action_id)
        if existing:
            return existing
        self.actions.put(action)
        self.audit_log.append(
            "action_proposed",
            action_id=action.action_id,
            action_type=action.action_type,
            domain=action.domain,
            risk=action.risk.value,
            connector=action.connector,
        )
        return action

    def propose_demo(self, domain: str = "example.co.nz") -> list[Action]:
        demo = [
            build_action("report.generate", domain=domain, payload={"source": "demo"}),
            build_action("ticket.create", domain=domain, payload={"message": "Demo local ticket"}),
            build_action(
                "outreach.send",
                domain=domain,
                payload={"recipient": "demo@example.invalid", "compliance_ok": False},
            ),
        ]
        return [self.propose(item) for item in demo]

    def propose_from_remediations(self, root: str | Path) -> int:
        root = Path(root)
        if not root.exists():
            return 0
        created = 0
        for path in sorted(root.rglob("*.json")):
            if "summary" in path.name:
                continue
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            domain = str(data.get("domain") or path.stem.replace("-remediation", ""))
            findings = data.get("actions") or data.get("findings") or data.get("defects") or []
            if not isinstance(findings, list):
                continue
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                action = action_from_finding(domain, finding)
                if self.actions.get(action.action_id) is None:
                    created += 1
                self.propose(action)
        return created

    def dry_run_all(self) -> dict[str, Any]:
        report: list[dict[str, Any]] = []
        for action in self.actions.all():
            approved = self.approvals.is_approved(action.action_id)
            authorized = (
                not action.requires_authorization
                or self.authorizations.is_authorized(action.domain, action.category)
            )
            decision = self.policy.evaluate(
                action,
                approved=approved,
                authorized=authorized,
                compliance_ok=bool(action.payload.get("compliance_ok")),
            )
            connector = self._connector(action.connector)
            connector_result = connector.dry_run(action) if decision.allowed else None
            action.status = ActionStatus.DRY_RUN if decision.allowed else ActionStatus.BLOCKED
            self.actions.put(action)
            record = {
                "action_id": action.action_id,
                "action_type": action.action_type,
                "decision": decision.to_dict(),
                "connector_result": connector_result.to_dict() if connector_result else None,
            }
            report.append(record)
            self.audit_log.append("action_dry_run", **record)

        payload = {"mode": self.policy.mode.value, "count": len(report), "actions": report}
        (self.output_dir / "dry_run_report.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str)
        )
        return payload

    def approve(self, action_id: str, *, actor: str, reason: str = "") -> dict:
        action = self.actions.get(action_id)
        if not action:
            raise KeyError(f"unknown action: {action_id}")
        record = self.approvals.set(action_id, approved=True, actor=actor, reason=reason)
        action.status = ActionStatus.APPROVED
        self.actions.put(action)
        self.audit_log.append("action_approved", **record)
        return record

    def reject(self, action_id: str, *, actor: str, reason: str = "") -> dict:
        action = self.actions.get(action_id)
        if not action:
            raise KeyError(f"unknown action: {action_id}")
        record = self.approvals.set(action_id, approved=False, actor=actor, reason=reason)
        action.status = ActionStatus.REJECTED
        self.actions.put(action)
        self.audit_log.append("action_rejected", **record)
        return record

    def authorize(self, domain: str, *, scopes: list[str], actor: str, note: str = "") -> dict:
        record = self.authorizations.authorize(domain, scopes=scopes, actor=actor, note=note)
        self.audit_log.append("authorization_recorded", **record)
        return record

    def execute(self, action_id: str) -> dict[str, Any]:
        action = self.actions.get(action_id)
        if not action:
            raise KeyError(f"unknown action: {action_id}")

        approved = self.approvals.is_approved(action_id)
        authorized = (
            not action.requires_authorization
            or self.authorizations.is_authorized(action.domain, action.category)
        )
        decision = self.policy.evaluate(
            action,
            approved=approved,
            authorized=authorized,
            compliance_ok=bool(action.payload.get("compliance_ok")),
        )
        self.audit_log.append(
            "action_evaluated",
            action_id=action_id,
            decision=decision.to_dict(),
            domain=action.domain,
        )

        if decision.effect == "dry_run":
            action.status = ActionStatus.DRY_RUN
            self.actions.put(action)
            return {"action": action.to_dict(), "decision": decision.to_dict(), "executed": False}

        if not decision.allowed:
            action.status = ActionStatus.BLOCKED
            self.actions.put(action)
            return {"action": action.to_dict(), "decision": decision.to_dict(), "executed": False}

        if self.idempotency.contains(action.idempotency_key):
            return {
                "action": action.to_dict(),
                "decision": decision.to_dict(),
                "executed": False,
                "idempotent": True,
                "reason": "Idempotency key already completed.",
            }

        limit = int(self.policy.config.get("max_actions_per_hour", 20))
        if not self.rate_limit.allowed(limit):
            action.status = ActionStatus.BLOCKED
            self.actions.put(action)
            return {
                "action": action.to_dict(),
                "decision": {"allowed": False, "effect": "blocked", "reason": "Rate limit reached."},
                "executed": False,
            }

        self.rate_limit.reserve()
        action.status = ActionStatus.EXECUTING
        self.actions.put(action)
        connector = self._connector(action.connector)
        result = connector.execute(action)
        verification = connector.verify(action, result)

        if result.ok and verification.get("ok"):
            action.status = ActionStatus.VERIFIED
            self.idempotency.mark(action.idempotency_key, action.action_id)
        elif result.ok:
            action.status = ActionStatus.EXECUTED
        else:
            action.status = ActionStatus.FAILED
        self.actions.put(action)

        payload = {
            "action": action.to_dict(),
            "decision": decision.to_dict(),
            "result": result.to_dict(),
            "verification": verification,
            "executed": result.ok,
        }
        self.audit_log.append("action_execution_finished", action_id=action_id, result=payload)
        return payload

    def rollback(self, action_id: str) -> dict[str, Any]:
        action = self.actions.get(action_id)
        if not action:
            raise KeyError(f"unknown action: {action_id}")
        if not action.reversible:
            raise ValueError("action is not reversible")
        if action.connector != "local":
            raise PermissionError("only the safe local connector supports rollback in this build")
        result = self._connector(action.connector).rollback(action)
        action.status = ActionStatus.ROLLED_BACK
        self.actions.put(action)
        payload = {"action": action.to_dict(), "result": result.to_dict()}
        self.audit_log.append("action_rolled_back", action_id=action_id, result=payload)
        return payload

    def status_summary(self) -> dict[str, Any]:
        actions = self.actions.all()
        counts: dict[str, int] = {}
        for action in actions:
            counts[action.status.value] = counts.get(action.status.value, 0) + 1
        return {
            "mode": self.policy.mode.value,
            "execution_enabled": bool(self.policy.config.get("execution_enabled", False)),
            "kill_switch": self.kill_switch.active,
            "external_connectors": bool(self.policy.config.get("allow_external_connectors", False)),
            "external_email": bool(self.policy.config.get("allow_external_emails", False)),
            "total_actions": len(actions),
            "status_counts": counts,
        }
