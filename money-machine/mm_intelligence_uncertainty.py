"""Read-only statistical uncertainty analysis for v45 intelligence.

Adds confidence intervals around confirmed accuracy/error rates and exact
matched-pair tests for rule-version comparisons. Statistical evidence remains
advisory and never grants promotion, merge, deployment, routing, threshold, or
external-action authority.
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from statistics import NormalDist

import mm_intelligence_calibration as calibration
import mm_intelligence_strategy as strategy

RULE_VERSION = "v45-statistical-uncertainty-v1"


def wilson_interval(
    successes: int,
    total: int,
    confidence_level: float = 0.95,
) -> dict:
    """Return a Wilson score interval for a binomial proportion."""
    successes = int(successes)
    total = int(total)
    confidence = float(confidence_level)
    if total < 0 or successes < 0 or successes > total:
        raise ValueError("Require 0 <= successes <= total")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    if total == 0:
        return {
            "estimate": None,
            "lower": None,
            "upper": None,
            "confidence_level": confidence,
            "n": 0,
            "successes": 0,
        }

    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    p = successes / total
    z2 = z * z
    denominator = 1.0 + z2 / total
    center = (p + z2 / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            p * (1.0 - p) / total
            + z2 / (4.0 * total * total)
        )
        / denominator
    )
    return {
        "estimate": round(p, 6),
        "lower": round(max(0.0, center - margin), 6),
        "upper": round(min(1.0, center + margin), 6),
        "confidence_level": confidence,
        "n": total,
        "successes": successes,
    }


def exact_mcnemar_p(
    a_only_correct: int,
    b_only_correct: int,
) -> float:
    """Two-sided exact McNemar p-value using discordant matched pairs."""
    a_only = int(a_only_correct)
    b_only = int(b_only_correct)
    if a_only < 0 or b_only < 0:
        raise ValueError("Discordant pair counts must be non-negative")
    discordant = a_only + b_only
    if discordant == 0:
        return 1.0

    tail = min(a_only, b_only)
    numerator = sum(
        math.comb(discordant, i)
        for i in range(tail + 1)
    )
    probability = numerator / (2 ** discordant)
    return round(min(1.0, 2.0 * probability), 12)


def _accuracy_summary(
    rows: list[dict],
    confidence_level: float,
) -> dict:
    total = len(rows)
    correct = sum(int(row["observed_correct"]) for row in rows)
    errors = total - correct
    return {
        "confirmed_examples": total,
        "correct": correct,
        "errors": errors,
        "accuracy": wilson_interval(
            correct,
            total,
            confidence_level,
        ),
        "error_rate": wilson_interval(
            errors,
            total,
            confidence_level,
        ),
    }


def uncertainty_report(
    d: sqlite3.Connection,
    *,
    limit: int = 5000,
    min_confirmed: int = 30,
    min_matched: int = 10,
    confidence_level: float = 0.95,
    alpha: float = 0.05,
) -> dict:
    """Return uncertainty bounds over confirmed intelligence outcomes."""
    bounded_limit = max(1, min(int(limit), 50000))
    minimum_confirmed = max(1, int(min_confirmed))
    minimum_matched = max(1, int(min_matched))
    confidence = float(confidence_level)
    significance_alpha = float(alpha)
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    if not 0.0 < significance_alpha < 1.0:
        raise ValueError("alpha must be between 0 and 1")

    examples = calibration.confirmed_examples(d, bounded_limit)
    overall = _accuracy_summary(examples, confidence)

    by_version: dict[str, list[dict]] = defaultdict(list)
    for row in examples:
        by_version[str(row.get("rule_version") or "unknown")].append(row)

    versions = {
        version: {
            **_accuracy_summary(rows, confidence),
            "sample_status": (
                "MEASURED"
                if len(rows) >= minimum_confirmed
                else "LOW_SAMPLE"
            ),
        }
        for version, rows in sorted(by_version.items())
    }

    matched_source = strategy.rule_version_report(
        d,
        limit=bounded_limit,
        min_samples=minimum_matched,
    )
    matched = []
    for row in matched_source.get("matched_comparisons", []):
        a_only = int(row.get("version_a_only_correct") or 0)
        b_only = int(row.get("version_b_only_correct") or 0)
        discordant = a_only + b_only
        p_value = exact_mcnemar_p(a_only, b_only)
        total_matched = int(row.get("matched_prospects") or 0)

        if b_only > a_only:
            direction = "VERSION_B_HIGHER_ON_MATCHED"
        elif a_only > b_only:
            direction = "VERSION_A_HIGHER_ON_MATCHED"
        else:
            direction = "TIE_ON_DISCORDANT_PAIRS"

        matched.append({
            "version_a": row["version_a"],
            "version_b": row["version_b"],
            "matched_prospects": total_matched,
            "both_correct": int(row.get("both_correct") or 0),
            "both_wrong": int(row.get("both_wrong") or 0),
            "version_a_only_correct": a_only,
            "version_b_only_correct": b_only,
            "discordant_pairs": discordant,
            "exact_mcnemar_p": p_value,
            "alpha": significance_alpha,
            "direction": direction,
            "sample_status": (
                "MEASURED"
                if total_matched >= minimum_matched
                else "LOW_SAMPLE"
            ),
            "statistically_distinguishable_at_alpha": bool(
                total_matched >= minimum_matched
                and p_value <= significance_alpha
            ),
            "causal_claim_allowed": False,
            "promotion_authorized": False,
        })

    status = (
        "MEASURED"
        if len(examples) >= minimum_confirmed
        else "INSUFFICIENT_HISTORY"
    )
    return {
        "status": status,
        "confirmed_examples": len(examples),
        "minimum_confirmed": minimum_confirmed,
        "minimum_matched": minimum_matched,
        "confidence_level": confidence,
        "alpha": significance_alpha,
        "overall": overall,
        "rule_versions": versions,
        "matched_rule_versions": matched,
        "method": (
            "Wilson intervals quantify binomial sampling uncertainty. Exact "
            "McNemar tests use only discordant outcomes for the same prospect "
            "observed under both rule versions. Historical matched evidence is "
            "not randomized and statistical distinction is not causal proof."
        ),
        "read_only": True,
        "causal_claim_allowed": False,
        "automatic_rule_change": False,
        "promotion_authorized": False,
        "merge_authority": False,
        "deployment_authorized": False,
        "paid_calls": 0,
        "external_sends": 0,
        "rule_version": RULE_VERSION,
    }
