"""Append-only action audit log."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import utc_now


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, event: str, **fields: Any) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {"at": utc_now(), "event": event, **fields}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        return record
