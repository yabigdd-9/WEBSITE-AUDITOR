"""Tests for read-only v45 historical evidence-value analysis."""
import sqlite3

import mm_intelligence_evidence_value as evidence_value
import mm_intelligence_ledger as ledger


def fresh_db():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    return d


def add_decision(
    d,
    prospect_id,
    state,
    confidence=0.8,
    missing=None,
    rule_version="v45.1",
    stage="qualification",
):
    derived = {}
    if missing is not None:
        derived["missing_evidence"] = missing
    return ledger.append_decision(
        d,
        ledger.IntelligenceDecision(
            prospect_id=prospect_id,
            business_name=f"Business {prospect_id}",
            domain=f"business{prospect_id}.co.nz",
            decision=state,
            confidence=confidence,
            rule_version=rule_version,
            stage=stage,
            source="searxng-local:q1",
            derived_evidence=derived,
        ),
    )


def add_outcome(d, prospect_id, state, observed, rule_version="v45.1"):
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


def test_empty_database_is_zero_and_read_only():
    d = fresh_db()
    before = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )

    result = evidence_value.evidence_value_report(d)

    after = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )
    assert result["field_count"] == 0
    assert result["confirmed_examples"] == 0
    assert result["confirmed_error_rate"] is None
    assert result["coverage"] == 0.0
    assert result["read_only"] is True
    assert result["causal_claim_allowed"] is False
    assert result["automatic_evidence_priority_change"] is False
    assert after == before


def test_confirmed_false_negative_is_counted_against_missing_field():
    d = fresh_db()
    add_decision(
        d,
        1,
        "REJECTED",
        confidence=0.9,
        missing=["booking_flow"],
    )
    add_outcome(d, 1, "REJECTED", "WON")

    result = evidence_value.evidence_value_report(
        d,
        min_samples=1,
    )
    field = result["fields"][0]

    assert field["field"] == "booking_flow"
    assert field["confirmed_examples"] == 1
    assert field["errors"] == 1
    assert field["confirmed_false_negatives"] == 1
    assert field["confirmed_false_positives"] == 0
    assert field["high_confidence_errors"] == 1
    assert field["error_rate"] == 1.0


def test_confirmed_false_positive_is_counted_separately():
    d = fresh_db()
    add_decision(
        d,
        2,
        "QUALIFIED",
        confidence=0.95,
        missing=["identity_corroboration"],
    )
    ledger.record_correction(
        d,
        2,
        "Verified wrong business",
        "REJECTED",
        0.99,
    )

    result = evidence_value.evidence_value_report(
        d,
        min_samples=1,
    )
    field = result["fields"][0]

    assert field["confirmed_false_positives"] == 1
    assert field["confirmed_false_negatives"] == 0
    assert field["confirmations"] == {"human_correction": 1}


def test_confirmed_correct_case_with_missing_field_is_not_an_error():
    d = fresh_db()
    add_decision(
        d,
        3,
        "QUALIFIED",
        confidence=0.8,
        missing=["contact_page"],
    )
    add_outcome(d, 3, "QUALIFIED", "REPLIED")

    result = evidence_value.evidence_value_report(
        d,
        min_samples=1,
    )
    field = result["fields"][0]

    assert field["confirmed_examples"] == 1
    assert field["errors"] == 0
    assert field["correct"] == 1
    assert field["error_rate"] == 0.0
    assert field["signal"] == "NO_CONFIRMED_ERRORS_IN_SAMPLE"


def test_elevated_error_association_is_relative_to_all_confirmed_cases():
    d = fresh_db()
    # Two confirmed wrong decisions with the same missing field.
    for prospect_id in (10, 11):
        add_decision(
            d,
            prospect_id,
            "REJECTED",
            confidence=0.9,
            missing=["booking_flow"],
        )
        add_outcome(d, prospect_id, "REJECTED", "WON")

    # Two confirmed correct decisions without named missing evidence.
    for prospect_id in (12, 13):
        add_decision(
            d,
            prospect_id,
            "QUALIFIED",
            confidence=0.8,
            missing=[],
        )
        add_outcome(d, prospect_id, "QUALIFIED", "WON")

    result = evidence_value.evidence_value_report(
        d,
        min_samples=2,
    )
    field = result["fields"][0]

    assert result["confirmed_examples"] == 4
    assert result["confirmed_errors"] == 2
    assert result["confirmed_error_rate"] == 0.5
    assert result["coverage"] == 0.5
    assert field["confirmed_examples"] == 2
    assert field["error_rate"] == 1.0
    assert field["error_rate_delta_vs_all_confirmed"] == 0.5
    assert field["signal"] == "ELEVATED_ERROR_ASSOCIATION"
    assert field["causal_claim_allowed"] is False
    assert field["automatic_priority_change"] is False


def test_duplicate_missing_field_names_count_once_per_confirmed_example():
    d = fresh_db()
    add_decision(
        d,
        20,
        "REJECTED",
        confidence=0.8,
        missing=["booking_flow", "booking_flow", " booking_flow "],
    )
    add_outcome(d, 20, "REJECTED", "WON")

    result = evidence_value.evidence_value_report(
        d,
        min_samples=1,
    )

    assert result["field_count"] == 1
    assert result["fields"][0]["confirmed_examples"] == 1
    assert result["fields"][0]["field"] == "booking_flow"


def test_malformed_missing_evidence_is_ignored():
    d = fresh_db()
    add_decision(
        d,
        30,
        "QUALIFIED",
        confidence=0.8,
        missing="not-a-list",
    )
    add_outcome(d, 30, "QUALIFIED", "WON")

    result = evidence_value.evidence_value_report(d)

    assert result["confirmed_examples"] == 1
    assert result["field_count"] == 0
    assert result["examples_with_named_missing_evidence"] == 0


def test_field_composition_tracks_stage_and_rule_version():
    d = fresh_db()
    add_decision(
        d,
        40,
        "REJECTED",
        confidence=0.9,
        missing=["commercial_evidence"],
        rule_version="v45.2",
        stage="qualification",
    )
    add_outcome(d, 40, "REJECTED", "WON", rule_version="v45.2")

    result = evidence_value.evidence_value_report(
        d,
        min_samples=1,
    )
    field = result["fields"][0]

    assert field["stages"] == {"qualification": 1}
    assert field["rule_versions"] == {"v45.2": 1}


def test_low_sample_field_is_not_overinterpreted():
    d = fresh_db()
    add_decision(
        d,
        50,
        "REJECTED",
        confidence=0.9,
        missing=["rare_field"],
    )
    add_outcome(d, 50, "REJECTED", "WON")

    result = evidence_value.evidence_value_report(
        d,
        min_samples=3,
    )

    assert result["fields"][0]["signal"] == "INSUFFICIENT_EVIDENCE"


def test_no_evidence_value_signal_can_change_priorities_automatically():
    d = fresh_db()
    add_decision(
        d,
        60,
        "REJECTED",
        confidence=0.99,
        missing=["booking_flow"],
    )
    add_outcome(d, 60, "REJECTED", "WON")

    result = evidence_value.evidence_value_report(
        d,
        min_samples=1,
        high_confidence_threshold=0.95,
    )

    assert result["fields"][0]["high_confidence_errors"] == 1
    assert result["causal_claim_allowed"] is False
    assert result["automatic_evidence_priority_change"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
    assert "does not prove" in result["method"]
