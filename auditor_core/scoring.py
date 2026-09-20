"""Transparent category scoring for normalized findings."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

SEVERITY_DEDUCTION = {
    "critical": 35.0,
    "high": 22.0,
    "medium": 12.0,
    "low": 6.0,
    "cosmetic": 2.0,
}

DEFAULT_CATEGORIES = [
    "security",
    "performance",
    "seo",
    "accessibility",
    "mobile",
    "privacy_compliance",
    "content",
    "conversion",
    "technical_health",
    "nz_business",
]


def category_scores(findings: Iterable[dict]) -> dict:
    deductions: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    confidence_sum: dict[str, float] = defaultdict(float)

    for finding in findings:
        category = str(finding.get("category") or "technical_health")
        severity = str(finding.get("severity") or "low")
        confidence = float(finding.get("confidence", 0.5))
        confidence = min(1.0, max(0.0, confidence))
        deductions[category] += SEVERITY_DEDUCTION.get(severity, 6.0) * confidence
        counts[category] += 1
        confidence_sum[category] += confidence

    all_categories = list(dict.fromkeys(DEFAULT_CATEGORIES + sorted(deductions)))
    categories: dict[str, dict] = {}
    for category in all_categories:
        count = counts.get(category, 0)
        avg_confidence = round(confidence_sum.get(category, 0.0) / count, 3) if count else None
        categories[category] = {
            "score": max(0, round(100 - deductions.get(category, 0.0))) if count else None,
            "tested": bool(count),
            "finding_count": count,
            "average_confidence": avg_confidence,
            "deduction": round(deductions.get(category, 0.0), 2),
        }

    tested = [
        item["score"]
        for item in categories.values()
        if item["tested"] and item["score"] is not None
    ]
    overall = round(sum(tested) / len(tested)) if tested else None
    return {
        "schema_version": 1,
        "meaning": "health_score_100_is_best",
        "overall_health_score": overall,
        "categories": categories,
        "coverage_note": (
            "Categories without observed findings are null/untested until pass-result "
            "coverage is recorded; they are not assumed to be perfect."
        ),
    }
