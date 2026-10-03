"""Read-only historical evidence-value analysis for v45 intelligence.

Measures associations between named missing-evidence fields and confirmed
decision errors. These are observational associations, not causal estimates.
Nothing here changes evidence priorities, pipeline behavior, rules, models,
approvals, or external actions.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict

import mm_intelligence_calibration as calibration

RULE_VERSION = "v45-evidence-value-v1"


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

    fields = set()
    for item in missing:
        if not isinstance(item, str):
            continue
        field = item.strip()[:80]
        if field:
            fields.add(field)
    return sorted(fields)


def evidence_value_report(
    d: sqlite3.Connection,
    limit: int = 5000,
    min_samples: int = 5,
    high_confidence_threshold: float = 0.80,
) -> dict:
    """Describe confirmed error association for named missing evidence."""
    bounded_limit = max(1, min(int(limit), 50000))
    minimum = max(1, int(min_samples))
    high_threshold = min(1.0, max(0.0, float(high_confidence_threshold)))

    if not _table_exists(d, "intelligence_ledger"):
        return {
            "fields": [],
            "field_count": 0,
            "confirmed_examples": 0,
            "confirmed_error_rate": None,
            "examples_with_named_missing_evidence": 0,
            "coverage": 0.0,
            "read_only": True,
            "causal_claim_allowed": False,
            "automatic_evidence_priority_change": False,
            "paid_calls": 0,
            "external_sends": 0,
            "rule_version": RULE_VERSION,
        }

    confirmed = calibration.confirmed_examples(d, bounded_limit)
    ledger_ids = [int(row["ledger_id"]) for row in confirmed]
    ledger_by_id = {}
    if ledger_ids:
        marks = ",".join("?" for _ in ledger_ids)
        rows = d.execute(
            f"SELECT id,derived_evidence FROM intelligence_ledger "
            f"WHERE id IN ({marks})",
            ledger_ids,
        ).fetchall()
        ledger_by_id = {int(row["id"]): row["derived_evidence"] for row in rows}

    total = len(confirmed)
    total_errors = sum(
        1 for row in confirmed if int(row["observed_correct"]) == 0
    )
    baseline_error_rate = (
        total_errors / total
        if total
        else None
    )

    stats = defaultdict(lambda: {
        "confirmed_examples": 0,
        "errors": 0,
        "correct": 0,
        "high_confidence_errors": 0,
        "confirmed_false_positives": 0,
        "confirmed_false_negatives": 0,
        "stages": Counter(),
        "rule_versions": Counter(),
        "confirmations": Counter(),
    })
    examples_with_missing = 0

    for example in confirmed:
        fields = _missing_fields(
            ledger_by_id.get(int(example["ledger_id"]))
        )
        if not fields:
            continue
        examples_with_missing += 1
        is_error = int(example["observed_correct"]) == 0
        original_polarity = int(example["decision_polarity"])
        confidence = float(example["confidence"])

        for field in fields:
            item = stats[field]
            item["confirmed_examples"] += 1
            item["stages"][str(example.get("stage") or "unknown")] += 1
            item["rule_versions"][
                str(example.get("rule_version") or "unknown")
            ] += 1
            item["confirmations"][
                str(example.get("confirmation") or "unknown")
            ] += 1

            if is_error:
                item["errors"] += 1
                if confidence >= high_threshold:
                    item["high_confidence_errors"] += 1
                if original_polarity == 1:
                    item["confirmed_false_positives"] += 1
                else:
                    item["confirmed_false_negatives"] += 1
            else:
                item["correct"] += 1

    fields = []
    for field, item in stats.items():
        count = item["confirmed_examples"]
        error_rate = item["errors"] / count if count else 0.0
        delta = (
            error_rate - baseline_error_rate
            if baseline_error_rate is not None
            else None
        )
        if count < minimum:
            signal = "INSUFFICIENT_EVIDENCE"
        elif delta is not None and delta >= 0.15:
            signal = "ELEVATED_ERROR_ASSOCIATION"
        elif item["errors"] == 0:
            signal = "NO_CONFIRMED_ERRORS_IN_SAMPLE"
        else:
            signal = "OBSERVE"

        fields.append({
            "field": field,
            "confirmed_examples": count,
            "errors": item["errors"],
            "correct": item["correct"],
            "error_rate": round(error_rate, 4),
            "error_rate_delta_vs_all_confirmed": (
                round(delta, 4)
                if delta is not None
                else None
            ),
            "high_confidence_errors": item["high_confidence_errors"],
            "confirmed_false_positives": item["confirmed_false_positives"],
            "confirmed_false_negatives": item["confirmed_false_negatives"],
            "stages": dict(sorted(item["stages"].items())),
            "rule_versions": dict(sorted(item["rule_versions"].items())),
            "confirmations": dict(sorted(item["confirmations"].items())),
            "signal": signal,
            "minimum_sample": minimum,
            "causal_claim_allowed": False,
            "automatic_priority_change": False,
        })

    fields.sort(
        key=lambda item: (
            -item["errors"],
            -item["confirmed_examples"],
            item["field"],
        )
    )
    return {
        "fields": fields,
        "field_count": len(fields),
        "confirmed_examples": total,
        "confirmed_errors": total_errors,
        "confirmed_error_rate": (
            round(baseline_error_rate, 4)
            if baseline_error_rate is not None
            else None
        ),
        "examples_with_named_missing_evidence": examples_with_missing,
        "coverage": (
            round(examples_with_missing / total, 4)
            if total
            else 0.0
        ),
        "high_confidence_threshold": high_threshold,
        "method": (
            "Fields come only from derived_evidence.missing_evidence on "
            "confirmed decisions. Elevated error association is descriptive; "
            "it does not prove that acquiring the field would prevent errors."
        ),
        "read_only": True,
        "causal_claim_allowed": False,
        "automatic_evidence_priority_change": False,
        "paid_calls": 0,
        "external_sends": 0,
        "rule_version": RULE_VERSION,
    }
