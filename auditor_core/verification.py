"""Before/after audit comparison for remediation verification."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _finding_map(audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    findings = audit.get("findings")
    if isinstance(findings, list) and findings:
        return {
            str(item.get("check_id") or f"legacy:{index}"): item
            for index, item in enumerate(findings)
            if isinstance(item, dict)
        }

    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(audit.get("defects", [])):
        if not isinstance(item, dict):
            continue
        key = str(item.get("defect_key") or item.get("defect") or f"legacy:{index}")
        result[key] = item
    return result


def _category_health(audit: dict[str, Any]) -> dict[str, int | None]:
    categories = (audit.get("category_scores") or {}).get("categories") or {}
    result: dict[str, int | None] = {}
    if isinstance(categories, dict):
        for name, data in categories.items():
            if isinstance(data, dict):
                value = data.get("score")
                result[str(name)] = int(value) if isinstance(value, (int, float)) else None
    return result


def compare_audits(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare two audit artifacts using stable check IDs where possible."""
    before_map = _finding_map(before)
    after_map = _finding_map(after)
    before_ids = set(before_map)
    after_ids = set(after_map)

    resolved = sorted(before_ids - after_ids)
    remaining = sorted(before_ids & after_ids)
    introduced = sorted(after_ids - before_ids)

    before_health = (before.get("category_scores") or {}).get("overall_health_score")
    after_health = (after.get("category_scores") or {}).get("overall_health_score")
    health_delta = (
        round(float(after_health) - float(before_health), 2)
        if isinstance(before_health, (int, float)) and isinstance(after_health, (int, float))
        else None
    )

    before_categories = _category_health(before)
    after_categories = _category_health(after)
    category_delta: dict[str, dict[str, int | float | None]] = {}
    for category in sorted(set(before_categories) | set(after_categories)):
        left = before_categories.get(category)
        right = after_categories.get(category)
        delta = right - left if isinstance(left, int) and isinstance(right, int) else None
        category_delta[category] = {"before": left, "after": right, "delta": delta}

    return {
        "schema_version": 1,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "target": after.get("url") or before.get("url"),
        "before_timestamp": before.get("timestamp"),
        "after_timestamp": after.get("timestamp"),
        "resolved_check_ids": resolved,
        "remaining_check_ids": remaining,
        "introduced_check_ids": introduced,
        "resolved_count": len(resolved),
        "remaining_count": len(remaining),
        "introduced_count": len(introduced),
        "health_score": {
            "before": before_health,
            "after": after_health,
            "delta": health_delta,
        },
        "category_health_delta": category_delta,
        "verification_passed": bool(resolved) and not introduced,
        "note": (
            "verification_passed means at least one previous finding resolved and no new "
            "finding IDs were introduced. Human review may still be required."
        ),
    }
