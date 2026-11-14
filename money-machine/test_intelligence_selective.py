"""Tests for read-only v45 selective-confidence analysis."""
import sqlite3

import mm_intelligence_ledger as ledger
import mm_intelligence_selective as selective


def fresh_db():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    return d


def add_decision(
    d,
    prospect_id,
    state,
    confidence,
    rule_version="v45.2",
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
            source="searxng-local:q1",
        ),
    )


def add_outcome(d, prospect_id, state, observed, rule_version="v45.2"):
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
            later_outcome=observed,
        ),
    )


def test_empty_database_is_insufficient_and_read_only():
    d = fresh_db()
    before = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )

    result = selective.selective_report(
        d,
        thresholds=[0.0, 0.8],
        min_confirmed=2,
    )

    after = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )
    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert result["confirmed_examples"] == 0
    assert result["overall_accuracy"] is None
    assert result["highest_coverage_candidate"] is None
    assert result["advisory_only"] is True
    assert result["automatic_threshold_change"] is False
    assert result["automatic_abstention_change"] is False
    assert result["promotion_authorized"] is False
    assert after == before


def test_low_confidence_errors_can_be_deferred_to_reduce_risk():
    d = fresh_db()
    # High-confidence correct decisions.
    for prospect_id, confidence in ((1, 0.95), (2, 0.90)):
        add_decision(d, prospect_id, "QUALIFIED", confidence)
        add_outcome(d, prospect_id, "QUALIFIED", "WON")
    # Lower-confidence confirmed errors.
    add_decision(d, 3, "REJECTED", 0.60)
    add_outcome(d, 3, "REJECTED", "WON")
    add_decision(d, 4, "QUALIFIED", 0.55)
    ledger.record_correction(
        d,
        4,
        "Verified non-prospect",
        "REJECTED",
        0.99,
    )

    result = selective.selective_report(
        d,
        thresholds=[0.0, 0.6, 0.7, 0.8, 0.9],
        min_confirmed=4,
        max_risk=0.10,
        min_coverage=0.50,
    )
    points = {point["threshold"]: point for point in result["points"]}

    assert result["status"] == "TARGET_OBSERVED"
    assert result["overall_accuracy"] == 0.5
    assert result["overall_risk"] == 0.5
    assert points[0.0]["coverage"] == 1.0
    assert points[0.0]["risk"] == 0.5
    assert points[0.7]["coverage"] == 0.5
    assert points[0.7]["risk"] == 0.0
    assert points[0.7]["deferred"] == 2
    assert result["highest_coverage_candidate"] == {
        "threshold": 0.7,
        "coverage": 0.5,
        "risk": 0.0,
    }
    assert result["eligible_thresholds"] == [0.7, 0.8, 0.9]


def test_false_positive_and_false_negative_errors_are_counted():
    d = fresh_db()
    add_decision(d, 10, "QUALIFIED", 0.9)
    ledger.record_correction(
        d,
        10,
        "Wrong business",
        "REJECTED",
        0.99,
    )
    add_decision(d, 11, "REJECTED", 0.9)
    add_outcome(d, 11, "REJECTED", "WON")

    result = selective.selective_report(
        d,
        thresholds=[0.8],
        min_confirmed=2,
        max_risk=1.0,
        min_coverage=1.0,
    )
    point = result["points"][0]

    assert point["selected"] == 2
    assert point["errors"] == 2
    assert point["false_positives"] == 1
    assert point["false_negatives"] == 1
    assert point["risk"] == 1.0


def test_ambiguous_negative_outcomes_are_not_counted_as_confirmed():
    d = fresh_db()
    add_decision(d, 20, "QUALIFIED", 0.9)
    add_outcome(d, 20, "QUALIFIED", "LOST")
    add_decision(d, 21, "QUALIFIED", 0.9)
    add_outcome(d, 21, "QUALIFIED", "NO_RESPONSE")

    result = selective.selective_report(
        d,
        thresholds=[0.0, 0.8],
        min_confirmed=1,
    )

    assert result["confirmed_examples"] == 0
    assert result["status"] == "INSUFFICIENT_HISTORY"


def test_no_threshold_meets_target_when_high_confidence_errors_remain():
    d = fresh_db()
    for prospect_id in range(30, 34):
        add_decision(d, prospect_id, "REJECTED", 0.95)
        add_outcome(d, prospect_id, "REJECTED", "WON")

    result = selective.selective_report(
        d,
        thresholds=[0.0, 0.8, 0.9, 0.95],
        min_confirmed=4,
        max_risk=0.10,
        min_coverage=0.25,
    )

    assert result["status"] == "NO_THRESHOLD_MEETS_TARGET"
    assert result["eligible_thresholds"] == []
    assert result["highest_coverage_candidate"] is None
    assert all(
        point["risk"] == 1.0
        for point in result["points"]
        if point["selected"]
    )


def test_risk_coverage_area_is_deterministic():
    d = fresh_db()
    add_decision(d, 40, "QUALIFIED", 0.95)
    add_outcome(d, 40, "QUALIFIED", "WON")
    add_decision(d, 41, "QUALIFIED", 0.85)
    add_outcome(d, 41, "QUALIFIED", "WON")
    add_decision(d, 42, "REJECTED", 0.65)
    add_outcome(d, 42, "REJECTED", "WON")
    add_decision(d, 43, "QUALIFIED", 0.55)
    ledger.record_correction(d, 43, "Wrong prospect", "REJECTED", 0.99)

    first = selective.selective_report(
        d,
        thresholds=[0.0, 0.6, 0.7, 0.8, 0.9],
        min_confirmed=4,
    )
    second = selective.selective_report(
        d,
        thresholds=[0.0, 0.6, 0.7, 0.8, 0.9],
        min_confirmed=4,
    )

    assert first["area_under_risk_coverage"] == second["area_under_risk_coverage"]
    assert first["area_under_risk_coverage"] is not None
    assert 0.0 <= first["area_under_risk_coverage"] <= 1.0


def test_invalid_threshold_set_fails_closed():
    d = fresh_db()

    try:
        selective.selective_report(
            d,
            thresholds=[-1.0, 2.0],
        )
    except ValueError as exc:
        assert "At least one threshold between 0 and 1" in str(exc)
    else:
        raise AssertionError("Expected invalid threshold set to fail")


def test_low_sample_status_overrides_apparent_target():
    d = fresh_db()
    add_decision(d, 50, "QUALIFIED", 0.95)
    add_outcome(d, 50, "QUALIFIED", "WON")

    result = selective.selective_report(
        d,
        thresholds=[0.9],
        min_confirmed=10,
        max_risk=0.0,
        min_coverage=1.0,
    )

    assert result["points"][0]["meets_target"] is True
    assert result["status"] == "INSUFFICIENT_HISTORY"


def test_selective_analysis_never_authorizes_threshold_changes():
    d = fresh_db()
    for prospect_id in range(60, 64):
        add_decision(d, prospect_id, "QUALIFIED", 0.95)
        add_outcome(d, prospect_id, "QUALIFIED", "WON")

    result = selective.selective_report(
        d,
        thresholds=[0.8, 0.9],
        min_confirmed=4,
        max_risk=0.0,
        min_coverage=0.5,
    )

    assert result["status"] == "TARGET_OBSERVED"
    assert result["advisory_only"] is True
    assert result["automatic_threshold_change"] is False
    assert result["automatic_abstention_change"] is False
    assert result["promotion_authorized"] is False
    assert result["causal_claim_allowed"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
