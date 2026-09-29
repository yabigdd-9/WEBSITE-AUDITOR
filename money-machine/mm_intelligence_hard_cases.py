"""Sanitized hard-case corpus for offline challenger replay.

Builds challenger-compatible golden cases from evidence-backed wrong decisions.
This module is read-only. It does not write fixtures, change rules, promote a
challenger, call a model, use the network, or send outreach.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict

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


def _stable_case_order(case: dict, salt: str) -> str:
    payload = f"{salt}|{case['case_id']}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def split_goldens(
    d: sqlite3.Connection,
    limit: int = 500,
    validation_fraction: float = 0.25,
    salt: str = "v45-hard-case-holdout",
) -> dict:
    """Deterministically split confirmed goldens into tuning and holdout sets."""
    fraction = float(validation_fraction)
    if not 0.0 < fraction < 1.0:
        raise ValueError("validation_fraction must be between 0 and 1")

    goldens = golden_rows(d, limit)
    if len(goldens) < 2:
        return {
            "training": list(goldens),
            "validation": [],
            "training_count": len(goldens),
            "validation_count": 0,
            "status": "INSUFFICIENT_CASES",
            "validation_fraction": fraction,
            "salt": str(salt),
            "deterministic": True,
            "read_only": True,
        }

    by_label: dict[str, list[dict]] = defaultdict(list)
    for case in goldens:
        by_label[str(case.get("expected") or "UNKNOWN")].append(case)

    training: list[dict] = []
    validation: list[dict] = []
    for label in sorted(by_label):
        rows = sorted(
            by_label[label],
            key=lambda case: _stable_case_order(case, str(salt)),
        )
        if len(rows) == 1:
            training.extend(rows)
            continue
        validation_count = max(
            1,
            min(len(rows) - 1, int(round(len(rows) * fraction))),
        )
        validation.extend(rows[:validation_count])
        training.extend(rows[validation_count:])

    if not validation:
        ordered = sorted(
            training,
            key=lambda case: _stable_case_order(case, str(salt)),
        )
        validation.append(ordered[0])
        training = ordered[1:]

    if not training:
        ordered = sorted(
            validation,
            key=lambda case: _stable_case_order(case, str(salt)),
        )
        training.append(ordered[-1])
        validation = ordered[:-1]

    training.sort(key=lambda case: case["case_id"])
    validation.sort(key=lambda case: case["case_id"])
    return {
        "training": training,
        "validation": validation,
        "training_count": len(training),
        "validation_count": len(validation),
        "status": "READY",
        "validation_fraction": fraction,
        "salt": str(salt),
        "deterministic": True,
        "read_only": True,
    }


def evaluate_challenger_holdout(
    d: sqlite3.Connection,
    baseline_rows: list[dict],
    challenger_rows: list[dict],
    limit: int = 500,
    validation_fraction: float = 0.25,
    salt: str = "v45-hard-case-holdout",
    min_improvement: float = 0.01,
) -> dict:
    """Evaluate a challenger on deterministic unseen confirmed hard cases."""
    import mm_challenger

    split = split_goldens(
        d,
        limit=limit,
        validation_fraction=validation_fraction,
        salt=salt,
    )
    validation = split["validation"]
    training = split["training"]
    if not validation:
        raise ValueError(
            "At least two confirmed hard cases are required for holdout evaluation"
        )

    validation_result = mm_challenger.compare(
        validation,
        baseline_rows,
        challenger_rows,
        min_improvement=min_improvement,
    )
    baseline_training = (
        mm_challenger.evaluate(training, baseline_rows)
        if training
        else None
    )
    challenger_training = (
        mm_challenger.evaluate(training, challenger_rows)
        if training
        else None
    )

    generalization_gap = None
    if challenger_training is not None:
        generalization_gap = round(
            validation_result["challenger"]["accuracy"]
            - challenger_training["accuracy"],
            6,
        )

    validation_result.update({
        "training": {
            "baseline": baseline_training,
            "challenger": challenger_training,
        },
        "split": {
            "training_count": split["training_count"],
            "validation_count": split["validation_count"],
            "validation_fraction": split["validation_fraction"],
            "salt": split["salt"],
            "deterministic": True,
        },
        "challenger_generalization_gap": generalization_gap,
        "recommendation_basis": "validation_holdout_only",
        "promotion_authorized": False,
        "merge_authority": False,
        "deployment_authorized": False,
        "automatic_rule_change": False,
        "external_sends": 0,
        "paid_calls": 0,
    })
    return validation_result
