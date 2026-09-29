"""Read-only historical review-efficiency analysis for v45 intelligence.

Measures how often decision-time review signals catch later-confirmed mistakes.
Signals are observational diagnostics only; they never change the live review
queue, thresholds, rules, routes, approvals, models, or external actions.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict

import mm_intelligence_calibration as calibration

RULE_VERSION = "v45-review-efficiency-v1"
_EXCLUDED = frozenset({"HUMAN_CORRECTED", "OUTCOME_OBSERVED"})


def _table_exists(d: sqlite3.Connection, name: str) -> bool:
    return bool(
        d.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
    )


def _missing_fields(value) -> list[str]:
    if isinstance(value, dict):
        derived = value
    else:
        try:
            decoded = json.loads(value or "{}")
        except (TypeError, ValueError):
            return []
        derived = decoded if isinstance(decoded, dict) else {}
    missing = derived.get("missing_evidence", [])
    if not isinstance(missing, list):
        return []
    return sorted({
        item.strip()[:80]
        for item in missing
        if isinstance(item, str) and item.strip()
    })


def _decision_signals(
    d: sqlite3.Connection,
    low_confidence_threshold: float,
) -> dict[int, set[str]]:
    rows = d.execute(
        """SELECT id,prospect_id,decision,disposition,confidence,
                  rule_version,stage,source,derived_evidence
           FROM intelligence_ledger ORDER BY id"""
    ).fetchall()

    previous_polarity: dict[tuple[int, str, str], int] = {}
    signals: dict[int, set[str]] = {}

    for raw in rows:
        row = dict(raw)
        if row.get("disposition") in _EXCLUDED:
            continue
        polarity = calibration._polarity(row.get("decision"))
        if polarity is None:
            continue

        current: set[str] = set()
        confidence = calibration._confidence(row.get("confidence"))
        missing = _missing_fields(row.get("derived_evidence"))

        if confidence is not None and confidence < low_confidence_threshold:
            current.add("low_confidence")
        if missing:
            current.add("missing_evidence")
        if len(missing) >= 2:
            current.add("multiple_missing_evidence")
        if not str(row.get("source") or "").strip():
            current.add("missing_source")

        key = (
            int(row["prospect_id"]),
            str(row.get("rule_version") or "unknown"),
            str(row.get("stage") or "unknown"),
        )
        prior = previous_polarity.get(key)
        if prior is not None and prior != int(polarity):
            current.add("prior_polarity_change")

        signals[int(row["id"])] = current
        previous_polarity[key] = int(polarity)

    return signals


def _metric(
    signal: str,
    examples: list[dict],
    signal_map: dict[int, set[str]],
    total_errors: int,
    baseline_error_rate: float | None,
    minimum_signal_samples: int,
) -> dict:
    flagged = [
        row
        for row in examples
        if signal in signal_map.get(int(row["ledger_id"]), set())
    ]
    count = len(flagged)
    errors = sum(
        1 for row in flagged
        if int(row["observed_correct"]) == 0
    )
    correct = count - errors
    precision = errors / count if count else None
    recall = errors / total_errors if total_errors else None
    workload = count / len(examples) if examples else 0.0
    lift = (
        precision - baseline_error_rate
        if precision is not None and baseline_error_rate is not None
        else None
    )
    reviews_per_error = count / errors if errors else None

    if count == 0:
        status = "NO_EXAMPLES"
    elif count < minimum_signal_samples:
        status = "LOW_SAMPLE"
    elif lift is not None and lift >= 0.15:
        status = "ELEVATED_ERROR_ASSOCIATION"
    elif lift is not None and lift <= 0:
        status = "NO_ERROR_LIFT"
    else:
        status = "OBSERVE"

    return {
        "signal": signal,
        "flagged_confirmed_examples": count,
        "errors_caught": errors,
        "correct_flagged": correct,
        "error_precision": (
            round(precision, 4)
            if precision is not None
            else None
        ),
        "error_recall": (
            round(recall, 4)
            if recall is not None
            else None
        ),
        "review_workload_rate": round(workload, 4),
        "error_rate_lift_vs_all_confirmed": (
            round(lift, 4)
            if lift is not None
            else None
        ),
        "reviews_per_error_caught": (
            round(reviews_per_error, 4)
            if reviews_per_error is not None
            else None
        ),
        "status": status,
        "minimum_signal_samples": minimum_signal_samples,
        "automatic_queue_change": False,
    }


def review_efficiency_report(
    d: sqlite3.Connection,
    *,
    limit: int = 5000,
    min_confirmed: int = 30,
    min_signal_samples: int = 5,
    low_confidence_threshold: float = 0.80,
) -> dict:
    """Measure confirmed-error yield of decision-time review signals."""
    bounded_limit = max(1, min(int(limit), 50000))
    minimum_confirmed = max(1, int(min_confirmed))
    minimum_signal = max(1, int(min_signal_samples))
    confidence_threshold = min(
        1.0,
        max(0.0, float(low_confidence_threshold)),
    )

    if not _table_exists(d, "intelligence_ledger"):
        return {
            "status": "INSUFFICIENT_HISTORY",
            "confirmed_examples": 0,
            "confirmed_errors": 0,
            "baseline_error_rate": None,
            "signals": [],
            "combined": None,
            "read_only": True,
            "automatic_queue_change": False,
            "automatic_threshold_change": False,
            "paid_calls": 0,
            "external_sends": 0,
            "rule_version": RULE_VERSION,
        }

    examples = calibration.confirmed_examples(d, bounded_limit)
    total = len(examples)
    total_errors = sum(
        1 for row in examples
        if int(row["observed_correct"]) == 0
    )
    baseline_error_rate = (
        total_errors / total
        if total
        else None
    )
    signal_map = _decision_signals(d, confidence_threshold)

    signal_names = (
        "low_confidence",
        "missing_evidence",
        "multiple_missing_evidence",
        "missing_source",
        "prior_polarity_change",
    )
    metrics = [
        _metric(
            signal,
            examples,
            signal_map,
            total_errors,
            baseline_error_rate,
            minimum_signal,
        )
        for signal in signal_names
    ]

    any_signal_map = {
        ledger_id: ({"any_review_signal"} if values else set())
        for ledger_id, values in signal_map.items()
    }
    combined = _metric(
        "any_review_signal",
        examples,
        any_signal_map,
        total_errors,
        baseline_error_rate,
        minimum_signal,
    )

    metrics.sort(
        key=lambda item: (
            -item["errors_caught"],
            -(
                item["error_precision"]
                if item["error_precision"] is not None
                else -1.0
            ),
            item["signal"],
        )
    )

    status = (
        "MEASURED"
        if total >= minimum_confirmed
        else "INSUFFICIENT_HISTORY"
    )
    return {
        "status": status,
        "confirmed_examples": total,
        "minimum_confirmed": minimum_confirmed,
        "confirmed_errors": total_errors,
        "baseline_error_rate": (
            round(baseline_error_rate, 4)
            if baseline_error_rate is not None
            else None
        ),
        "low_confidence_threshold": confidence_threshold,
        "signals": metrics,
        "combined": combined,
        "method": (
            "Signals are computed using only information available at each "
            "original decision. Later corrections/outcomes supply labels but "
            "are never used as review signals. Associations are historical and "
            "do not prove a signal will prevent future errors."
        ),
        "read_only": True,
        "causal_claim_allowed": False,
        "automatic_queue_change": False,
        "automatic_threshold_change": False,
        "promotion_authorized": False,
        "paid_calls": 0,
        "external_sends": 0,
        "rule_version": RULE_VERSION,
    }
