"""Tests for read-only v45 review-efficiency analysis."""
import sqlite3

import mm_intelligence_ledger as ledger
import mm_intelligence_review_efficiency as review_efficiency


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
    missing=None,
    source="searxng-local:q1",
    rule_version="v45.2",
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
            source=source,
            derived_evidence=derived,
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


def metric(result, name):
    return next(item for item in result["signals"] if item["signal"] == name)


def test_empty_database_is_insufficient_and_read_only():
    d = fresh_db()
    before = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )

    result = review_efficiency.review_efficiency_report(d)

    after = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )
    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert result["confirmed_examples"] == 0
    assert result["signals"] == []
    assert result["combined"] is None
    assert result["automatic_queue_change"] is False
    assert result["automatic_threshold_change"] is False
    assert after == before


def test_low_confidence_signal_measures_precision_recall_and_workload():
    d = fresh_db()
    # Two low-confidence errors.
    for prospect_id in (1, 2):
        add_decision(d, prospect_id, "REJECTED", confidence=0.6)
        add_outcome(d, prospect_id, "REJECTED", "WON")
    # One low-confidence correct decision.
    add_decision(d, 3, "QUALIFIED", confidence=0.7)
    add_outcome(d, 3, "QUALIFIED", "WON")
    # One high-confidence correct decision.
    add_decision(d, 4, "QUALIFIED", confidence=0.95)
    add_outcome(d, 4, "QUALIFIED", "WON")

    result = review_efficiency.review_efficiency_report(
        d,
        min_confirmed=4,
        min_signal_samples=1,
        low_confidence_threshold=0.8,
    )
    low = metric(result, "low_confidence")

    assert result["confirmed_examples"] == 4
    assert result["confirmed_errors"] == 2
    assert result["baseline_error_rate"] == 0.5
    assert low["flagged_confirmed_examples"] == 3
    assert low["errors_caught"] == 2
    assert low["correct_flagged"] == 1
    assert low["error_precision"] == 0.6667
    assert low["error_recall"] == 1.0
    assert low["review_workload_rate"] == 0.75
    assert low["reviews_per_error_caught"] == 1.5


def test_missing_and_multiple_missing_evidence_are_measured_separately():
    d = fresh_db()
    add_decision(
        d,
        10,
        "REJECTED",
        confidence=0.9,
        missing=["booking_flow", "commercial_evidence"],
    )
    add_outcome(d, 10, "REJECTED", "WON")

    add_decision(
        d,
        11,
        "QUALIFIED",
        confidence=0.9,
        missing=["contact_page"],
    )
    add_outcome(d, 11, "QUALIFIED", "WON")

    result = review_efficiency.review_efficiency_report(
        d,
        min_confirmed=2,
        min_signal_samples=1,
    )
    missing = metric(result, "missing_evidence")
    multiple = metric(result, "multiple_missing_evidence")

    assert missing["flagged_confirmed_examples"] == 2
    assert missing["errors_caught"] == 1
    assert missing["error_precision"] == 0.5
    assert multiple["flagged_confirmed_examples"] == 1
    assert multiple["errors_caught"] == 1
    assert multiple["error_precision"] == 1.0


def test_prior_polarity_change_flags_only_the_later_decision():
    d = fresh_db()
    add_decision(d, 20, "QUALIFIED", confidence=0.9)
    second = add_decision(d, 20, "REJECTED", confidence=0.9)
    add_outcome(d, 20, "REJECTED", "WON")

    result = review_efficiency.review_efficiency_report(
        d,
        min_confirmed=1,
        min_signal_samples=1,
    )
    flip = metric(result, "prior_polarity_change")

    assert flip["flagged_confirmed_examples"] == 1
    assert flip["errors_caught"] == 1
    assert flip["error_precision"] == 1.0

    confirmed_ids = {
        row["ledger_id"]
        for row in __import__(
            "mm_intelligence_calibration"
        ).confirmed_examples(d)
    }
    assert second in confirmed_ids


