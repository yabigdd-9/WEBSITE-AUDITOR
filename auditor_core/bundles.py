"""Deterministic remediation fix bundles for client/package planning."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


BUNDLE_ORDER = [
    "quick_wins",
    "trust_security",
    "seo_accessibility",
    "ecommerce",
    "content_conversion",
    "technical_projects",
]


def _minutes(value: str | None) -> int | None:
    text = str(value or "").lower()
    numbers = [int(item) for item in re.findall(r"\d+", text)]
    if not numbers:
        return None
    upper = max(numbers)
    return upper * 60 if "hour" in text else upper


def bundle_for(action: dict[str, Any]) -> str:
    check_id = str(action.get("check_id") or "")
    category = str(action.get("category") or "")
    priority = int(action.get("priority", 99) or 99)
    effort = _minutes((action.get("fix") or {}).get("effort"))

    if check_id.startswith("ecommerce."):
        return "ecommerce"
    if category == "security" or check_id.startswith(("security.", "email.")):
        return "trust_security"
    if category in {"seo", "accessibility"}:
        if priority <= 4 and (effort is None or effort <= 30):
            return "quick_wins"
        return "seo_accessibility"
    if category in {"content", "conversion"}:
        return "content_conversion"
    if priority <= 3 and (effort is None or effort <= 30):
        return "quick_wins"
    return "technical_projects"


def build_fix_bundles(remediation: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in BUNDLE_ORDER}
    for action in remediation.get("actions", []):
        if not isinstance(action, dict):
            continue
        grouped[bundle_for(action)].append(action)

    bundles: list[dict[str, Any]] = []
    for name in BUNDLE_ORDER:
        actions = grouped[name]
        if not actions:
            continue
        known_minutes = [
            value
            for value in (_minutes((action.get("fix") or {}).get("effort")) for action in actions)
            if value is not None
        ]
        bundles.append(
            {
                "bundle_id": name,
                "title": name.replace("_", " ").title(),
                "action_count": len(actions),
                "estimated_minutes_upper_bound": sum(known_minutes) if known_minutes else None,
                "human_review_count": sum(bool(action.get("human_review")) for action in actions),
                "highest_priority": min(int(action.get("priority", 99) or 99) for action in actions),
                "check_ids": [action.get("check_id") for action in actions],
                "actions": actions,
            }
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "domain": remediation.get("domain"),
        "bundle_count": len(bundles),
        "bundles": bundles,
        "note": (
            "Bundles group evidence-backed remediation work. Time values are context estimates "
            "from the fix library, not guaranteed quotes."
        ),
    }


def bundles_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Fix Bundles — {report.get('domain') or 'unknown'}", ""]
    for bundle in report.get("bundles", []):
        lines.extend(
            [
                f"## {bundle['title']}",
                "",
                f"- Actions: {bundle['action_count']}",
                f"- Highest priority: P{bundle['highest_priority']}",
                f"- Human review: {bundle['human_review_count']}",
                (
                    f"- Estimated effort upper bound: {bundle['estimated_minutes_upper_bound']} minutes"
                    if bundle.get("estimated_minutes_upper_bound") is not None
                    else "- Estimated effort: requires manual sizing"
                ),
                "",
            ]
        )
        for action in bundle.get("actions", []):
            fix = action.get("fix") or {}
            lines.append(
                f"- **{action.get('check_id')}** — {action.get('defect')} → "
                f"{fix.get('title', 'Review')} ({fix.get('effort', 'TBD')})"
            )
        lines.append("")
    lines.append(str(report.get("note") or ""))
    return "\n".join(lines) + "\n"
