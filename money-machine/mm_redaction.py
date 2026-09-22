"""Privacy boundary for optional free external model assistance.

Default behavior is conservative: secrets, direct contact details, credentials,
and local paths are removed or masked before a prompt can leave the host.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.I | re.S),
    re.compile(r"(?i)\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
)
EMAIL = re.compile(r"\b[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9-]+(?:\.[A-Z0-9-]+)+\b", re.I)
PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")
LOCAL_PATH = re.compile(r"(?:/Users/[^\s]+|/private/tmp/[^\s]+|[A-Z]:\\[^\s]+)")


def redact(text: str) -> tuple[str, list[str]]:
    if not isinstance(text, str):
        raise ValueError("prompt text must be a string")
    redactions = []
    output = text
    for pattern, label in ((pattern, "secret") for pattern in SECRET_PATTERNS):
        output, count = pattern.subn("[REDACTED_SECRET]", output)
        if count:
            redactions.extend([label] * count)
    output, count = EMAIL.subn("[REDACTED_EMAIL]", output)
    redactions.extend(["email"] * count)
    output, count = PHONE.subn("[REDACTED_PHONE]", output)
    redactions.extend(["phone"] * count)
    output, count = LOCAL_PATH.subn("[REDACTED_LOCAL_PATH]", output)
    redactions.extend(["local_path"] * count)
    return output, redactions


def prepare_prompt(prompt: str, *, public_only=True, max_chars=40_000) -> dict:
    clean, redactions = redact(prompt)
    if len(clean) > max_chars:
        raise ValueError("redacted prompt exceeds configured size limit")
    if "[REDACTED_SECRET]" in clean:
        # Redaction is safe, but requires human review rather than silently
        # treating a secret-bearing source as ordinary public content.
        review = True
    else:
        review = False
    return {
        "prompt": clean,
        "prompt_sha256": hashlib.sha256(clean.encode()).hexdigest(),
        "redactions": sorted(set(redactions)),
        "public_only": bool(public_only),
        "human_review_required": True,
        "secret_detected": "secret" in redactions,
        "external_send_allowed": False,
        "paid_calls": 0,
        "model_cost_usd": 0.0,
        "requires_source_review": review,
    }
