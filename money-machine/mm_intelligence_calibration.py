"""Read-only confidence calibration for v45 intelligence decisions.

Calibration only uses decisions with later evidence strong enough to establish a
label: explicit human corrections, or positive observed outcomes. It never
changes thresholds, pipeline state, approvals, outreach, or model routing.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

POSITIVE_DECISIONS = frozenset({
    "ACCEPTED",
    "QUALIFIED",
    "CONTACT_PENDING",
    "CONTACT_RESOLVED",
    "VERIFIED",
    "REMEDIATION_PENDING",
    "DEMO_PENDING",
    "DEMO_READY",
    "QA_PENDING",
    "OUTREACH_PENDING",
    "APPROVAL_PENDING",
    "APPROVED",
    "READY_TO_SEND",
    "SENT",
    "RESPONDED",
    "CONVERTED",
})

NEGATIVE_DECISIONS = frozenset({
    "REJECTED",
    "SUPPRESSED",
    "DUPLICATE",
    "PERMANENT_FAILURE",
})

POSITIVE_OUTCOMES = frozenset({
    "REPLIED",
    "CALL_OR_DISCOVERY",
    "PROPOSAL_SENT",
    "WON",
})

_EXCLUDED_DISPOSITIONS = frozenset({"HUMAN_CORRECTED", "OUTCOME_OBSERVED"})


def _table_exists(d: sqlite3.Connection, name: str) -> bool:
    return bool(
        d.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
    )


def _polarity(decision: str | None) -> int | None:
    value = str(decision or "")
    if value in POSITIVE_DECISIONS:
        return 1
    if value in NEGATIVE_DECISIONS:
        return 0
    return None


def _confidence(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= result <= 1.0:
        return None
    return result


def _previous_real_decision(rows: list[dict], index: int) -> dict | None:
    for row in reversed(rows[:index]):
        if row.get("disposition") in _EXCLUDED_DISPOSITIONS:
            continue
        if _polarity(row.get("decision")) is not None:
            return row
    return None


def _eligible_decisions(rows: list[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if row.get("disposition") not in _EXCLUDED_DISPOSITIONS
        and _polarity(row.get("decision")) is not None
        and _confidence(row.get("confidence")) is not None
    ]


def confirmed_examples(d: sqlite3.Connection, limit: int = 5000) -> list[dict]:
    """Return original decisions with evidence-backed correctness labels.

    Human corrections are highest-authority. Positive observed outcomes confirm
    a prior positive decision or contradict a prior negative decision. Ambiguous
    outcomes such as LOST or NO_RESPONSE are deliberately not treated as proof
    that the original qualification decision was wrong.
    """
    if not _table_exists(d, "intelligence_ledger"):
        return []

    bounded_limit = max(1, min(int(limit), 50000))
    rows = [
        dict(row)
        for row in d.execute(
            "SELECT * FROM intelligence_ledger ORDER BY id"
        ).fetchall()
    ]
    by_prospect: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        by_prospect[int(row["prospect_id"])].append(row)

    labeled: dict[int, tuple[int, dict]] = {}
    for prospect_rows in by_prospect.values():
        for index, evidence in enumerate(prospect_rows):
            original = None
            observed_correct = None
            confirmation = None
            priority = 0

            if evidence.get("disposition") == "HUMAN_CORRECTED":
                candidate = _previous_real_decision(prospect_rows, index)
                candidate_polarity = _polarity(
                    candidate.get("decision") if candidate else None
                )
                corrected_polarity = _polarity(evidence.get("decision"))
                if (
                    candidate is not None
                    and candidate_polarity is not None
                    and corrected_polarity is not None
                ):
                    original = candidate
                    observed_correct = int(
                        candidate_polarity == corrected_polarity
                    )
                    confirmation = "human_correction"
                    priority = 2

            later_outcome = evidence.get("later_outcome")
            if (
                original is None
                and later_outcome in POSITIVE_OUTCOMES
            ):
                candidate = (
                    evidence
                    if evidence.get("disposition") not in _EXCLUDED_DISPOSITIONS
                    and _polarity(evidence.get("decision")) is not None
                    else _previous_real_decision(prospect_rows, index)
                )
                candidate_polarity = _polarity(
                    candidate.get("decision") if candidate else None
                )
                if candidate is not None and candidate_polarity is not None:
                    original = candidate
                    observed_correct = int(candidate_polarity == 1)
                    confirmation = "positive_later_outcome"
                    priority = 1

            if original is None or observed_correct is None:
                continue
            confidence = _confidence(original.get("confidence"))
            if confidence is None:
                continue

            original_id = int(original["id"])
            existing = labeled.get(original_id)
            if existing is not None and existing[0] > priority:
                continue
            labeled[original_id] = (
                priority,
                {
                    "ledger_id": original_id,
                    "prospect_id": int(original["prospect_id"]),
                    "decision": original["decision"],
                    "decision_polarity": _polarity(original["decision"]),
                    "confidence": confidence,
                    "observed_correct": observed_correct,
                    "confirmation": confirmation,
                    "confirmation_ledger_id": int(evidence["id"]),
                    "later_outcome": later_outcome,
                    "rule_version": str(original.get("rule_version") or ""),
                    "stage": str(original.get("stage") or ""),
                    "source": str(original.get("source") or ""),
                },
            )

    examples = [
        value
        for _, value in sorted(
            (item for item in labeled.values()),
            key=lambda item: item[1]["ledger_id"],
            reverse=True,
        )
    ]
    return examples[:bounded_limit]


def _bin_index(confidence: float, bins: int) -> int:
    if confidence >= 1.0:
        return bins - 1
    return min(bins - 1, int(confidence * bins))


def _summary(rows: list[dict]) -> dict:
    count = len(rows)
    if not count:
        return {
            "count": 0,
            "avg_confidence": None,
            "observed_accuracy": None,
            "brier_score": None,
        }
    avg_confidence = sum(row["confidence"] for row in rows) / count
    accuracy = sum(row["observed_correct"] for row in rows) / count
    brier = sum(
        (row["confidence"] - row["observed_correct"]) ** 2
        for row in rows
    ) / count
    return {
        "count": count,
        "avg_confidence": round(avg_confidence, 4),
        "observed_accuracy": round(accuracy, 4),
        "brier_score": round(brier, 6),
    }


def calibration_report(
    d: sqlite3.Connection,
    bins: int = 10,
    limit: int = 5000,
    min_samples: int = 30,
) -> dict:
    """Measure confidence reliability over evidence-backed examples only."""
    if not 2 <= int(bins) <= 20:
        raise ValueError("bins must be between 2 and 20")
    bounded_bins = int(bins)
    bounded_limit = max(1, min(int(limit), 50000))
    minimum = max(1, int(min_samples))

    if not _table_exists(d, "intelligence_ledger"):
        return {
            "status": "NO_CONFIRMED_EXAMPLES",
            "confirmed_examples": 0,
            "eligible_decisions": 0,
            "coverage": 0.0,
            "bins": [],
            "expected_calibration_error": None,
            "brier_score": None,
            "rule_versions": {},
            "advisory_only": True,
            "paid_calls": 0,
            "external_sends": 0,
        }

    all_rows = [
        dict(row)
        for row in d.execute(
            "SELECT * FROM intelligence_ledger ORDER BY id"
        ).fetchall()
    ]
    eligible = _eligible_decisions(all_rows)
    examples = confirmed_examples(d, bounded_limit)

    grouped_bins: list[list[dict]] = [[] for _ in range(bounded_bins)]
    for row in examples:
        grouped_bins[_bin_index(row["confidence"], bounded_bins)].append(row)

    bin_rows = []
    ece = 0.0
    total = len(examples)
    for index, rows in enumerate(grouped_bins):
        lower = index / bounded_bins
        upper = (index + 1) / bounded_bins
        stats = _summary(rows)
        gap = None
        if rows:
            gap = abs(stats["avg_confidence"] - stats["observed_accuracy"])
            ece += (len(rows) / total) * gap
        bin_rows.append({
            "lower": round(lower, 4),
            "upper": round(upper, 4),
            **stats,
            "calibration_gap": round(gap, 4) if gap is not None else None,
        })

    overall = _summary(examples)
    by_rule: dict[str, list[dict]] = defaultdict(list)
    for row in examples:
        by_rule[row["rule_version"] or "unknown"].append(row)

    coverage = len(examples) / len(eligible) if eligible else 0.0
    if not examples:
        status = "NO_CONFIRMED_EXAMPLES"
    elif len(examples) < minimum:
        status = "LOW_SAMPLE"
    else:
        status = "MEASURED"

    return {
        "status": status,
        "confirmed_examples": len(examples),
        "eligible_decisions": len(eligible),
        "coverage": round(coverage, 4),
        "avg_confidence": overall["avg_confidence"],
        "observed_accuracy": overall["observed_accuracy"],
        "expected_calibration_error": round(ece, 6) if examples else None,
        "brier_score": overall["brier_score"],
        "bins": bin_rows,
        "rule_versions": {
            version: _summary(rows)
            for version, rows in sorted(by_rule.items())
        },
        "sample_warning": (
            None
            if len(examples) >= minimum
            else (
                f"Only {len(examples)} confirmed examples; "
                f"minimum requested is {minimum}."
            )
        ),
        "method": (
            "Human corrections and positive later outcomes only. "
            "Ambiguous outcomes are not treated as correctness labels."
        ),
        "advisory_only": True,
        "auto_threshold_changes": False,
        "paid_calls": 0,
        "external_sends": 0,
    }
