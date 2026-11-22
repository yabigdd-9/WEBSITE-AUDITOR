"""Quarantine and dead-letter queue management."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QuarantineEntry:
    job_id: str
    reason: str
    error_type: str
    data_hash: str = ""
    created_at: str = ""
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "reason": self.reason,
            "error_type": self.error_type,
            "data_hash": self.data_hash,
            "created_at": self.created_at,
            "retry_count": self.retry_count,
        }


@dataclass(frozen=True)
class DLQEntry:
    job_id: str
    reason: str
    retries_exhausted: int = 0
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "reason": self.reason, "retries_exhausted": self.retries_exhausted, "created_at": self.created_at}


class QuarantineStore:
    def __init__(self, store_dir: Path):
        self.store_dir = store_dir
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def add(self, entry: QuarantineEntry) -> Path:
        path = self.store_dir / f"{entry.job_id}.json"
        path.write_text(json.dumps(entry.to_dict(), indent=2))
        return path

    def list(self) -> list[QuarantineEntry]:
        entries = []
        for p in self.store_dir.glob("*.json"):
            data = json.loads(p.read_text())
            entries.append(QuarantineEntry(**data))
        return entries


class DLQStore:
    def __init__(self, store_dir: Path):
        self.store_dir = store_dir
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def add(self, entry: DLQEntry) -> Path:
        path = self.store_dir / f"{entry.job_id}.json"
        path.write_text(json.dumps(entry.to_dict(), indent=2))
        return path

    def count(self) -> int:
        return len(list(self.store_dir.glob("*.json")))


def quarantine_or_dlq(
    job_id: str,
    error: Exception,
    error_type: str,
    is_deterministic: bool,
    retry_count: int,
    max_retries: int,
    quarantine_dir: Path,
    dlq_dir: Path,
) -> QuarantineEntry | DLQEntry:
    from datetime import UTC, datetime
    now = datetime.now(UTC).isoformat()
    data_hash = hashlib.sha256(f"{job_id}:{error_type}".encode()).hexdigest()[:12]

    if is_deterministic or retry_count >= max_retries:
        return DLQStore(dlq_dir).add(DLQEntry(job_id=job_id, reason=str(error), retries_exhausted=retry_count, created_at=now))
    return QuarantineStore(quarantine_dir).add(QuarantineEntry(job_id=job_id, reason=str(error), error_type=error_type, data_hash=data_hash, created_at=now, retry_count=retry_count))