def test_future_flip_does_not_retroactively_flag_earlier_confirmed_error():
    d = fresh_db()
    first = add_decision(d, 30, "REJECTED", confidence=0.9)
    add_outcome(d, 30, "REJECTED", "WON")
    # This happens later and must not leak back into the original signal set.
    add_decision(d, 30, "QUALIFIED", confidence=0.9)

    result = review_efficiency.review_efficiency_report(
        d,
        min_confirmed=1,
        min_signal_samples=1,
    )
    flip = metric(result, "prior_polarity_change")

    assert result["confirmed_examples"] == 1
    assert flip["flagged_confirmed_examples"] == 0

    confirmed = __import__(
        "mm_intelligence_calibration"
    ).confirmed_examples(d)
    assert confirmed[0]["ledger_id"] == first


def test_rule_version_and_stage_boundaries_prevent_false_flip_signal():
    d = fresh_db()
    add_decision(
        d,
        40,
        "QUALIFIED",
        confidence=0.9,
        rule_version="v45.1",
        stage="qualification",
    )
    add_decision(
        d,
        40,
        "REJECTED",
        confidence=0.9,
        rule_version="v45.2",
        stage="qualification",
    )
    add_outcome(d, 40, "REJECTED", "WON", rule_version="v45.2")

    add_decision(
        d,
        41,
        "QUALIFIED",
        confidence=0.9,
        stage="identity",
    )
    add_decision(
        d,
        41,
        "REJECTED",
        confidence=0.9,
        stage="qualification",
    )
    add_outcome(d, 41, "REJECTED", "WON")

    result = review_efficiency.review_efficiency_report(
        d,
        min_confirmed=2,
        min_signal_samples=1,
    )
    flip = metric(result, "prior_polarity_change")

    assert flip["flagged_confirmed_examples"] == 0


def test_missing_source_is_measured_as_review_signal():
    d = fresh_db()
    add_decision(
        d,
        50,
        "REJECTED",
        confidence=0.9,
        source="",
    )
    add_outcome(d, 50, "REJECTED", "WON")
    add_decision(
        d,
        51,
        "QUALIFIED",
        confidence=0.9,
        source="searxng-local:q1",
    )
    add_outcome(d, 51, "QUALIFIED", "WON")

    result = review_efficiency.review_efficiency_report(
        d,
        min_confirmed=2,
        min_signal_samples=1,
    )
    source = metric(result, "missing_source")

    assert source["flagged_confirmed_examples"] == 1
    assert source["errors_caught"] == 1
    assert source["error_precision"] == 1.0


def test_combined_signal_reports_total_review_load_without_double_counting():
    d = fresh_db()
    add_decision(
        d,
        60,
        "REJECTED",
        confidence=0.6,
        missing=["booking_flow", "commercial_evidence"],
        source="",
    )
    add_outcome(d, 60, "REJECTED", "WON")
    add_decision(
        d,
        61,
        "QUALIFIED",
        confidence=0.95,
    )
    add_outcome(d, 61, "QUALIFIED", "WON")

    result = review_efficiency.review_efficiency_report(
        d,
        min_confirmed=2,
        min_signal_samples=1,
    )
    combined = result["combined"]

    assert combined["flagged_confirmed_examples"] == 1
    assert combined["errors_caught"] == 1
    assert combined["error_precision"] == 1.0
    assert combined["error_recall"] == 1.0
    assert combined["review_workload_rate"] == 0.5


def test_low_sample_signal_is_not_overinterpreted():
    d = fresh_db()
    add_decision(d, 70, "REJECTED", confidence=0.5)
    add_outcome(d, 70, "REJECTED", "WON")

    result = review_efficiency.review_efficiency_report(
        d,
        min_confirmed=1,
        min_signal_samples=3,
    )
    low = metric(result, "low_confidence")

    assert low["status"] == "LOW_SAMPLE"


def test_review_efficiency_never_reweights_queue_automatically():
    d = fresh_db()
    add_decision(d, 80, "REJECTED", confidence=0.5)
    add_outcome(d, 80, "REJECTED", "WON")

    result = review_efficiency.review_efficiency_report(
        d,
        min_confirmed=1,
        min_signal_samples=1,
    )

    assert result["status"] == "MEASURED"
    assert result["read_only"] is True
    assert result["causal_claim_allowed"] is False
    assert result["automatic_queue_change"] is False
    assert result["automatic_threshold_change"] is False
    assert result["promotion_authorized"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
    assert "never used as review signals" in result["method"]
