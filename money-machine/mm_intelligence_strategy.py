"""Read-only strategy analysis for v45 intelligence.

Provides:
- matched-prospect comparison across decision rule versions;
- outcome-backed source/query cohort diagnostics.

Historical observations are not randomized experiments. This module therefore
reports descriptive evidence only and never authorizes rule promotion, source
reallocation, pipeline changes, model calls, or external sends.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from itertools import combinations

import mm_intelligence_calibration as calibration

RULE_VERSION = "v45-strategy-analysis-v1"

_EXCLUDED_DISPOSITIONS = frozenset({"HUMAN_CORRECTED", "OUTCOME_OBSERVED"})


def _table_exists(d: sqlite3.Connection, name: str) -> bool:
    return bool(
        d.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
    )


def _decision_polarity(decision: str | None) -> int | None:
    value = str(decision or "")
    if value in calibration.POSITIVE_DECISIONS:
        return 1
    if value in calibration.NEGATIVE_DECISIONS:
        return 0
    return None


def _expected_polarity(example: dict) -> int:
    original = int(example["decision_polarity"])
    correct = int(example["observed_correct"])
    return original if correct else 1 - original


def _metrics(rows: list[dict], minimum: int) -> dict:
    count = len(rows)
    if not count:
        return {
            "confirmed_examples": 0,
            "correct": 0,
            "errors": 0,
            "observed_accuracy": None,
            "avg_confidence": None,
            "brier_score": None,
            "expected_positive_labels": 0,
            "sample_status": "NO_CONFIRMED_EXAMPLES",
            "minimum_sample": minimum,
        }

    correct = sum(int(row["observed_correct"]) for row in rows)
    confidence = sum(float(row["confidence"]) for row in rows) / count
    brier = sum(
        (float(row["confidence"]) - int(row["observed_correct"])) ** 2
        for row in rows
    ) / count
    positive_labels = sum(_expected_polarity(row) for row in rows)
    return {
        "confirmed_examples": count,
        "correct": correct,
        "errors": count - correct,
        "observed_accuracy": round(correct / count, 4),
        "avg_confidence": round(confidence, 4),
        "brier_score": round(brier, 6),
        "expected_positive_labels": positive_labels,
        "sample_status": (
            "MEASURED" if count >= minimum else "LOW_SAMPLE"
        ),
        "minimum_sample": minimum,
    }


def rule_version_report(
    d: sqlite3.Connection,
    limit: int = 5000,
    min_samples: int = 10,
) -> dict:
    """Compare rule versions descriptively, including matched prospects."""
    bounded_limit = max(1, min(int(limit), 50000))
    minimum = max(1, int(min_samples))
    examples = calibration.confirmed_examples(d, bounded_limit)

    by_version: dict[str, list[dict]] = defaultdict(list)
    by_prospect: dict[int, dict[str, dict]] = defaultdict(dict)
    for row in examples:
        version = str(row.get("rule_version") or "unknown")
        by_version[version].append(row)
        prospect_id = int(row["prospect_id"])
        existing = by_prospect[prospect_id].get(version)
        if existing is None or int(row["ledger_id"]) > int(existing["ledger_id"]):
            by_prospect[prospect_id][version] = row

    version_metrics = {
        version: _metrics(rows, minimum)
        for version, rows in sorted(by_version.items())
    }

    pair_stats: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {
            "matched_prospects": 0,
            "both_correct": 0,
            "version_a_only_correct": 0,
            "version_b_only_correct": 0,
            "both_wrong": 0,
        }
    )
    for versions in by_prospect.values():
        if len(versions) < 2:
            continue
        for version_a, version_b in combinations(sorted(versions), 2):
            row_a = versions[version_a]
            row_b = versions[version_b]
            correct_a = bool(row_a["observed_correct"])
            correct_b = bool(row_b["observed_correct"])
            stats = pair_stats[(version_a, version_b)]
            stats["matched_prospects"] += 1
            if correct_a and correct_b:
                stats["both_correct"] += 1
            elif correct_a:
                stats["version_a_only_correct"] += 1
            elif correct_b:
                stats["version_b_only_correct"] += 1
            else:
                stats["both_wrong"] += 1

    matched = []
    for (version_a, version_b), stats in sorted(pair_stats.items()):
        total = stats["matched_prospects"]
        accuracy_a = (
            stats["both_correct"] + stats["version_a_only_correct"]
        ) / total
        accuracy_b = (
            stats["both_correct"] + stats["version_b_only_correct"]
        ) / total
        matched.append({
            "version_a": version_a,
            "version_b": version_b,
            **stats,
            "version_a_accuracy_on_matched": round(accuracy_a, 4),
            "version_b_accuracy_on_matched": round(accuracy_b, 4),
            "delta_b_minus_a": round(accuracy_b - accuracy_a, 4),
            "sample_status": (
                "MEASURED" if total >= minimum else "LOW_SAMPLE"
            ),
            "minimum_sample": minimum,
            "causal_claim_allowed": False,
            "promotion_authorized": False,
        })

    return {
        "confirmed_examples": len(examples),
        "versions": version_metrics,
        "matched_comparisons": matched,
        "matched_comparison_count": len(matched),
        "method": (
            "Aggregate metrics are descriptive. Matched comparisons only compare "
            "confirmed decisions for the same prospect across rule versions; "
            "they are still historical observations, not randomized trials."
        ),
        "causal_claim_allowed": False,
        "promotion_authorized": False,
        "automatic_rule_change": False,
        "read_only": True,
        "paid_calls": 0,
        "external_sends": 0,
        "rule_version": RULE_VERSION,
    }


def _source_diagnostic(
    prospects: int,
    confirmed: int,
    error_rate: float | None,
    engaged_rate: float,
    won_rate: float,
    min_prospects: int,
    min_confirmed: int,
) -> dict:
    if prospects < min_prospects or confirmed < min_confirmed:
        signal = "INSUFFICIENT_EVIDENCE"
        reason = (
            "Need more distinct prospects and confirmed labels before "
            "drawing a source/query conclusion."
        )
    elif won_rate > 0 or engaged_rate >= 0.20:
        signal = "OUTCOME_SIGNAL_PRESENT"
        reason = "Observed downstream engagement or won outcomes are present."
    elif error_rate is not None and error_rate >= 0.30:
        signal = "REVIEW_CONFIRMED_ERRORS"
        reason = "Confirmed decision errors are elevated in this cohort."
    else:
        signal = "OBSERVE"
        reason = "No strong outcome or error signal justifies a routing change."
    return {
        "signal": signal,
        "reason": reason,
        "minimum_prospects": min_prospects,
        "minimum_confirmed_labels": min_confirmed,
        "automatic_action": False,
    }


def source_query_report(
    d: sqlite3.Connection,
    limit: int = 10000,
    min_prospects: int = 10,
    min_confirmed: int = 5,
) -> dict:
    """Measure source/query cohorts using confirmed labels and real outcomes."""
    bounded_limit = max(1, min(int(limit), 50000))
    minimum_prospects = max(1, int(min_prospects))
    minimum_confirmed = max(1, int(min_confirmed))

    if not _table_exists(d, "intelligence_ledger"):
        return {
            "cohorts": [],
            "cohort_count": 0,
            "ledger_rows_assessed": 0,
            "truncated": False,
            "read_only": True,
            "automatic_source_change": False,
            "causal_claim_allowed": False,
            "paid_calls": 0,
            "external_sends": 0,
            "rule_version": RULE_VERSION,
        }

    total_rows = int(
        d.execute("SELECT COUNT(*) FROM intelligence_ledger").fetchone()[0]
    )
    rows = [
        dict(row)
        for row in d.execute(
            """SELECT id,prospect_id,source,query_fingerprint,decision,
                      disposition,confidence,rule_version
               FROM intelligence_ledger
               ORDER BY id DESC LIMIT ?""",
            (bounded_limit,),
        ).fetchall()
    ]
    ledger_by_id = {int(row["id"]): row for row in rows}

    grouped = defaultdict(lambda: {
        "eligible_decisions": 0,
        "prospect_ids": set(),
        "rule_versions": set(),
        "confirmed": [],
    })

    for row in rows:
        if row.get("disposition") in _EXCLUDED_DISPOSITIONS:
            continue
        if _decision_polarity(row.get("decision")) is None:
            continue
        key = (
            str(row.get("source") or "unknown"),
            str(row.get("query_fingerprint") or ""),
        )
        stats = grouped[key]
        stats["eligible_decisions"] += 1
        stats["prospect_ids"].add(int(row["prospect_id"]))
        stats["rule_versions"].add(str(row.get("rule_version") or "unknown"))

    confirmed = calibration.confirmed_examples(d, bounded_limit)
    for example in confirmed:
        ledger_row = ledger_by_id.get(int(example["ledger_id"]))
        if ledger_row is None:
            continue
        key = (
            str(ledger_row.get("source") or "unknown"),
            str(ledger_row.get("query_fingerprint") or ""),
        )
        grouped[key]["confirmed"].append(example)

    engaged_ids: set[int] = set()
    won_ids: set[int] = set()
    if _table_exists(d, "prospect_outcomes"):
        outcome_rows = d.execute(
            """SELECT business_id,outcome FROM prospect_outcomes
               WHERE outcome IN (
                 'REPLIED','CALL_OR_DISCOVERY','PROPOSAL_SENT','WON'
               )"""
        ).fetchall()
        for row in outcome_rows:
            business_id = int(row["business_id"])
            engaged_ids.add(business_id)
            if row["outcome"] == "WON":
                won_ids.add(business_id)

    cohorts = []
    for (source, query_fingerprint), stats in grouped.items():
        prospect_ids = set(stats["prospect_ids"])
        prospects = len(prospect_ids)
        confirmed_rows = list(stats["confirmed"])
        confirmed_count = len(confirmed_rows)
        confirmed_correct = sum(
            int(row["observed_correct"]) for row in confirmed_rows
        )
        confirmed_errors = confirmed_count - confirmed_correct
        error_rate = (
            confirmed_errors / confirmed_count
            if confirmed_count
            else None
        )
        confirmed_positive = sum(
            _expected_polarity(row) for row in confirmed_rows
        )
        engaged = len(prospect_ids & engaged_ids)
        won = len(prospect_ids & won_ids)
        engaged_rate = engaged / prospects if prospects else 0.0
        won_rate = won / prospects if prospects else 0.0
        label_coverage = (
            confirmed_count / stats["eligible_decisions"]
            if stats["eligible_decisions"]
            else 0.0
        )

        cohorts.append({
            "source": source,
            "query_fingerprint": query_fingerprint,
            "distinct_prospects": prospects,
            "eligible_decisions": stats["eligible_decisions"],
            "confirmed_examples": confirmed_count,
            "confirmed_correct": confirmed_correct,
            "confirmed_errors": confirmed_errors,
            "confirmed_accuracy": (
                round(confirmed_correct / confirmed_count, 4)
                if confirmed_count
                else None
            ),
            "confirmed_error_rate": (
                round(error_rate, 4)
                if error_rate is not None
                else None
            ),
            "confirmed_positive_labels": confirmed_positive,
            "label_coverage": round(label_coverage, 4),
            "engaged_businesses": engaged,
            "won_businesses": won,
            "engagement_rate": round(engaged_rate, 4),
            "won_rate": round(won_rate, 4),
            "rule_versions": sorted(stats["rule_versions"]),
            "diagnostic": _source_diagnostic(
                prospects,
                confirmed_count,
                error_rate,
                engaged_rate,
                won_rate,
                minimum_prospects,
                minimum_confirmed,
            ),
        })

    cohorts.sort(
        key=lambda item: (
            -item["distinct_prospects"],
            -item["eligible_decisions"],
            item["source"],
            item["query_fingerprint"],
        )
    )
    return {
        "cohorts": cohorts,
        "cohort_count": len(cohorts),
        "ledger_rows_assessed": len(rows),
        "truncated": total_rows > len(rows),
        "minimum_prospects": minimum_prospects,
        "minimum_confirmed_labels": minimum_confirmed,
        "method": (
            "Cohorts use recorded source/query fingerprints, confirmed decision "
            "labels, and observed downstream outcomes. Results are observational "
            "and do not establish causal source superiority."
        ),
        "read_only": True,
        "automatic_source_change": False,
        "causal_claim_allowed": False,
        "paid_calls": 0,
        "external_sends": 0,
        "rule_version": RULE_VERSION,
    }


def strategy_report(
    d: sqlite3.Connection,
    limit: int = 5000,
    min_rule_samples: int = 10,
    min_source_prospects: int = 10,
    min_confirmed: int = 5,
) -> dict:
    """Return the combined rule-version and source/query strategy report."""
    return {
        "rule_versions": rule_version_report(
            d,
            limit=limit,
            min_samples=min_rule_samples,
        ),
        "source_queries": source_query_report(
            d,
            limit=limit,
            min_prospects=min_source_prospects,
            min_confirmed=min_confirmed,
        ),
        "read_only": True,
        "automatic_changes": False,
        "promotion_authorized": False,
        "paid_calls": 0,
        "external_sends": 0,
        "rule_version": RULE_VERSION,
    }
