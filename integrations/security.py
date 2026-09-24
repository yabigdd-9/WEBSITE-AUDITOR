"""Shared secret-safe diagnostics and webhook authentication helpers."""
from __future__ import annotations

import hashlib
import hmac
import re

_SECRET = re.compile(
    r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?|api[_-]?key\s*[:=]\s*|"
    r"access[_-]?token\s*[:=]\s*|password\s*[:=]\s*|secret\s*[:=]\s*)"
    r"([^\s,;]+)|\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"ghs_[A-Za-z0-9]{20,}|ya29\.[A-Za-z0-9_-]+)\b"
)


def redact(value):
    if isinstance(value, dict):
        return {str(k): ("[REDACTED]" if re.search(r"(?i)(token|secret|password|api[_-]?key|authorization)", str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return _SECRET.sub(lambda m: (m.group(1) + "[REDACTED]") if m.group(1) else "[REDACTED]", value)
    return value


def verify_github_signature(body: bytes, signature: str | None, secret: str | None) -> bool:
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_agent_token(supplied: str | None, expected: str | None) -> bool:
    return bool(supplied and expected and hmac.compare_digest(supplied, expected))
