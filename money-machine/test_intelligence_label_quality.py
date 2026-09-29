"""Tests for read-only v45 confirmed-label quality diagnostics."""
import sqlite3

import mm_intelligence_label_quality as label_quality
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
    *,
    source="source-a",
    rule_version="v45.2",
    stage="qualification",
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
            stage=stage,
            source=source,
        ),
    )


def add_outcome(d, prospect_id, state, observed, *, source="source-a"):
    return ledger.append_decision(
        d,
        ledger.IntelligenceDecision(
            prospect_id=prospect_id,
            business_name=f"Business {prospect_id}",
            domain=f"business{prospect_id}.co.nz",
            decision=state,
            disposition="OUTCOME_OBSERVED",
            confidence=0.5,
            rule_version="v45.2",
            stage="outcome",
            source=source,
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

    result = label_quality.label_quality_report(d)

    after = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )
    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert result["confirmed_examples"] == 0
    assert "LOW_SAMPLE" in result["flags"]
    assert result["confirmation_channels"] == {}
    assert result["expected_classes"] == {}
    assert result["read_only"] is True
    assert result["automatic_label_policy_change"] is False
    assert result["automatic_promotion_gate_change"] is False
    assert after == before


def test_positive_outcome_only_sample_surfaces_channel_and_class_bias():
    d = fresh_db()
    for prospect_id in range(1, 5):
        add_decision(d, prospect_id, "QUALIFIED", source="source-a")
        add_outcome(d, prospect_id, "QUALIFIED", "WON")

    result = label_quality.label_quality_report(
        d,
        min_confirmed=4,
        max_source_share=1.0,
    )

    assert result["status"] == "REPRESENTATIVENESS_WARNINGS"
    assert result["confirmation_channels"] == {
        "positive_later_outcome": 4
    }
    assert result["expected_classes"] == {"POSITIVE": 4}
    assert "SINGLE_CONFIRMATION_CHANNEL" in result["flags"]
    assert "SINGLE_EXPECTED_CLASS" in result["flags"]
    assert "Positive later outcomes" in result["known_label_asymmetry"]


def test_human_corrections_can_supply_both_expected_classes():
    d = fresh_db()
    add_decision(d, 10, "QUALIFIED", source="source-a")
    ledger.record_correction(
        d,
        10,
        "Verified negative",
        "REJECTED",
        0.99,
    )
    add_decision(d, 11, "REJECTED", source="source-b")
    ledger.record_correction(
        d,
        11,
        "Verified positive",
        "QUALIFIED",
        0.99,
    )

    result = label_quality.label_quality_report(
        d,
        min_confirmed=2,
        max_source_share=1.0,
    )

    assert result["expected_classes"] == {
        "NEGATIVE": 1,
        "POSITIVE": 1,
    }
    assert result["confirmation_channels"] == {
        "human_correction": 2
    }
    assert "SINGLE_EXPECTED_CLASS" not in result["flags"]
    assert "SINGLE_CONFIRMATION_CHANNEL" in result["flags"]


def test_mixed_channels_classes_and_sources_can_be_measured_cleanly():
    d = fresh_db()

    add_decision(d, 20, "QUALIFIED", source="source-a")
    add_outcome(d, 20, "QUALIFIED", "WON")

    add_decision(d, 21, "REJECTED", source="source-b")
    add_outcome(d, 21, "REJECTED", "WON")

    add_decision(d, 22, "QUALIFIED", source="source-a")
    ledger.record_correction(
        d,
        22,
        "Verified negative",
        "REJECTED",
        0.99,
    )

    add_decision(d, 23, "REJECTED", source="source-b")
    ledger.record_correction(
        d,
        23,
        "Verified positive",
        "QUALIFIED",
        0.99,
    )

    result = label_quality.label_quality_report(
        d,
        min_confirmed=4,
        max_source_share=0.75,
    )

    assert result["status"] == "MEASURED"
    assert result["flags"] == []
    assert result["confirmation_channels"] == {
        "human_correction": 2,
        "positive_later_outcome": 2,
    }
    assert result["expected_classes"] == {
        "NEGATIVE": 1,
        "POSITIVE": 3,
    }
    assert result["sources"] == {
        "source-a": 2,
        "source-b": 2,
    }
    assert result["largest_source_share"] == 0.5


def test_source_concentration_warning_is_thresholded():
    d = fresh_db()
    for prospect_id in range(30, 34):
        add_decision(d, prospect_id, "QUALIFIED", source="dominant")
        add_outcome(d, prospect_id, "QUALIFIED", "WON")
    add_decision(d, 34, "QUALIFIED", source="other")
    ledger.record_correction(
        d,
        34,
        "Verified negative",
        "REJECTED",
        0.99,
    )

    result = label_quality.label_quality_report(
        d,
        min_confirmed=5,
        max_source_share=0.70,
    )

    assert result["largest_source_share"] == 0.8
    assert "SOURCE_CONCENTRATION" in result["flags"]
    assert result["status"] == "REPRESENTATIVENESS_WARNINGS"


def test_repeated_prospect_labels_are_visible():
    d = fresh_db()

    add_decision(
        d,
        40,
        "REJECTED",
        source="source-a",
        rule_version="v45.1",
    )
    add_outcome(d, 40, "REJECTED", "WON")

    add_decision(
        d,
        40,
        "QUALIFIED",
        source="source-b",
        rule_version="v45.2",
    )
    add_outcome(d, 40, "QUALIFIED", "WON")

    result = label_quality.label_quality_report(
        d,
        min_confirmed=2,
        max_source_share=1.0,
    )

    assert result["confirmed_examples"] == 2
    assert result["unique_prospects"] == 1
    assert result["repeated_prospect_examples"] == 1
    assert "REPEATED_PROSPECT_LABELS" in result["flags"]


def test_rule_stage_and_confirmation_concentration_are_reported():
    d = fresh_db()
    for prospect_id in (50, 51):
        add_decision(
            d,
            prospect_id,
            "QUALIFIED",
            source="source-a",
            rule_version="v45.2",
            stage="qualification",
        )
        add_outcome(d, prospect_id, "QUALIFIED", "WON")

    result = label_quality.label_quality_report(
        d,
        min_confirmed=2,
        max_source_share=1.0,
    )

    assert result["largest_confirmation_channel_share"] == 1.0
    assert result["largest_rule_version_share"] == 1.0
    assert result["largest_stage_share"] == 1.0
    assert result["rule_versions"] == {"v45.2": 2}
    assert result["stages"] == {"qualification": 2}


def test_low_sample_warning_remains_even_with_balanced_classes():
    d = fresh_db()
    add_decision(d, 60, "QUALIFIED", source="source-a")
    ledger.record_correction(
        d,
        60,
        "Verified negative",
        "REJECTED",
        0.99,
    )
    add_decision(d, 61, "REJECTED", source="source-b")
    ledger.record_correction(
        d,
        61,
        "Verified positive",
        "QUALIFIED",
        0.99,
    )

    result = label_quality.label_quality_report(
        d,
        min_confirmed=10,
        max_source_share=1.0,
    )

    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert "LOW_SAMPLE" in result["flags"]


def test_label_quality_never_changes_policy_automatically():
    d = fresh_db()
    add_decision(d, 70, "QUALIFIED", source="source-a")
    add_outcome(d, 70, "QUALIFIED", "WON")

    result = label_quality.label_quality_report(
        d,
        min_confirmed=1,
        max_source_share=1.0,
    )

    assert result["causal_claim_allowed"] is False
    assert result["automatic_label_policy_change"] is False
    assert result["automatic_promotion_gate_change"] is False
    assert result["promotion_authorized"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
    assert "do not prove" in result["method"]
