"""Idempotency — stable job identities and duplicate suppression."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def make_idempotency_key(
    business_id: str,
    snapshot_id: str,
    stage: str,
    policy_version: str = "v41",
    detector_version: str = "1",
) -> str:
    """Create a stable idempotency key for a job."""
    raw = f"{business_id}|{snapshot_id}|{stage}|{policy_version}|{detector_version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class IdempotencyStore:
    """Tracks completed jobs to prevent duplicate processing."""

    def __init__(self, store_dir: Path):
        self.store_dir = store_dir
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def is_completed(self, key: str) -> bool:
        path = self.store_dir / f"{key}.json"
        return path.exists()

    def mark_completed(self, key: str, result: dict[str, Any] | None = None) -> Path:
        path = self.store_dir / f"{key}.json"
        path.write_text(json.dumps({"key": key, "completed_at": time.time(), "result": result}))
        return path

    def count(self) -> int:
        return len(list(self.store_dir.glob("*.json")))
