"""Read-only drift detection for v45 intelligence.

Compares recent confirmed decision outcomes with the immediately preceding
confirmed window. Drift signals are advisory only: no thresholds, routes,
rules, approvals, models, or external actions are changed automatically.
"""
from __future__ import annotations

import sqlite3
from collections import Counter

import mm_intelligence_calibration as calibration

RULE_VERSION = "v45-intelligence-drift-v1"


def _expected_polarity(example: dict) -> int:
    original = int(example["decision_polarity"])
    correct = int(example["observed_correct"])
    return original if correct else 1 - original


def _metrics(rows: list[dict]) -> dict:
    count = len(rows)
    if not count:
        return {
            "count": 0,
            "accuracy": None,
            "avg_confidence": None,
            "brier_score": None,
            "positive_label_rate": None,
            "errors": 0,
        }

    correct = sum(int(row["observed_correct"]) for row in rows)
    avg_confidence = sum(float(row["confidence"]) for row in rows) / count
    brier = sum(
        (float(row["confidence"]) - int(row["observed_correct"])) ** 2
        for row in rows
    ) / count
    positive_labels = sum(_expected_polarity(row) for row in rows)
    return {
        "count": count,
        "accuracy": round(correct / count, 4),
        "avg_confidence": round(avg_confidence, 4),
        "brier_score": round(brier, 6),
        "positive_label_rate": round(positive_labels / count, 4),
        "errors": count - correct,
    }


def _composition(rows: list[dict], field: str, fallback: str) -> dict:
    counts = Counter(str(row.get(field) or fallback) for row in rows)
    return dict(sorted(counts.items()))


def drift_report(
    d: sqlite3.Connection,
    window: int = 25,
    min_samples: int = 10,
    accuracy_drop_threshold: float = 0.15,
    brier_increase_threshold: float = 0.10,
    confidence_shift_threshold: float = 0.15,
    label_shift_threshold: float = 0.25,
    limit: int = 5000,
) -> dict:
    """Compare adjacent confirmed-decision windows for material drift."""
    window_size = max(1, min(int(window), 1000))
    minimum = max(1, min(int(min_samples), window_size))
    bounded_limit = max(window_size * 2, min(int(limit), 50000))

    accuracy_threshold = abs(float(accuracy_drop_threshold))
    brier_threshold = abs(float(brier_increase_threshold))
    confidence_threshold = abs(float(confidence_shift_threshold))
    label_threshold = abs(float(label_shift_threshold))

    confirmed = calibration.confirmed_examples(d, bounded_limit)
    recent = confirmed[:window_size]
    prior = confirmed[window_size:window_size * 2]

    recent_metrics = _metrics(recent)
    prior_metrics = _metrics(prior)
    enough = len(recent) >= minimum and len(prior) >= minimum

    deltas = {
        "accuracy": None,
        "brier_score": None,
        "avg_confidence": None,
        "positive_label_rate": None,
    }
    flags: list[str] = []

    if enough:
        deltas = {
            "accuracy": round(
                recent_metrics["accuracy"] - prior_metrics["accuracy"],
                4,
            ),
            "brier_score": round(
                recent_metrics["brier_score"] - prior_metrics["brier_score"],
                6,
            ),
            "avg_confidence": round(
                recent_metrics["avg_confidence"]
                - prior_metrics["avg_confidence"],
                4,
            ),
            "positive_label_rate": round(
                recent_metrics["positive_label_rate"]
                - prior_metrics["positive_label_rate"],
                4,
            ),
        }

        if deltas["accuracy"] <= -accuracy_threshold:
            flags.append("ACCURACY_DROP")
        if deltas["brier_score"] >= brier_threshold:
            flags.append("BRIER_WORSENING")
        if abs(deltas["avg_confidence"]) >= confidence_threshold:
            flags.append("CONFIDENCE_SHIFT")
        if abs(deltas["positive_label_rate"]) >= label_threshold:
            flags.append("LABEL_MIX_SHIFT")

    if not enough:
        status = "INSUFFICIENT_HISTORY"
    elif flags:
        status = "REVIEW_DRIFT"
    else:
        status = "STABLE"

    return {
        "status": status,
        "flags": flags,
        "recent": {
            "metrics": recent_metrics,
            "rule_versions": _composition(
                recent,
                "rule_version",
                "unknown",
            ),
            "sources": _composition(recent, "source", "unknown"),
        },
        "prior": {
            "metrics": prior_metrics,
            "rule_versions": _composition(
                prior,
                "rule_version",
                "unknown",
            ),
            "sources": _composition(prior, "source", "unknown"),
        },
        "deltas_recent_minus_prior": deltas,
        "window": window_size,
        "minimum_samples_per_window": minimum,
        "confirmed_examples_available": len(confirmed),
        "thresholds": {
            "accuracy_drop": accuracy_threshold,
            "brier_increase": brier_threshold,
            "confidence_shift": confidence_threshold,
            "label_mix_shift": label_threshold,
        },
        "method": (
            "Adjacent windows are ordered by confirmed intelligence ledger id, "
            "newest first. Signals are descriptive and may reflect changing "
            "case mix rather than model or rule degradation."
        ),
        "automatic_rule_change": False,
        "automatic_source_change": False,
        "promotion_authorized": False,
        "read_only": True,
        "paid_calls": 0,
        "external_sends": 0,
        "rule_version": RULE_VERSION,
    }
