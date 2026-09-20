"""Evidence capture helpers for deterministic static audits."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .models import EvidenceRecord


SENSITIVE_RESPONSE_HEADERS = {"set-cookie", "authorization", "proxy-authorization"}


def _safe_headers(headers: dict[str, Any]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in (headers or {}).items():
        name = str(key)
        if name.lower() in SENSITIVE_RESPONSE_HEADERS:
            safe[name] = "[redacted]"
        else:
            safe[name] = str(value)
    return safe


def build_page_evidence(
    url: str,
    html: str,
    headers: dict[str, Any],
    *,
    source: str = "static",
    snippet_limit: int = 2000,
) -> dict:
    encoded = (html or "").encode("utf-8", errors="replace")
    status = headers.get("status") if isinstance(headers, dict) else None
    clean_headers = {k: v for k, v in (headers or {}).items() if str(k).lower() != "status"}
    record = EvidenceRecord(
        url=url,
        captured_at=datetime.now(timezone.utc),
        source=source,
        http_status=int(status) if isinstance(status, int) else None,
        response_headers=_safe_headers(clean_headers),
        html_sha256=hashlib.sha256(encoded).hexdigest() if encoded else None,
        html_size_bytes=len(encoded),
        html_snippet=(html or "")[:snippet_limit] or None,
    )
    return record.model_dump(mode="json")
