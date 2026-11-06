"""Tests for read-only v45 intelligence strategy analysis."""
import sqlite3

import mm_intelligence_ledger as ledger
import mm_intelligence_strategy as strategy


def fresh_db():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    return d


def add_decision(
    d,
    prospect_id,
    state,
    confidence=0.8,
    rule_version="v45.1",
    source="searxng-local:q1",
    query_fingerprint="q1",
):
    return ledger.append_decision(
        d,
        ledger.IntelligenceDecision(
            prospect_id=prospect_id,
            business_name=f"Business {prospect_id}",
            domain=f"business{prospect_id}.co.nz",
            decision=state,
            confidence=confidence,
            rule_version=rule_version,
            stage="qualification",
            source=source,
            query_fingerprint=query_fingerprint,
        ),
    )


def add_outcome_observation(
    d,
    prospect_id,
    state,
    observed,
    rule_version="v45.1",
    source="searxng-local:q1",
    query_fingerprint="q1",
):
    return ledger.append_decision(
        d,
        ledger.IntelligenceDecision(
            prospect_id=prospect_id,
            business_name=f"Business {prospect_id}",
            domain=f"business{prospect_id}.co.nz",
            decision=state,
            disposition="OUTCOME_OBSERVED",
            confidence=0.5,
            rule_version=rule_version,
            stage="outcome",
            source=source,
            query_fingerprint=query_fingerprint,
            later_outcome=observed,
        ),
    )


def add_real_outcome_table(d):
    d.execute(
        """CREATE TABLE IF NOT EXISTS prospect_outcomes(
        id INTEGER PRIMARY KEY,
        business_id INTEGER NOT NULL,
        outcome TEXT NOT NULL)"""
    )


