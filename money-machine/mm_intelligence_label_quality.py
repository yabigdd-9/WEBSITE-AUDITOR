"""Read-only label-quality diagnostics for v45 intelligence.

Assesses the composition of evidence-backed confirmed labels used by
calibration, drift, challengers, and readiness. It explicitly surfaces known
selection asymmetries without changing rules, thresholds, promotion gates,
queues, models, or external actions.
"""
from __future__ import annotations

import sqlite3
from collections import Counter

import mm_intelligence_calibration as calibration

RULE_VERSION = "v45-label-quality-v1"


def _expected_label(example: dict) -> str:
    original = int(example["decision_polarity"])
    correct = int(example["observed_correct"])
    expected = original if correct else 1 - original
    return "POSITIVE" if expected == 1 else "NEGATIVE"


def _distribution(rows: list[dict], field: str, fallback: str) -> dict:
    return dict(sorted(
        Counter(str(row.get(field) or fallback) for row in rows).items()
    ))


def _largest_share(counts: dict, total: int) -> float | None:
    if not counts or not total:
        return None
    return max(counts.values()) / total


def label_quality_report(
    d: sqlite3.Connection,
    *,
    limit: int = 5000,
    min_confirmed: int = 30,
    max_source_share: float = 0.80,
) -> dict:
    """Describe confirmed-label representativeness and known asymmetries."""
    bounded_limit = max(1, min(int(limit), 50000))
    minimum = max(1, int(min_confirmed))
    source_share_limit = min(1.0, max(0.0, float(max_source_share)))

    examples = calibration.confirmed_examples(d, bounded_limit)
    total = len(examples)

    confirmation_channels = _distribution(
        examples,
        "confirmation",
        "unknown",
    )
    expected_classes = dict(sorted(Counter(
        _expected_label(row) for row in examples
    ).items()))
    sources = _distribution(examples, "source", "unknown")
    rule_versions = _distribution(
        examples,
        "rule_version",
        "unknown",
    )
    stages = _distribution(examples, "stage", "unknown")
    prospects = Counter(int(row["prospect_id"]) for row in examples)

    largest_confirmation_share = _largest_share(
        confirmation_channels,
        total,
    )
    largest_source_share = _largest_share(sources, total)
    largest_rule_share = _largest_share(rule_versions, total)
    largest_stage_share = _largest_share(stages, total)
    unique_prospects = len(prospects)
    repeated_prospect_examples = sum(
        count - 1 for count in prospects.values() if count > 1
    )

    flags: list[str] = []
    if total < minimum:
        flags.append("LOW_SAMPLE")
    if total and len(expected_classes) < 2:
        flags.append("SINGLE_EXPECTED_CLASS")
    if total and len(confirmation_channels) < 2:
        flags.append("SINGLE_CONFIRMATION_CHANNEL")
    if (
        largest_source_share is not None
        and largest_source_share > source_share_limit
    ):
        flags.append("SOURCE_CONCENTRATION")
    if repeated_prospect_examples:
        flags.append("REPEATED_PROSPECT_LABELS")

    if total < minimum:
        status = "INSUFFICIENT_HISTORY"
    elif flags:
        status = "REPRESENTATIVENESS_WARNINGS"
    else:
        status = "MEASURED"

    return {
        "status": status,
        "flags": flags,
        "confirmed_examples": total,
        "minimum_confirmed": minimum,
        "confirmation_channels": confirmation_channels,
        "expected_classes": expected_classes,
        "sources": sources,
        "rule_versions": rule_versions,
        "stages": stages,
        "unique_prospects": unique_prospects,
        "repeated_prospect_examples": repeated_prospect_examples,
        "largest_confirmation_channel_share": (
            round(largest_confirmation_share, 4)
            if largest_confirmation_share is not None
            else None
        ),
        "largest_source_share": (
            round(largest_source_share, 4)
            if largest_source_share is not None
            else None
        ),
        "largest_rule_version_share": (
            round(largest_rule_share, 4)
            if largest_rule_share is not None
            else None
        ),
        "largest_stage_share": (
            round(largest_stage_share, 4)
            if largest_stage_share is not None
            else None
        ),
        "max_source_share": source_share_limit,
        "known_label_asymmetry": (
            "Positive later outcomes can confirm positive decisions or expose "
            "false negatives, but ambiguous negative outcomes are deliberately "
            "not treated as proof of a negative ground-truth label. Human "
            "corrections can contribute either expected class."
        ),
        "method": (
            "Composition is measured only over evidence-backed confirmed "
            "examples. Warnings identify concentration or selection concerns; "
            "they do not prove the sample is invalid or future performance will "
            "match historical observations."
        ),
        "read_only": True,
        "causal_claim_allowed": False,
        "automatic_label_policy_change": False,
        "automatic_promotion_gate_change": False,
        "promotion_authorized": False,
        "paid_calls": 0,
        "external_sends": 0,
        "rule_version": RULE_VERSION,
    }
