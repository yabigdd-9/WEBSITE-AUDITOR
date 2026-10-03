"""Tests for read-only v45 decision consistency analysis."""
import sqlite3

import mm_intelligence_consistency as consistency
import mm_intelligence_ledger as ledger


def fresh_db():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    return d


def add(
    d,
    prospect_id,
    decision,
    confidence=0.9,
    rule_version="v45.2",
    stage="qualification",
    disposition="",
):
    return ledger.append_decision(
        d,
        ledger.IntelligenceDecision(
            prospect_id=prospect_id,
            business_name=f"Business {prospect_id}",
            domain=f"business{prospect_id}.co.nz",
            decision=decision,
            disposition=disposition,
            confidence=confidence,
            rule_version=rule_version,
            stage=stage,
        ),
    )


def test_empty_database_is_read_only_zero_report():
    d = fresh_db()
    before = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )

    result = consistency.consistency_report(d)

    after = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )
    assert result["group_count"] == 0
    assert result["unstable_group_count"] == 0
    assert result["total_flips"] == 0
    assert result["read_only"] is True
    assert result["automatic_rule_change"] is False
    assert result["promotion_authorized"] is False
    assert after == before


def test_repeated_same_polarity_decisions_are_stable():
    d = fresh_db()
    add(d, 1, "QUALIFIED", 0.9)
    add(d, 1, "APPROVED", 0.85)

    result = consistency.consistency_report(d)

    assert result["group_count"] == 1
    group = result["groups"][0]
    assert group["decision_count"] == 2
    assert group["flip_count"] == 0
    assert group["signal"] == "STABLE"


def test_positive_to_negative_flip_is_detected():
    d = fresh_db()
    first = add(d, 2, "QUALIFIED", 0.9)
    second = add(d, 2, "REJECTED", 0.7)

    result = consistency.consistency_report(d)

    assert result["unstable_group_count"] == 1
    assert result["total_flips"] == 1
    flip = result["groups"][0]["flips"][0]
    assert flip["from_ledger_id"] == first
    assert flip["to_ledger_id"] == second
    assert flip["from_decision"] == "QUALIFIED"
    assert flip["to_decision"] == "REJECTED"
    assert flip["high_confidence"] is False


def test_high_confidence_flip_is_counted_separately():
    d = fresh_db()
    add(d, 3, "REJECTED", 0.95)
    add(d, 3, "QUALIFIED", 0.9)

    result = consistency.consistency_report(d, min_confidence=0.8)

    assert result["total_flips"] == 1
    assert result["high_confidence_flips"] == 1
    assert result["groups"][0]["high_confidence_flip_count"] == 1
    assert result["groups"][0]["signal"] == "REVIEW_OSCILLATION"


def test_different_stages_are_not_compared():
    d = fresh_db()
    add(d, 4, "QUALIFIED", 0.9, stage="qualification")
    add(d, 4, "REJECTED", 0.9, stage="contact")

    result = consistency.consistency_report(d)

    assert result["group_count"] == 0
    assert result["total_flips"] == 0


def test_different_rule_versions_are_not_compared():
    d = fresh_db()
    add(d, 5, "QUALIFIED", 0.9, rule_version="v45.1")
    add(d, 5, "REJECTED", 0.9, rule_version="v45.2")

    result = consistency.consistency_report(d)

    assert result["group_count"] == 0
    assert result["total_flips"] == 0


def test_corrections_and_outcome_observations_do_not_create_flips():
    d = fresh_db()
    add(d, 6, "QUALIFIED", 0.9)
    add(
        d,
        6,
        "REJECTED",
        0.99,
        disposition="HUMAN_CORRECTED",
    )
    add(
        d,
        6,
        "REJECTED",
        0.5,
        disposition="OUTCOME_OBSERVED",
    )

    result = consistency.consistency_report(d)

    assert result["group_count"] == 0
    assert result["total_flips"] == 0


def test_multiple_flips_are_ordered_and_counted():
    d = fresh_db()
    add(d, 7, "QUALIFIED", 0.9)
    add(d, 7, "REJECTED", 0.9)
    add(d, 7, "QUALIFIED", 0.9)

    result = consistency.consistency_report(d)

    group = result["groups"][0]
    assert group["flip_count"] == 2
    assert group["high_confidence_flip_count"] == 2
    assert result["total_flips"] == 2
    assert result["high_confidence_flips"] == 2


def test_limit_is_bounded_to_recent_ledger_rows():
    d = fresh_db()
    add(d, 8, "QUALIFIED", 0.9)
    add(d, 8, "REJECTED", 0.9)
    add(d, 9, "QUALIFIED", 0.9)
    add(d, 9, "REJECTED", 0.9)

    result = consistency.consistency_report(d, limit=2)

    assert result["ledger_rows_assessed"] == 2
    assert result["group_count"] == 1
    assert result["groups"][0]["prospect_id"] == 9


def test_consistency_signal_never_authorizes_changes():
    d = fresh_db()
    add(d, 10, "QUALIFIED", 0.99)
    add(d, 10, "REJECTED", 0.99)

    result = consistency.consistency_report(d)

    assert result["total_flips"] == 1
    assert result["causal_claim_allowed"] is False
    assert result["automatic_rule_change"] is False
    assert result["promotion_authorized"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
