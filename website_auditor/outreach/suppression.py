"""Local suppression list for outreach compliance.

Emails are normalized and stored by SHA-256 fingerprint with a masked display value.
Domains are stored in normalized lower-case form.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def normalize_domain(value: str) -> str:
    domain = str(value or "").strip().lower().rstrip(".")
    if "@" in domain:
        domain = domain.rsplit("@", 1)[1]
    return domain


def email_fingerprint(email: str) -> str:
    normalized = normalize_email(email)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def mask_email(email: str) -> str:
    normalized = normalize_email(email)
    if "@" not in normalized:
        return "***"
    local, domain = normalized.split("@", 1)
    visible = local[:1] if local else ""
    return f"{visible}***@{domain}"


class SuppressionStore:
    def __init__(self, path: str | Path = "outputs/outreach/suppression.json"):
        self.path = Path(path)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"emails": {}, "domains": {}}
        try:
            payload = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return {"emails": {}, "domains": {}}
        if not isinstance(payload, dict):
            return {"emails": {}, "domains": {}}
        payload.setdefault("emails", {})
        payload.setdefault("domains", {})
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
        tmp.replace(self.path)

    def suppress_email(
        self,
        email: str,
        *,
        reason: str = "manual",
        source: str = "local_user",
    ) -> dict[str, Any]:
        normalized = normalize_email(email)
        if "@" not in normalized:
            raise ValueError("a valid email address is required")
        fingerprint = email_fingerprint(normalized)
        payload = self._load()
        record = {
            "fingerprint": fingerprint,
            "masked": mask_email(normalized),
            "domain": normalize_domain(normalized),
            "reason": reason,
            "source": source,
            "suppressed_at": utc_now(),
        }
        payload["emails"][fingerprint] = record
        self._save(payload)
        return record

    def suppress_domain(
        self,
        domain: str,
        *,
        reason: str = "manual",
        source: str = "local_user",
    ) -> dict[str, Any]:
        normalized = normalize_domain(domain)
        if not normalized or "." not in normalized:
            raise ValueError("a valid domain is required")
        payload = self._load()
        record = {
            "domain": normalized,
            "reason": reason,
            "source": source,
            "suppressed_at": utc_now(),
        }
        payload["domains"][normalized] = record
        self._save(payload)
        return record

    def unsuppress_email(self, email: str) -> bool:
        payload = self._load()
        removed = payload["emails"].pop(email_fingerprint(email), None) is not None
        if removed:
            self._save(payload)
        return removed

    def unsuppress_domain(self, domain: str) -> bool:
        payload = self._load()
        removed = payload["domains"].pop(normalize_domain(domain), None) is not None
        if removed:
            self._save(payload)
        return removed

    def check(self, *, email: str | None = None, domain: str | None = None) -> dict[str, Any]:
        payload = self._load()
        normalized_email = normalize_email(email or "")
        normalized_domain = normalize_domain(domain or normalized_email)

        if normalized_email:
            record = payload["emails"].get(email_fingerprint(normalized_email))
            if record:
                return {
                    "suppressed": True,
                    "scope": "email",
                    "reason": record.get("reason"),
                    "record": record,
                }

        if normalized_domain:
            record = payload["domains"].get(normalized_domain)
            if record:
                return {
                    "suppressed": True,
                    "scope": "domain",
                    "reason": record.get("reason"),
                    "record": record,
                }

        return {"suppressed": False, "scope": None, "reason": None}

    def snapshot(self) -> dict[str, Any]:
        payload = self._load()
        return {
            "email_suppressions": list(payload["emails"].values()),
            "domain_suppressions": list(payload["domains"].values()),
            "email_count": len(payload["emails"]),
            "domain_count": len(payload["domains"]),
        }
