import json
from pathlib import Path
from ..models import Action, ActionStatus
from .policy import PolicyEngine
from .registry import action_from_defect

class ActionExecutor:
    def __init__(self, output_dir="outputs/actions"):
        self.output_dir = Path(output_dir); self.output_dir.mkdir(parents=True, exist_ok=True)
        self.proposed_path = self.output_dir / "proposed_actions.jsonl"
        self.policy = PolicyEngine()
        
    def _load_actions(self):
        if not self.proposed_path.exists(): return []
        return [Action.from_dict(json.loads(line)) for line in self.proposed_path.read_text().splitlines() if line.strip()]

    def _write_actions(self, actions):
        lines = [json.dumps(a.to_dict(), default=str) for a in actions]
        self.proposed_path.write_text("\n".join(lines) + ("\n" if lines else ""))

    def add_actions(self, actions):
        existing = self._load_actions()
        existing_keys = {a.idempotency_key for a in existing}
        added = 0
        for action in actions:
            if action.idempotency_key not in existing_keys:
                existing.append(action)
                existing_keys.add(action.idempotency_key)
                added += 1
        self._write_actions(existing)
        return added

    def _god_mode_extract(self, obj):
        """Recursively hunts for defect lists in any JSON structure."""
        found = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                found.extend(self._god_mode_extract(v))
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    s = str(item).lower()
                    if any(x in s for x in ["fix:", "missing", "broken", "error", "priority", "hsts", "title"]):
                        found.append(item)
        return found

    def propose_from_remediations(self, root):
        root = Path(root); created = 0
        if not root.exists(): return 0
        for json_path in root.rglob("*.json"):
            if "summary" in json_path.name: continue
            try:
                data = json.loads(json_path.read_text())
                domain = json_path.stem.replace("-remediation", "")
                defects = self._god_mode_extract(data)
                for d in defects:
                    issue_text = d.get("issue") or d.get("title") or d.get("name") or str(d)
                    action = action_from_defect(domain, {"issue": issue_text, "raw": d})
                    self.add_actions([action])
                    created += 1
            except Exception: continue
        return created

    def dry_run_all(self):
        actions = self._load_actions()
        for action in actions:
            decision = self.policy.evaluate(action)
            if decision.get("effect") == "dry_run": action.status = ActionStatus.DRY_RUN
        self._write_actions(actions)
        return {"mode": "dry_run", "total_actions": len(actions)}

    def execute_simulated(self):
        from ..connectors.git_connector import GitConnector
        git = GitConnector()
        actions = self._load_actions()
        results = []
        for action in actions:
            if action.status.value in ["dry_run", "proposed"]:
                res = git.execute_local_patch(action)
                action.status = ActionStatus.SIMULATED
                results.append({"action": action.name, "domain": action.domain, "result": res})
        self._write_actions(actions)
        return results

    def status_summary(self):
        actions = self._load_actions(); counts = {}
        for a in actions: counts[a.status.value] = counts.get(a.status.value, 0) + 1
        return {"policy_mode": "dry_run", "total_actions": len(actions), "status_counts": counts}
