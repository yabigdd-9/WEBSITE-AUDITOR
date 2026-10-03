"""Tests for read-only v45 intelligence drift detection."""
import sqlite3

import mm_intelligence_drift as drift
import mm_intelligence_ledger as ledger


def fresh_db():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    return d


def add_decision(
    d,
    prospect_id,
    state,
    confidence,
    rule_version="v45.1",
    source="searxng-local:q1",
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
        ),
    )


def add_outcome(d, prospect_id, state, observed, rule_version="v45.1", source="searxng-local:q1"):
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
            later_outcome=observed,
        ),
    )


def add_correct_positive(d, prospect_id, confidence=0.9, rule_version="v45.1", source="searxng-local:q1"):
    add_decision(d, prospect_id, "QUALIFIED", confidence, rule_version, source)
    add_outcome(d, prospect_id, "QUALIFIED", "WON", rule_version, source)


def add_wrong_negative(d, prospect_id, confidence=0.9, rule_version="v45.1", source="searxng-local:q1"):
    add_decision(d, prospect_id, "REJECTED", confidence, rule_version, source)
    add_outcome(d, prospect_id, "REJECTED", "WON", rule_version, source)


def test_empty_database_is_insufficient_and_read_only():
    d = fresh_db()
    before = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )

    result = drift.drift_report(d, window=4, min_samples=2)

    after = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )
    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert result["recent"]["metrics"]["count"] == 0
    assert result["prior"]["metrics"]["count"] == 0
    assert result["flags"] == []
    assert result["read_only"] is True
    assert result["automatic_rule_change"] is False
    assert result["automatic_source_change"] is False
    assert result["promotion_authorized"] is False
    assert after == before


def test_insufficient_history_requires_both_windows():
    d = fresh_db()
    for prospect_id in range(1, 5):
        add_correct_positive(d, prospect_id)

    result = drift.drift_report(d, window=4, min_samples=2)

    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert result["recent"]["metrics"]["count"] == 4
    assert result["prior"]["metrics"]["count"] == 0
    assert all(value is None for value in result["deltas_recent_minus_prior"].values())


def test_stable_adjacent_windows_stay_stable():
    d = fresh_db()
    for prospect_id in range(1, 9):
        add_correct_positive(d, prospect_id, confidence=0.8)

    result = drift.drift_report(
        d,
        window=4,
        min_samples=4,
        accuracy_drop_threshold=0.15,
        brier_increase_threshold=0.10,
        confidence_shift_threshold=0.15,
        label_shift_threshold=0.25,
    )

    assert result["status"] == "STABLE"
    assert result["flags"] == []
    assert result["recent"]["metrics"]["accuracy"] == 1.0
    assert result["prior"]["metrics"]["accuracy"] == 1.0
    assert result["deltas_recent_minus_prior"]["accuracy"] == 0.0
    assert result["deltas_recent_minus_prior"]["brier_score"] == 0.0


def test_recent_accuracy_drop_is_flagged():
    d = fresh_db()
    # Older confirmed window: all correct.
    for prospect_id in range(1, 5):
        add_correct_positive(d, prospect_id, confidence=0.9)
    # Newer confirmed window: all wrong.
    for prospect_id in range(5, 9):
        add_wrong_negative(d, prospect_id, confidence=0.9)

    result = drift.drift_report(
        d,
        window=4,
        min_samples=4,
        accuracy_drop_threshold=0.15,
    )

    assert result["status"] == "REVIEW_DRIFT"
    assert "ACCURACY_DROP" in result["flags"]
    assert result["recent"]["metrics"]["accuracy"] == 0.0
    assert result["prior"]["metrics"]["accuracy"] == 1.0
    assert result["deltas_recent_minus_prior"]["accuracy"] == -1.0


def test_brier_and_confidence_deterioration_are_flagged():
    d = fresh_db()
    # Older: correct and well-calibrated.
    for prospect_id in range(1, 5):
        add_correct_positive(d, prospect_id, confidence=0.9)
    # Newer: still correct, but much less confident.
    for prospect_id in range(5, 9):
        add_correct_positive(d, prospect_id, confidence=0.55)

    result = drift.drift_report(
        d,
        window=4,
        min_samples=4,
        brier_increase_threshold=0.10,
        confidence_shift_threshold=0.15,
    )

    assert result["status"] == "REVIEW_DRIFT"
    assert "BRIER_WORSENING" in result["flags"]
    assert "CONFIDENCE_SHIFT" in result["flags"]
    assert result["deltas_recent_minus_prior"]["brier_score"] > 0.10
    assert result["deltas_recent_minus_prior"]["avg_confidence"] == -0.35


def test_label_mix_shift_is_flagged_without_claiming_rule_failure():
    d = fresh_db()
    # Older window: confirmed positive labels.
    for prospect_id in range(1, 5):
        add_correct_positive(d, prospect_id, confidence=0.8)

    # Newer window: correct negative decisions confirmed by human correction.
    for prospect_id in range(5, 9):
        add_decision(d, prospect_id, "QUALIFIED", 0.8)
        ledger.record_correction(
            d,
            prospect_id,
            "Verified negative prospect",
            "REJECTED",
            0.99,
        )

    result = drift.drift_report(
        d,
        window=4,
        min_samples=4,
        label_shift_threshold=0.25,
    )

    assert result["status"] == "REVIEW_DRIFT"
    assert "LABEL_MIX_SHIFT" in result["flags"]
    assert result["recent"]["metrics"]["positive_label_rate"] == 0.0
    assert result["prior"]["metrics"]["positive_label_rate"] == 1.0
    assert "changing case mix" in result["method"]


def test_window_composition_reports_rule_and_source_changes():
    d = fresh_db()
    for prospect_id in range(1, 5):
        add_correct_positive(
            d,
            prospect_id,
            confidence=0.8,
            rule_version="v45.1",
            source="source-old",
        )
    for prospect_id in range(5, 9):
        add_correct_positive(
            d,
            prospect_id,
            confidence=0.8,
            rule_version="v45.2",
            source="source-new",
        )

    result = drift.drift_report(d, window=4, min_samples=4)

    assert result["recent"]["rule_versions"] == {"v45.2": 4}
    assert result["prior"]["rule_versions"] == {"v45.1": 4}
    assert result["recent"]["sources"] == {"source-new": 4}
    assert result["prior"]["sources"] == {"source-old": 4}


def test_no_drift_signal_can_authorize_automatic_changes():
    d = fresh_db()
    for prospect_id in range(1, 5):
        add_correct_positive(d, prospect_id, confidence=0.9)
    for prospect_id in range(5, 9):
        add_wrong_negative(d, prospect_id, confidence=0.9)

    result = drift.drift_report(d, window=4, min_samples=4)

    assert result["status"] == "REVIEW_DRIFT"
    assert result["automatic_rule_change"] is False
    assert result["automatic_source_change"] is False
    assert result["promotion_authorized"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
