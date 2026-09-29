"""Sanitized hard-case corpus for offline challenger replay.

Builds challenger-compatible golden cases from evidence-backed wrong decisions.
This module is read-only. It does not write fixtures, change rules, promote a
challenger, call a model, use the network, or send outreach.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter

import mm_intelligence_calibration as calibration

RULE_VERSION = "v45-hard-cases-v1"

_SAFE_DERIVED_FIELDS = frozenset({
    "commercial_score",
    "commercial_opportunity_score",
    "technical_score",
    "technical_opportunity_score",
    "opportunity_score",
    "evidence_confidence",
    "missing_evidence",
    "qualification_basis",
})


def _table_exists(d: sqlite3.Connection, name: str) -> bool:
    return bool(
        d.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
    )


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _safe_derived(value) -> dict:
    obj = _json_object(value)
    result = {}
    for key in sorted(_SAFE_DERIVED_FIELDS):
        if key not in obj:
            continue
        item = obj[key]
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[key] = item
        elif isinstance(item, list):
            result[key] = [
                x for x in item
                if isinstance(x, (str, int, float, bool)) or x is None
            ][:25]
        elif key == "opportunity_score" and isinstance(item, dict):
            score = item.get("score")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                result[key] = {"score": score}
    return result


def _expected_polarity(example: dict) -> str:
    original = int(example["decision_polarity"])
    correct = int(example["observed_correct"])
    expected = original if correct else 1 - original
    return "POSITIVE" if expected == 1 else "NEGATIVE"


def _error_type(example: dict) -> str:
    original = int(example["decision_polarity"])
    if int(example["observed_correct"]) == 1:
        return "CONFIRMED_CORRECT"
    return (
        "CONFIRMED_FALSE_POSITIVE"
        if original == 1
        else "CONFIRMED_FALSE_NEGATIVE"
    )


def hard_cases(d: sqlite3.Connection, limit: int = 500) -> dict:
    """Return confirmed wrong decisions as sanitized challenger goldens."""
    bounded = max(1, min(int(limit), 5000))
    if not _table_exists(d, "intelligence_ledger"):
        return {
            "cases": [],
            "count": 0,
            "by_type": {},
            "by_rule_version": {},
            "read_only": True,
            "sanitized": True,
            "paid_calls": 0,
            "external_sends": 0,
            "rule_version": RULE_VERSION,
        }

    confirmed = calibration.confirmed_examples(d, limit=max(bounded * 4, bounded))
    wrong = [row for row in confirmed if int(row["observed_correct"]) == 0][:bounded]
    ledger_ids = [int(row["ledger_id"]) for row in wrong]
    ledger_by_id = {}
    if ledger_ids:
        marks = ",".join("?" for _ in ledger_ids)
        rows = d.execute(
            f"SELECT * FROM intelligence_ledger WHERE id IN ({marks})",
            ledger_ids,
        ).fetchall()
        ledger_by_id = {int(row["id"]): dict(row) for row in rows}

    cases = []
    type_counts = Counter()
    rule_counts = Counter()

    for example in wrong:
        ledger_id = int(example["ledger_id"])
        original = ledger_by_id.get(ledger_id, {})
        case_type = _error_type(example)
        expected = _expected_polarity(example)
        case_id = f"intelligence-ledger-{ledger_id}"

        case = {
            "case_id": case_id,
            "expected": expected,
            "safety": {
                "paid_calls": 0,
                "external_sends": 0,
                "auto_promoted": False,
            },
            "case_type": case_type,
            "prospect_id": int(example["prospect_id"]),
            "original_decision": example["decision"],
            "original_polarity": (
                "POSITIVE"
                if int(example["decision_polarity"]) == 1
                else "NEGATIVE"
            ),
            "original_confidence": example["confidence"],
            "confirmation": example["confirmation"],
            "confirmation_ledger_id": example["confirmation_ledger_id"],
            "later_outcome": example.get("later_outcome"),
            "rule_version": example.get("rule_version") or "",
            "stage": example.get("stage") or "",
            "source": example.get("source") or "",
            "derived_evidence": _safe_derived(
                original.get("derived_evidence")
            ),
            "raw_payloads_included": False,
        }
        cases.append(case)
        type_counts[case_type] += 1
        rule_counts[case["rule_version"] or "unknown"] += 1

    return {
        "cases": cases,
        "count": len(cases),
        "by_type": dict(sorted(type_counts.items())),
        "by_rule_version": dict(sorted(rule_counts.items())),
        "read_only": True,
        "sanitized": True,
        "challenger_compatible": True,
        "promotion_authorized": False,
        "paid_calls": 0,
        "external_sends": 0,
        "rule_version": RULE_VERSION,
    }


def golden_rows(d: sqlite3.Connection, limit: int = 500) -> list[dict]:
    """Return only fields consumed by mm_challenger.evaluate()."""
    report = hard_cases(d, limit)
    return [
        {
            "case_id": case["case_id"],
            "expected": case["expected"],
            "safety": dict(case["safety"]),
        }
        for case in report["cases"]
    ]


def evaluate_challenger(
    d: sqlite3.Connection,
    baseline_rows: list[dict],
    challenger_rows: list[dict],
    limit: int = 500,
    min_improvement: float = 0.01,
) -> dict:
    """Evaluate predictions against confirmed hard cases, never auto-promote."""
    import mm_challenger

    goldens = golden_rows(d, limit)
    if not goldens:
        raise ValueError(
            "No confirmed hard cases are available for challenger evaluation"
        )
    result = mm_challenger.compare(
        goldens,
        baseline_rows,
        challenger_rows,
        min_improvement=min_improvement,
    )
    result.update({
        "hard_case_count": len(goldens),
        "hard_case_rule_version": RULE_VERSION,
        "golden_source": "confirmed_intelligence_errors",
        "promotion_authorized": False,
        "merge_authority": False,
        "deployment_authorized": False,
        "external_sends": 0,
        "paid_calls": 0,
    })
    return result
