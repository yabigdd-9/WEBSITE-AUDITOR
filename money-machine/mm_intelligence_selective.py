"""Read-only selective-confidence / risk-coverage analysis for v45.

Measures how confirmed decision error risk changes when lower-confidence
decisions are deferred. Threshold candidates are advisory only: this module
never changes production confidence thresholds, rules, routes, approvals,
models, or external actions.
"""
from __future__ import annotations

import sqlite3

import mm_intelligence_calibration as calibration

RULE_VERSION = "v45-selective-confidence-v1"
DEFAULT_THRESHOLDS = (
    0.00,
    0.50,
    0.60,
    0.70,
    0.80,
    0.85,
    0.90,
    0.95,
)


def _expected_polarity(example: dict) -> int:
    original = int(example["decision_polarity"])
    correct = int(example["observed_correct"])
    return original if correct else 1 - original


def _threshold_point(
    examples: list[dict],
    threshold: float,
    max_risk: float,
    min_coverage: float,
) -> dict:
    selected = [
        row for row in examples
        if float(row["confidence"]) >= threshold
    ]
    total = len(examples)
    kept = len(selected)
    correct = sum(int(row["observed_correct"]) for row in selected)
    errors = kept - correct
    false_positives = sum(
        1
        for row in selected
        if int(row["observed_correct"]) == 0
        and int(row["decision_polarity"]) == 1
    )
    false_negatives = sum(
        1
        for row in selected
        if int(row["observed_correct"]) == 0
        and int(row["decision_polarity"]) == 0
    )
    coverage = kept / total if total else 0.0
    accuracy = correct / kept if kept else None
    risk = errors / kept if kept else None
    avg_confidence = (
        sum(float(row["confidence"]) for row in selected) / kept
        if kept
        else None
    )
    positive_labels = sum(_expected_polarity(row) for row in selected)

    meets_target = bool(
        kept
        and risk is not None
        and risk <= max_risk
        and coverage >= min_coverage
    )
    return {
        "threshold": round(threshold, 4),
        "selected": kept,
        "deferred": total - kept,
        "coverage": round(coverage, 4),
        "accuracy": round(accuracy, 4) if accuracy is not None else None,
        "risk": round(risk, 4) if risk is not None else None,
        "errors": errors,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "avg_confidence": (
            round(avg_confidence, 4)
            if avg_confidence is not None
            else None
        ),
        "expected_positive_labels": positive_labels,
        "meets_target": meets_target,
    }


def _aurc(points: list[dict]) -> float | None:
    usable = [
        (float(point["coverage"]), float(point["risk"]))
        for point in points
        if point["risk"] is not None
    ]
    if len(usable) < 2:
        return None
    by_coverage = sorted(set(usable))
    area = 0.0
    for (x1, y1), (x2, y2) in zip(by_coverage, by_coverage[1:]):
        area += (x2 - x1) * ((y1 + y2) / 2)
    return round(area, 6)


def selective_report(
    d: sqlite3.Connection,
    *,
    thresholds: list[float] | tuple[float, ...] | None = None,
    min_confirmed: int = 30,
    max_risk: float = 0.10,
    min_coverage: float = 0.30,
    limit: int = 5000,
) -> dict:
    """Return a confirmed-outcome risk/coverage curve."""
    minimum = max(1, int(min_confirmed))
    risk_target = min(1.0, max(0.0, float(max_risk)))
    coverage_target = min(1.0, max(0.0, float(min_coverage)))
    bounded_limit = max(1, min(int(limit), 50000))

    raw_thresholds = (
        DEFAULT_THRESHOLDS
        if thresholds is None
        else thresholds
    )
    normalized = sorted({
        round(float(value), 6)
        for value in raw_thresholds
        if 0.0 <= float(value) <= 1.0
    })
    if not normalized:
        raise ValueError("At least one threshold between 0 and 1 is required")

    examples = calibration.confirmed_examples(d, bounded_limit)
    points = [
        _threshold_point(
            examples,
            threshold,
            risk_target,
            coverage_target,
        )
        for threshold in normalized
    ]
    eligible = [
        point for point in points
        if point["meets_target"]
    ]
    # Lowest threshold gives the highest coverage among eligible thresholds.
    highest_coverage_candidate = eligible[0] if eligible else None

    total = len(examples)
    overall_correct = sum(
        int(row["observed_correct"]) for row in examples
    )
    overall_accuracy = (
        overall_correct / total
        if total
        else None
    )

    if total < minimum:
        status = "INSUFFICIENT_HISTORY"
    elif eligible:
        status = "TARGET_OBSERVED"
    else:
        status = "NO_THRESHOLD_MEETS_TARGET"

    return {
        "status": status,
        "confirmed_examples": total,
        "minimum_confirmed": minimum,
        "overall_accuracy": (
            round(overall_accuracy, 4)
            if overall_accuracy is not None
            else None
        ),
        "overall_risk": (
            round(1.0 - overall_accuracy, 4)
            if overall_accuracy is not None
            else None
        ),
        "target": {
            "max_risk": risk_target,
            "min_coverage": coverage_target,
        },
        "points": points,
        "area_under_risk_coverage": _aurc(points),
        "eligible_thresholds": [
            point["threshold"] for point in eligible
        ],
        "highest_coverage_candidate": (
            {
                "threshold": highest_coverage_candidate["threshold"],
                "coverage": highest_coverage_candidate["coverage"],
                "risk": highest_coverage_candidate["risk"],
            }
            if highest_coverage_candidate is not None
            else None
        ),
        "method": (
            "Only evidence-backed confirmed decisions are evaluated. "
            "Coverage is the fraction retained at or above each confidence "
            "threshold; risk is the confirmed error rate among retained "
            "decisions. Historical threshold performance may not generalize."
        ),
        "advisory_only": True,
        "automatic_threshold_change": False,
        "automatic_abstention_change": False,
        "promotion_authorized": False,
        "causal_claim_allowed": False,
        "paid_calls": 0,
        "external_sends": 0,
        "rule_version": RULE_VERSION,
    }
