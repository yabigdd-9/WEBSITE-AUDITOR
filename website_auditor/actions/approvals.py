from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class ApprovalStore:
    def __init__(self, path: Path | str = "outputs/actions/approvals.json") -> None:
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists(): self.path.write_text("{}", encoding="utf-8")
    def load(self) -> dict[str, Any]: return json.loads(self.path.read_text(encoding="utf-8"))
    def save(self, data: dict[str, Any]) -> None: self.path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    def approve(self, action_id: str, approver: str, reason: str = "") -> dict[str, Any]:
        data = self.load(); record = {"action_id": action_id, "decision": "approved", "approver": approver, "reason": reason, "decided_at": datetime.now(timezone.utc).isoformat()}
        data[action_id] = record; self.save(data); return record
    def is_approved(self, action_id: str) -> bool: return self.load().get(action_id, {}).get("decision") == "approved"
