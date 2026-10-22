"""Read-only freshness and confirmation-latency analysis for v45 intelligence.

Confirmed labels are not timeless. This module measures how long decisions took
to receive evidence-backed confirmation and how old those confirmations are at
a reproducible reference time. By default the reference is the latest valid
confirmation timestamp in the analyzed sample, never the wall clock.
"""
from __future__ import annotations

import datetime as dt
import math
import sqlite3
from collections import defaultdict

import mm_intelligence_calibration as calibration
from mm_core import timestamp

RULE_VERSION = "v45-confirmed-label-freshness-v1"


def _percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(probability * len(ordered)))
    return ordered[rank - 1]


def _parse(value) -> dt.datetime | None:
    if not value:
        return None
    try:
        return timestamp(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _days(delta: dt.timedelta) -> float:
    return delta.total_seconds() / 86400.0


def _stats(values: list[float]) -> dict:
    if not values:
        return {
            "count": 0,
            "min_days": None,
            "median_days": None,
            "p90_days": None,
            "max_days": None,
        }
    return {
        "count": len(values),
        "min_days": round(min(values), 4),
        "median_days": round(_percentile(values, 0.50), 4),
        "p90_days": round(_percentile(values, 0.90), 4),
        "max_days": round(max(values), 4),
    }


def _group_stats(rows: list[dict], field: str) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(field) or "unknown")].append(row)

    result = {}
    for key, group in sorted(grouped.items()):
        ages = [
            float(row["confirmation_age_days"])
            for row in group
            if row.get("confirmation_age_days") is not None
        ]
        latencies = [
            float(row["confirmation_latency_days"])
            for row in group
            if row.get("confirmation_latency_days") is not None
        ]
        result[key] = {
            "confirmed_examples": len(group),
            "confirmation_age": _stats(ages),
            "confirmation_latency": _stats(latencies),
        }
    return result


