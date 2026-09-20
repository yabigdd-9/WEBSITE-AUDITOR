from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Iterable
from ..models import Action, ActionStatus
from .approvals import ApprovalStore
from .audit_log import AuditLog
from .policy import PolicyEngine
from .registry import SAMPLE_DEFECTS, action_from_defect

class ActionExecutor:
    def __init__(self, output_dir: Path | str = "outputs/actions") -> None:
        self.output_dir = Path(output_dir); self.output_dir.mkdir(parents=True, exist_ok=True)
        self.proposed_path = self.output_dir / "proposed_actions.jsonl"
        self.dry_run_report_path = self.output_dir / "dry_run_report.json"
        self.policy = PolicyEngine(); self.audit = AuditLog(self.output_dir / "audit.jsonl")
        self.approvals = ApprovalStore(self.output_dir / "approvals.json")

    def _load_actions(self) -> list[Action]:
        if not self.proposed_path.exists(): return []
        return [Action.from_dict(json.loads(line)) for line in self.proposed_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _write_actions(self, actions: Iterable[Action]) -> None:
        lines = [json.dumps(action.to_dict(), default=str) for action in actions]
        self.proposed_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def add_actions(self, actions: Iterable[Action]) -> int:
        existing = self._load_actions(); existing_keys = {a.idempotency_key for a in existing}; added = 0
        for action in actions:
            if action.idempotency_key not in existing_keys: existing.append(action); existing_keys.add(action.idempotency_key); added += 1
        self._write_actions(existing); return added

    def propose_demo(self, domain: str = "example.co.nz") -> int: return self.add_actions([action_from_defect(domain, d) for d in SAMPLE_DEFECTS])

    def propose_from_remediations(self, root: Path | str, force: bool = False) -> int:
        root = Path(root)
        if not root.exists(): return 0
        created = []
        
        if force:
            # Clear existing actions for fresh repopulation
            self.proposed_path.unlink(missing_ok=True)
            self.dry_run_report_path.unlink(missing_ok=True)
        
        for json_path in root.rglob("*.json"):
            if "summary" in json_path.name: continue
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                domain = json_path.stem.replace("-remediation", "")
                
                # SMART HUNT: Look for defect-like arrays under various keys
                defects = []
                
                # Direct keys
                for key in ("defects", "issues", "findings", "actions"):
                    value = data.get(key)
                    if isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict):
                                defects.append(item)
                
                # If still empty, scan all list values for defect-like dicts
                if not defects and isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, list) and value and isinstance(value[0], dict):
                            first_item_str = str(value[0]).lower()
                            if any(k in first_item_str for k in ["issue", "fix", "defect", "error", "missing", "priority", "score", "impact"]):
                                defects.extend(value)
                
                for d in defects:
                    issue_text = d.get("issue") or d.get("title") or d.get("name") or d.get("defect") or d.get("fix", {}).get("title", "") or str(d)
                    normalized_defect = {"issue": issue_text, "raw": d}
                    created.append(action_from_defect(domain, normalized_defect))
            except Exception: continue
        return self.add_actions(created)

    def dry_run_all(self) -> dict[str, Any]:
        actions = self._load_actions(); results = []
        for action in actions:
            decision = self.policy.evaluate(action)
            if decision.effect == "dry_run": action.status = ActionStatus.DRY_RUN
            results.append({"action_id": action.action_id, "name": action.name, "domain": action.domain, "risk": action.risk.value, "decision": decision.to_dict()})
            self.audit.write("action_dry_run", {"action_id": action.action_id, "decision": decision.to_dict()})
        self._write_actions(actions)
        report = {"mode": self.policy.config.get("mode"), "total_actions": len(actions), "results": results}
        self.dry_run_report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8"); return report

    def execute_simulated(self) -> list[dict[str, Any]]:
        """Executes approved/dry-run actions using the local Git connector."""
        from ..connectors.git_connector import GitConnector
        git = GitConnector()
        actions = self._load_actions()
        results = []
        
        for action in actions:
            if action.status.value in ["dry_run", "proposed", "approved"]:
                res = git.execute_local_patch(action)
                action.status = ActionStatus.SIMULATED
                results.append({"action": action.name, "domain": action.domain, "result": res})
                
        self._write_actions(actions)
        return results

    def execute_wordpress_fix(self) -> list[dict[str, Any]]:
        """Generates WordPress-specific fix instructions for actions."""
        from ..connectors.wordpress_connector import WordPressConnector
        wp = WordPressConnector()
        actions = self._load_actions()
        results = []
        
        for action in actions:
            if action.status.value in ["dry_run", "proposed", "approved", "simulated"]:
                res = wp.execute_wordpress_fix(action)
                action.status = ActionStatus.SIMULATED
                results.append({"action": action.name, "domain": action.domain, "result": res})
                
        self._write_actions(actions)
        return results

    def execute_github_pr(self) -> list[dict[str, Any]]:
        """Opens GitHub PRs for approved/dry-run actions."""
        from ..connectors.github_connector import GitHubConnector
        gh = GitHubConnector()
        actions = self._load_actions()
        results = []
        
        for action in actions:
            if action.status.value in ["dry_run", "proposed", "approved", "simulated"] and action.connector == "local":
                res = gh.execute_action(action)
                action.status = ActionStatus.SIMULATED
                results.append({"action": action.name, "domain": action.domain, "result": res})
                
        self._write_actions(actions)
        return results

    def status_summary(self) -> dict[str, Any]:
        actions = self._load_actions(); counts = {}
        for a in actions: counts[a.status.value] = counts.get(a.status.value, 0) + 1
        return {"policy_mode": self.policy.config.get("mode"), "total_actions": len(actions), "status_counts": counts}