def test_empty_database_returns_read_only_zero_reports_without_mutation():
    d = fresh_db()
    before = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )

    result = strategy.strategy_report(d)

    after = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )
    assert result["rule_versions"]["confirmed_examples"] == 0
    assert result["source_queries"]["cohort_count"] == 0
    assert result["read_only"] is True
    assert result["automatic_changes"] is False
    assert result["promotion_authorized"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
    assert after == before


def test_rule_version_report_has_descriptive_accuracy_and_brier():
    d = fresh_db()
    add_decision(d, 1, "QUALIFIED", 0.8, rule_version="v45.1")
    add_outcome_observation(d, 1, "QUALIFIED", "WON", rule_version="v45.1")
    add_decision(d, 2, "REJECTED", 0.9, rule_version="v45.1")
    add_outcome_observation(d, 2, "REJECTED", "WON", rule_version="v45.1")
    add_decision(d, 3, "QUALIFIED", 0.7, rule_version="v45.2")
    add_outcome_observation(d, 3, "QUALIFIED", "REPLIED", rule_version="v45.2")

    result = strategy.rule_version_report(d, min_samples=1)

    v1 = result["versions"]["v45.1"]
    v2 = result["versions"]["v45.2"]
    assert v1["confirmed_examples"] == 2
    assert v1["observed_accuracy"] == 0.5
    assert v1["errors"] == 1
    assert v2["confirmed_examples"] == 1
    assert v2["observed_accuracy"] == 1.0
    assert result["causal_claim_allowed"] is False
    assert result["promotion_authorized"] is False
    assert result["automatic_rule_change"] is False


def test_matched_rule_version_comparison_uses_same_prospect_only():
    d = fresh_db()
    add_decision(d, 10, "REJECTED", 0.9, rule_version="v45.1")
    ledger.record_correction(
        d,
        10,
        "v45.1 missed a qualified prospect",
        "QUALIFIED",
        0.99,
        rule_version="v45.1",
    )
    add_decision(d, 10, "QUALIFIED", 0.8, rule_version="v45.2")
    add_outcome_observation(
        d,
        10,
        "QUALIFIED",
        "WON",
        rule_version="v45.2",
    )
    # Unmatched v45.2 case must not inflate the matched comparison.
    add_decision(d, 11, "QUALIFIED", 0.8, rule_version="v45.2")
    add_outcome_observation(
        d,
        11,
        "QUALIFIED",
        "REPLIED",
        rule_version="v45.2",
    )

    result = strategy.rule_version_report(d, min_samples=1)

    assert result["matched_comparison_count"] == 1
    matched = result["matched_comparisons"][0]
    assert matched["version_a"] == "v45.1"
    assert matched["version_b"] == "v45.2"
    assert matched["matched_prospects"] == 1
    assert matched["version_a_only_correct"] == 0
    assert matched["version_b_only_correct"] == 1
    assert matched["version_a_accuracy_on_matched"] == 0.0
    assert matched["version_b_accuracy_on_matched"] == 1.0
    assert matched["delta_b_minus_a"] == 1.0
    assert matched["causal_claim_allowed"] is False
    assert matched["promotion_authorized"] is False


def test_source_query_cohorts_use_confirmed_labels_and_real_outcomes():
    d = fresh_db()
    add_real_outcome_table(d)

    add_decision(
        d,
        20,
        "QUALIFIED",
        source="searxng-local:plumbers",
        query_fingerprint="plumbers-chch",
    )
    add_outcome_observation(
        d,
        20,
        "QUALIFIED",
        "WON",
        source="searxng-local:plumbers",
        query_fingerprint="plumbers-chch",
    )
    d.execute(
        "INSERT INTO prospect_outcomes(id,business_id,outcome) VALUES(1,20,'WON')"
    )

    add_decision(
        d,
        21,
        "QUALIFIED",
        source="searxng-local:plumbers",
        query_fingerprint="plumbers-chch",
    )
    add_outcome_observation(
        d,
        21,
        "QUALIFIED",
        "REPLIED",
        source="searxng-local:plumbers",
        query_fingerprint="plumbers-chch",
    )
    d.execute(
        "INSERT INTO prospect_outcomes(id,business_id,outcome) VALUES(2,21,'REPLIED')"
    )

    add_decision(
        d,
        22,
        "REJECTED",
        source="searxng-local:directory-heavy",
        query_fingerprint="directory-heavy",
    )
    add_outcome_observation(
        d,
        22,
        "REJECTED",
        "WON",
        source="searxng-local:directory-heavy",
        query_fingerprint="directory-heavy",
    )

    result = strategy.source_query_report(
        d,
        min_prospects=1,
        min_confirmed=1,
    )
    cohorts = {
        (row["source"], row["query_fingerprint"]): row
        for row in result["cohorts"]
    }

    good = cohorts[("searxng-local:plumbers", "plumbers-chch")]
    bad = cohorts[("searxng-local:directory-heavy", "directory-heavy")]

    assert good["distinct_prospects"] == 2
    assert good["confirmed_examples"] == 2
    assert good["confirmed_accuracy"] == 1.0
    assert good["engagement_rate"] == 1.0
    assert good["won_rate"] == 0.5
    assert good["diagnostic"]["signal"] == "OUTCOME_SIGNAL_PRESENT"

    assert bad["confirmed_examples"] == 1
    assert bad["confirmed_accuracy"] == 0.0
    assert bad["confirmed_error_rate"] == 1.0
    assert bad["confirmed_positive_labels"] == 1
    assert bad["diagnostic"]["signal"] == "REVIEW_CONFIRMED_ERRORS"

    assert result["automatic_source_change"] is False
    assert result["causal_claim_allowed"] is False


def test_ambiguous_outcome_does_not_create_confirmed_source_label():
    d = fresh_db()
    add_decision(
        d,
        30,
        "QUALIFIED",
        source="import",
        query_fingerprint="manual",
    )
    add_outcome_observation(
        d,
        30,
        "QUALIFIED",
        "LOST",
        source="import",
        query_fingerprint="manual",
    )

    result = strategy.source_query_report(
        d,
        min_prospects=1,
        min_confirmed=1,
    )
    cohort = result["cohorts"][0]

    assert cohort["eligible_decisions"] == 1
    assert cohort["confirmed_examples"] == 0
    assert cohort["confirmed_accuracy"] is None
    assert cohort["diagnostic"]["signal"] == "INSUFFICIENT_EVIDENCE"


def test_source_query_report_marks_bounded_history_as_truncated():
    d = fresh_db()
    for prospect_id in range(1, 6):
        add_decision(
            d,
            prospect_id,
            "QUALIFIED",
            source="import",
            query_fingerprint="batch",
        )

    result = strategy.source_query_report(d, limit=2)

    assert result["ledger_rows_assessed"] == 2
    assert result["truncated"] is True


def test_combined_strategy_report_never_authorizes_changes():
    d = fresh_db()
    add_decision(d, 40, "QUALIFIED", 0.8)
    add_outcome_observation(d, 40, "QUALIFIED", "WON")

    result = strategy.strategy_report(
        d,
        min_rule_samples=1,
        min_source_prospects=1,
        min_confirmed=1,
    )

    assert result["read_only"] is True
    assert result["automatic_changes"] is False
    assert result["promotion_authorized"] is False
    assert result["rule_versions"]["promotion_authorized"] is False
    assert result["source_queries"]["automatic_source_change"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