def freshness_report(
    d: sqlite3.Connection,
    *,
    as_of: str | None = None,
    limit: int = 5000,
    min_confirmed: int = 30,
    stale_after_days: float = 90.0,
    slow_confirmation_days: float = 30.0,
) -> dict:
    """Measure age and latency of evidence-backed confirmed labels."""
    bounded_limit = max(1, min(int(limit), 50000))
    minimum = max(1, int(min_confirmed))
    stale_after = max(0.0, float(stale_after_days))
    slow_after = max(0.0, float(slow_confirmation_days))

    examples = calibration.confirmed_examples(d, bounded_limit)
    ids = {
        int(row["ledger_id"])
        for row in examples
    } | {
        int(row["confirmation_ledger_id"])
        for row in examples
        if row.get("confirmation_ledger_id") is not None
    }

    timestamps_by_id: dict[int, str] = {}
    if ids:
        marks = ",".join("?" for _ in ids)
        rows = d.execute(
            f"SELECT id,recorded_at FROM intelligence_ledger "
            f"WHERE id IN ({marks})",
            sorted(ids),
        ).fetchall()
        timestamps_by_id = {
            int(row["id"]): row["recorded_at"]
            for row in rows
        }

    parsed_confirmations = [
        parsed
        for row in examples
        if (
            parsed := _parse(
                timestamps_by_id.get(int(row["confirmation_ledger_id"]))
            )
        ) is not None
    ]

    if as_of is not None:
        reference = _parse(as_of)
        if reference is None:
            raise ValueError("as_of must be a valid ISO-8601 timestamp")
        reference_source = "explicit"
    elif parsed_confirmations:
        reference = max(parsed_confirmations)
        reference_source = "latest_confirmation"
    else:
        reference = None
        reference_source = "unavailable"

    analyzed = []
    malformed = 0
    negative_latency = 0
    future_confirmation = 0

    for example in examples:
        original_at = _parse(
            timestamps_by_id.get(int(example["ledger_id"]))
        )
        confirmation_at = _parse(
            timestamps_by_id.get(int(example["confirmation_ledger_id"]))
        )
        latency_days = None
        age_days = None
        flags = []

        if original_at is None or confirmation_at is None:
            malformed += 1
            flags.append("TIMESTAMP_GAP")
        else:
            latency_days = _days(confirmation_at - original_at)
            if latency_days < 0:
                negative_latency += 1
                flags.append("NEGATIVE_CONFIRMATION_LATENCY")
                latency_days = None

        if confirmation_at is not None and reference is not None:
            age_days = _days(reference - confirmation_at)
            if age_days < 0:
                future_confirmation += 1
                flags.append("CONFIRMATION_AFTER_REFERENCE")
                age_days = None

        if latency_days is not None and latency_days > slow_after:
            flags.append("SLOW_CONFIRMATION")
        if age_days is not None and age_days > stale_after:
            flags.append("STALE_CONFIRMATION")

        analyzed.append({
            "ledger_id": int(example["ledger_id"]),
            "prospect_id": int(example["prospect_id"]),
            "confirmation_ledger_id": int(
                example["confirmation_ledger_id"]
            ),
            "confirmation": example.get("confirmation"),
            "rule_version": example.get("rule_version") or "unknown",
            "source": example.get("source") or "unknown",
            "stage": example.get("stage") or "unknown",
            "observed_correct": int(example["observed_correct"]),
            "confirmation_latency_days": (
                round(latency_days, 4)
                if latency_days is not None
                else None
            ),
            "confirmation_age_days": (
                round(age_days, 4)
                if age_days is not None
                else None
            ),
            "flags": flags,
        })

    ages = [
        float(row["confirmation_age_days"])
        for row in analyzed
        if row["confirmation_age_days"] is not None
    ]
    latencies = [
        float(row["confirmation_latency_days"])
        for row in analyzed
        if row["confirmation_latency_days"] is not None
    ]
    stale_count = sum(
        1 for row in analyzed
        if "STALE_CONFIRMATION" in row["flags"]
    )
    slow_count = sum(
        1 for row in analyzed
        if "SLOW_CONFIRMATION" in row["flags"]
    )

    flags = []
    if len(examples) < minimum:
        flags.append("LOW_SAMPLE")
    if malformed:
        flags.append("TIMESTAMP_GAPS")
    if negative_latency:
        flags.append("NEGATIVE_CONFIRMATION_LATENCY")
    if future_confirmation:
        flags.append("CONFIRMATION_AFTER_REFERENCE")
    if stale_count:
        flags.append("STALE_LABELS")
    if slow_count:
        flags.append("SLOW_CONFIRMATION")

    if len(examples) < minimum:
        status = "INSUFFICIENT_HISTORY"
    elif malformed or negative_latency or future_confirmation:
        status = "TIMESTAMP_QUALITY_WARNINGS"
    elif stale_count or slow_count:
        status = "FRESHNESS_WARNINGS"
    else:
        status = "MEASURED"

    return {
        "status": status,
        "flags": flags,
        "confirmed_examples": len(examples),
        "minimum_confirmed": minimum,
        "reference_time": (
            reference.isoformat()
            if reference is not None
            else None
        ),
        "reference_source": reference_source,
        "stale_after_days": stale_after,
        "slow_confirmation_days": slow_after,
        "stale_confirmations": stale_count,
        "slow_confirmations": slow_count,
        "malformed_or_missing_timestamps": malformed,
        "negative_confirmation_latencies": negative_latency,
        "confirmations_after_reference": future_confirmation,
        "confirmation_age": _stats(ages),
        "confirmation_latency": _stats(latencies),
        "by_rule_version": _group_stats(analyzed, "rule_version"),
        "by_source": _group_stats(analyzed, "source"),
        "by_confirmation_channel": _group_stats(
            analyzed,
            "confirmation",
        ),
        "examples": analyzed,
        "method": (
            "Latency is original decision recorded_at to confirmation ledger "
            "recorded_at. Age is confirmation time to the explicit as_of, or "
            "to the latest valid confirmation in the sample when as_of is "
            "omitted. No wall-clock time is used by default."
        ),
        "read_only": True,
        "automatic_label_expiry": False,
        "automatic_rule_change": False,
        "automatic_promotion_gate_change": False,
        "promotion_authorized": False,
        "paid_calls": 0,
        "external_sends": 0,
        "rule_version": RULE_VERSION,
    }
