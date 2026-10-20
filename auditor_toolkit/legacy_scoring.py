"""Compatibility arithmetic for old {defect, impact} reports.

This is not the canonical evidence-based scorer or a separate audit engine.
It preserves two named message-weight formulas for an explicit legacy adapter.
Current pipeline reports must use scoring.score_from_findings instead.
"""
from __future__ import annotations

import re

LEGACY_SCORE_METHOD = "legacy-message-weights-v2"
ENHANCED_SCORE_METHOD = "legacy-enhanced-message-weights-v4"
LEGACY_SCORE_METHODS = (LEGACY_SCORE_METHOD, ENHANCED_SCORE_METHOD)


def score_legacy_defects(defects: list[dict], *, method: str = LEGACY_SCORE_METHOD) -> int | float:
    """Preserve valid legacy arithmetic without importing a root audit script."""
    if not isinstance(defects, list):
        raise ValueError("Legacy defects must be a list")
    if method not in LEGACY_SCORE_METHODS:
        raise ValueError("A known legacy scoring method must be selected explicitly")
    enhanced = method == ENHANCED_SCORE_METHOD
    high = ("missing h1", "no contact form", "missing title", "broken", "missing alt")
    high += ("no cta",) if enhanced else ("mobile-responsive",)
    medium = ("missing meta", "missing og", "missing canonical", "multiple h1", "stale copyright")
    if enhanced:
        medium += (
            "missing favicon", "missing viewport", "contrast", "missing og:image",
            "missing breadcrumb", "missing author", "no trust", "no compression", "missing pagination",
        )
    low = ("missing header", "no hsts", "no csp")
    if enhanced:
        low += ("missing referrer", "missing x-frame", "missing spf", "missing dmarc")
    score = 0
    for defect in defects:
        if not isinstance(defect, dict):
            raise ValueError("Every legacy defect must be a mapping")
        message = defect.get("defect", defect.get("header", ""))
        if not isinstance(message, str):
            raise ValueError("Legacy defect text must be a string")
        text = message.lower()
        if any(word in text for word in ("expired", "ssl_error", "noindex", "thin content")):
            score += 20
        elif any(word in text for word in high):
            score += 12
        elif any(word in text for word in medium):
            score += 8
        elif any(word in text for word in low):
            score += 5
        elif "w3c" in text or ("html error" if enhanced else "markup") in text:
            number = re.search(r"(\d+)", message)
            score += min(int(number.group(1)) * 0.2, 15) if number else 5
        else:
            score += 5
    return min(score, 100)
