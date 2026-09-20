from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class AuditLog:
    def __init__(self, path: Path | str = "outputs/actions/audit.jsonl") -> None:
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
    def write(self, event: str, data: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, "data": data}, default=str) + "\n")
