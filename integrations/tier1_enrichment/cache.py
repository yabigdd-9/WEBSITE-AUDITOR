"""Disk cache for enrichment results.

Separate from the auditors' ``outputs/.cache`` so keyed third-party payloads
never mix with deterministic audit artifacts. TTLs are per-source (SSL Labs
grades move slowly; PageSpeed moves fast); stale cache is still returned when
a source is unreachable, flagged ``stale: true``.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

CACHE_DIR = Path("outputs/.cache/enrichment")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _path(key: str) -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()[:40]
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in key[:50])
    return CACHE_DIR / f"{safe}_{digest}.json"


class EnrichmentCache:
    def __init__(self, ttl: int = 86400) -> None:
        self.ttl = ttl

    def get(self, key: str, ttl: int | None = None) -> tuple[Any | None, bool]:
        """Return ``(data, fresh)``; ``fresh`` is False for stale fallback."""
        p = _path(key)
        if not p.exists():
            return None, False
        try:
            doc = json.loads(p.read_text())
        except (OSError, ValueError):
            return None, False
        age = time.time() - doc.get("_ts", 0)
        limit = self.ttl if ttl is None else ttl
        if age < limit:
            return doc.get("data"), True
        return doc.get("data"), False

    def set(self, key: str, data: Any) -> None:
        _path(key).write_text(
            json.dumps({"_ts": time.time(), "data": data}, default=str)
        )
