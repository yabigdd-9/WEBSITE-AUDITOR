"""Tests for read-only v45 intelligence confidence calibration."""
import sqlite3

import mm_intelligence_calibration as calibration
import mm_intelligence_ledger as ledger


def fresh_db():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    return d


def add_decision(
    d,
    prospect_id,
    decision,
    confidence,
    rule_version="v45.1",
    stage="qualification",
):
    return ledger.append_decision(
        d,
        ledger.IntelligenceDecision(
            prospect_id=prospect_id,
            business_name=f"Business {prospect_id}",
            domain=f"business{prospect_id}.co.nz",
            decision=decision,
            confidence=confidence,
            rule_version=rule_version,
            stage=stage,
        ),
    )


def add_outcome_observation(
    d,
    prospect_id,
    decision,
    later_outcome,
    confidence=0.5,
    rule_version="v45.1",
):
    return ledger.append_decision(
        d,
        ledger.IntelligenceDecision(
            prospect_id=prospect_id,
            business_name=f"Business {prospect_id}",
            domain=f"business{prospect_id}.co.nz",
            decision=decision,
            disposition="OUTCOME_OBSERVED",
            confidence=confidence,
            rule_version=rule_version,
            stage="outcome",
            later_outcome=later_outcome,
        ),
    )


def test_empty_database_is_clean_read_only_zero_result():
    d = fresh_db()
    before = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )
    result = calibration.calibration_report(d)
    after = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )
    assert result["status"] == "NO_CONFIRMED_EXAMPLES"
    assert result["confirmed_examples"] == 0
    assert result["eligible_decisions"] == 0
    assert result["expected_calibration_error"] is None
    assert result["brier_score"] is None
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
    assert after == before


def test_positive_decision_with_positive_outcome_is_confirmed_correct():
    d = fresh_db()
    original_id = add_decision(d, 1, "QUALIFIED", 0.8)
    add_outcome_observation(d, 1, "QUALIFIED", "WON")

    examples = calibration.confirmed_examples(d)

    assert len(examples) == 1
    assert examples[0]["ledger_id"] == original_id
    assert examples[0]["observed_correct"] == 1
    assert examples[0]["confirmation"] == "positive_later_outcome"


def test_rejection_with_positive_outcome_is_confirmed_wrong():
    d = fresh_db()
    original_id = add_decision(d, 2, "REJECTED", 0.9)
    add_outcome_observation(d, 2, "REJECTED", "REPLIED")

    examples = calibration.confirmed_examples(d)

    assert len(examples) == 1
    assert examples[0]["ledger_id"] == original_id
    assert examples[0]["observed_correct"] == 0
    assert examples[0]["confidence"] == 0.9


def test_human_correction_overrides_lower_authority_outcome_label():
    d = fresh_db()
    original_id = add_decision(d, 3, "QUALIFIED", 0.95)
    add_outcome_observation(d, 3, "QUALIFIED", "WON")
    ledger.record_correction(
        d,
        3,
        "Verified non-prospect",
        "REJECTED",
        0.99,
    )

    examples = calibration.confirmed_examples(d)

    assert len(examples) == 1
    assert examples[0]["ledger_id"] == original_id
    assert examples[0]["observed_correct"] == 0
    assert examples[0]["confirmation"] == "human_correction"


def test_ambiguous_negative_outcomes_do_not_become_ground_truth():
    d = fresh_db()
    add_decision(d, 4, "QUALIFIED", 0.8)
    add_outcome_observation(d, 4, "QUALIFIED", "LOST")
    add_outcome_observation(d, 4, "QUALIFIED", "NO_RESPONSE")

    assert calibration.confirmed_examples(d) == []


def test_unconfirmed_decisions_reduce_coverage_but_not_accuracy_sample():
    d = fresh_db()
    add_decision(d, 5, "QUALIFIED", 0.8)
    add_decision(d, 6, "QUALIFIED", 0.7)
    add_outcome_observation(d, 5, "QUALIFIED", "WON")

    result = calibration.calibration_report(d, bins=5, min_samples=1)

    assert result["eligible_decisions"] == 2
    assert result["confirmed_examples"] == 1
    assert result["coverage"] == 0.5
    assert result["observed_accuracy"] == 1.0


def test_calibration_bins_ece_and_brier_are_deterministic():
    d = fresh_db()
    add_decision(d, 10, "QUALIFIED", 0.9)
    add_outcome_observation(d, 10, "QUALIFIED", "WON")
    add_decision(d, 11, "REJECTED", 0.9)
    add_outcome_observation(d, 11, "REJECTED", "WON")
    add_decision(d, 12, "QUALIFIED", 0.6)
    add_outcome_observation(d, 12, "QUALIFIED", "REPLIED")
    add_decision(d, 13, "QUALIFIED", 0.6)
    ledger.record_correction(d, 13, "Wrong prospect", "REJECTED", 0.99)

    result = calibration.calibration_report(d, bins=5, min_samples=1)

    assert result["status"] == "MEASURED"
    assert result["confirmed_examples"] == 4
    assert result["observed_accuracy"] == 0.5
    assert result["avg_confidence"] == 0.75
    assert result["expected_calibration_error"] == 0.25
    assert result["brier_score"] == 0.335
    nonempty = [row for row in result["bins"] if row["count"]]
    assert sum(row["count"] for row in nonempty) == 4


def test_rule_versions_are_reported_separately():
    d = fresh_db()
    add_decision(d, 20, "QUALIFIED", 0.8, rule_version="v45.1")
    add_outcome_observation(
        d,
        20,
        "QUALIFIED",
        "WON",
        rule_version="v45.1",
    )
    add_decision(d, 21, "REJECTED", 0.7, rule_version="v45.2")
    add_outcome_observation(
        d,
        21,
        "REJECTED",
        "WON",
        rule_version="v45.2",
    )

    result = calibration.calibration_report(d, min_samples=1)

    assert result["rule_versions"]["v45.1"]["observed_accuracy"] == 1.0
    assert result["rule_versions"]["v45.2"]["observed_accuracy"] == 0.0


def test_low_sample_warning_is_explicit():
    d = fresh_db()
    add_decision(d, 30, "QUALIFIED", 0.8)
    add_outcome_observation(d, 30, "QUALIFIED", "WON")

    result = calibration.calibration_report(d, min_samples=30)

    assert result["status"] == "LOW_SAMPLE"
    assert result["sample_warning"]
    assert result["auto_threshold_changes"] is False
    assert result["advisory_only"] is True


def test_invalid_bin_count_fails_closed():
    d = fresh_db()
    try:
        calibration.calibration_report(d, bins=1)
    except ValueError as exc:
        assert "bins must be between 2 and 20" in str(exc)
    else:
        raise AssertionError("Expected invalid bin count to fail")
