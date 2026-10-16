"""Read-only decision consistency analysis for v45 intelligence.

Detects polarity oscillation for the same prospect, rule version, and stage.
A flip is a review signal, not proof that either decision was wrong: evidence
may legitimately have changed between observations.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

import mm_intelligence_calibration as calibration

RULE_VERSION = "v45-decision-consistency-v1"
_EXCLUDED = frozenset({"HUMAN_CORRECTED", "OUTCOME_OBSERVED"})


def _table_exists(d: sqlite3.Connection, name: str) -> bool:
    return bool(
        d.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
    )


def consistency_report(
    d: sqlite3.Connection,
    limit: int = 10000,
    min_confidence: float = 0.80,
) -> dict:
    """Report repeated decision polarity flips without changing any state."""
    bounded = max(1, min(int(limit), 50000))
    confidence_threshold = min(1.0, max(0.0, float(min_confidence)))

    if not _table_exists(d, "intelligence_ledger"):
        return {
            "groups": [],
            "group_count": 0,
            "unstable_group_count": 0,
            "total_flips": 0,
            "high_confidence_flips": 0,
            "read_only": True,
            "automatic_rule_change": False,
            "promotion_authorized": False,
            "paid_calls": 0,
            "external_sends": 0,
            "rule_version": RULE_VERSION,
        }

    rows = [
        dict(row)
        for row in d.execute(
            """SELECT id,prospect_id,decision,disposition,confidence,
                      rule_version,stage,recorded_at
               FROM intelligence_ledger
               ORDER BY id DESC LIMIT ?""",
            (bounded,),
        ).fetchall()
    ]
    rows.reverse()

    grouped = defaultdict(list)
    for row in rows:
        if row.get("disposition") in _EXCLUDED:
            continue
        polarity = calibration._polarity(row.get("decision"))
        if polarity is None:
            continue
        key = (
            int(row["prospect_id"]),
            str(row.get("rule_version") or "unknown"),
            str(row.get("stage") or "unknown"),
        )
        row["polarity"] = polarity
        grouped[key].append(row)

    groups = []
    total_flips = 0
    total_high = 0
    for (prospect_id, rule_version, stage), decisions in grouped.items():
        if len(decisions) < 2:
            continue
        flips = []
        for before, after in zip(decisions, decisions[1:]):
            if int(before["polarity"]) == int(after["polarity"]):
                continue
            before_conf = calibration._confidence(before.get("confidence"))
            after_conf = calibration._confidence(after.get("confidence"))
            high = (
                before_conf is not None
                and after_conf is not None
                and before_conf >= confidence_threshold
                and after_conf >= confidence_threshold
            )
            flips.append({
                "from_ledger_id": int(before["id"]),
                "to_ledger_id": int(after["id"]),
                "from_decision": before["decision"],
                "to_decision": after["decision"],
                "from_confidence": before_conf,
                "to_confidence": after_conf,
                "high_confidence": high,
            })

        high_count = sum(1 for item in flips if item["high_confidence"])
        total_flips += len(flips)
        total_high += high_count
        groups.append({
            "prospect_id": prospect_id,
            "rule_version": rule_version,
            "stage": stage,
            "decision_count": len(decisions),
            "flip_count": len(flips),
            "high_confidence_flip_count": high_count,
            "signal": "REVIEW_OSCILLATION" if flips else "STABLE",
            "flips": flips,
            "automatic_action": False,
        })

    groups.sort(
        key=lambda item: (
            -item["high_confidence_flip_count"],
            -item["flip_count"],
            item["prospect_id"],
            item["rule_version"],
            item["stage"],
        )
    )
    unstable = sum(1 for item in groups if item["flip_count"])
    return {
        "groups": groups,
        "group_count": len(groups),
        "unstable_group_count": unstable,
        "total_flips": total_flips,
        "high_confidence_flips": total_high,
        "high_confidence_threshold": confidence_threshold,
        "ledger_rows_assessed": len(rows),
        "method": (
            "Only same-prospect, same-rule-version, same-stage decisions are "
            "compared. Corrections and outcome observations are excluded. "
            "A flip is a review signal and may reflect legitimate new evidence."
        ),
        "read_only": True,
        "causal_claim_allowed": False,
        "automatic_rule_change": False,
        "promotion_authorized": False,
        "paid_calls": 0,
        "external_sends": 0,
        "rule_version": RULE_VERSION,
    }
