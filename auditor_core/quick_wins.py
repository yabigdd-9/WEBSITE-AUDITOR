"""Quick-win prioritization from remediation actions."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


def _effort_minutes(text: str | None) -> int | None:
    value = (text or "").lower()
    numbers = [int(item) for item in re.findall(r"\d+", value)]
    if not numbers:
        return None
    upper = max(numbers)
    if "hour" in value:
        return upper * 60
    return upper


def rank_quick_wins(remediation: dict[str, Any], limit: int = 10) -> dict[str, Any]:
    ranked: list[dict[str, Any]] = []
    for action in remediation.get("actions", []):
        if not isinstance(action, dict):
            continue
        fix = action.get("fix") if isinstance(action.get("fix"), dict) else {}
        minutes = _effort_minutes(fix.get("effort"))
        priority = int(action.get("priority", 99) or 99)
        confidence = action.get("confidence")
        confidence_value = float(confidence) if isinstance(confidence, (int, float)) else 0.5
        auto_fixable = bool(action.get("auto_fixable", False))
        human_review = bool(action.get("human_review", False))

        effort_component = 0 if minutes is None else max(0, 120 - min(minutes, 120))
        priority_component = max(0, 100 - min(priority, 99) * 8)
        confidence_component = round(confidence_value * 30)
        automation_component = 10 if auto_fixable else 0
        review_penalty = 15 if human_review else 0
        quick_win_score = max(
            0,
            round(
                priority_component
                + effort_component * 0.6
                + confidence_component
                + automation_component
                - review_penalty
            ),
        )

        ranked.append(
            {
                "check_id": action.get("check_id"),
                "defect": action.get("defect"),
                "category": action.get("category"),
                "severity": action.get("severity"),
                "confidence": confidence,
                "priority": priority,
                "effort": fix.get("effort"),
                "effort_minutes_upper_bound": minutes,
                "cost": fix.get("cost"),
                "fix_title": fix.get("title"),
                "human_review": human_review,
                "quick_win_score": quick_win_score,
            }
        )

    ranked.sort(
        key=lambda item: (
            -int(item["quick_win_score"]),
            int(item["priority"]),
            item.get("effort_minutes_upper_bound")
            if item.get("effort_minutes_upper_bound") is not None
            else 10_000,
            str(item.get("check_id") or ""),
        )
    )
    selected = ranked[: max(0, int(limit))]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "domain": remediation.get("domain"),
        "count": len(selected),
        "quick_wins": selected,
        "method": (
            "Higher score favors urgent, high-confidence, low-effort findings and penalizes "
            "items flagged for human review."
        ),
    }


def quick_wins_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Quick Wins — {report.get('domain') or 'unknown'}",
        "",
        "| # | Finding | Fix | Effort | Cost | Score |",
        "|---:|---|---|---|---|---:|",
    ]
    for index, item in enumerate(report.get("quick_wins", []), 1):
        def clean(value: Any) -> str:
            return str(value or "").replace("|", "\\|").replace("\n", " ")

        lines.append(
            f"| {index} | {clean(item.get('defect'))} | {clean(item.get('fix_title'))} | "
            f"{clean(item.get('effort'))} | {clean(item.get('cost'))} | "
            f"{item.get('quick_win_score', 0)} |"
        )
    lines.extend(["", report.get("method", "")])
    return "\n".join(lines) + "\n"
