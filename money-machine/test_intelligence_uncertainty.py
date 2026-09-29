"""Tests for read-only v45 statistical uncertainty analysis."""
import sqlite3

import mm_intelligence_ledger as ledger
import mm_intelligence_uncertainty as uncertainty


def fresh_db():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    return d


def add_decision(
    d,
    prospect_id,
    state,
    confidence=0.8,
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
            source="source-a",
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


def test_wilson_interval_known_half_success_case():
    result = uncertainty.wilson_interval(5, 10, 0.95)

    assert result["estimate"] == 0.5
    assert result["lower"] == 0.236593
    assert result["upper"] == 0.763407
    assert result["n"] == 10
    assert result["successes"] == 5


def test_wilson_interval_handles_empty_sample():
    result = uncertainty.wilson_interval(0, 0)

    assert result == {
        "estimate": None,
        "lower": None,
        "upper": None,
        "confidence_level": 0.95,
        "n": 0,
        "successes": 0,
    }


def test_wilson_interval_invalid_inputs_fail_closed():
    for successes, total in ((-1, 10), (11, 10), (1, -1)):
        try:
            uncertainty.wilson_interval(successes, total)
        except ValueError as exc:
            assert "0 <= successes <= total" in str(exc)
        else:
            raise AssertionError("Expected invalid Wilson inputs to fail")

    try:
        uncertainty.wilson_interval(1, 2, confidence_level=1.0)
    except ValueError as exc:
        assert "confidence_level must be between 0 and 1" in str(exc)
    else:
        raise AssertionError("Expected invalid confidence level to fail")


def test_exact_mcnemar_known_values():
    assert uncertainty.exact_mcnemar_p(0, 0) == 1.0
    assert uncertainty.exact_mcnemar_p(0, 5) == 0.0625
    assert uncertainty.exact_mcnemar_p(0, 6) == 0.03125
    assert uncertainty.exact_mcnemar_p(2, 2) == 1.0


def test_exact_mcnemar_rejects_negative_counts():
    try:
        uncertainty.exact_mcnemar_p(-1, 2)
    except ValueError as exc:
        assert "must be non-negative" in str(exc)
    else:
        raise AssertionError("Expected negative discordant count to fail")


def test_empty_database_is_insufficient_and_read_only():
    d = fresh_db()

    result = uncertainty.uncertainty_report(
        d,
        min_confirmed=5,
        min_matched=2,
    )

    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert result["confirmed_examples"] == 0
    assert result["overall"]["accuracy"]["estimate"] is None
    assert result["rule_versions"] == {}
    assert result["matched_rule_versions"] == []
    assert result["read_only"] is True
    assert result["promotion_authorized"] is False
    assert result["merge_authority"] is False
    assert result["deployment_authorized"] is False


def test_overall_and_rule_version_intervals_are_reported():
    d = fresh_db()

    for prospect_id in (1, 2, 3):
        add_decision(d, prospect_id, "QUALIFIED", 0.8, "v45.2")
        add_outcome(d, prospect_id, "QUALIFIED", "WON", "v45.2")

    add_decision(d, 4, "REJECTED", 0.8, "v45.2")
    add_outcome(d, 4, "REJECTED", "WON", "v45.2")

    result = uncertainty.uncertainty_report(
        d,
        min_confirmed=4,
        min_matched=1,
    )

    assert result["status"] == "MEASURED"
    assert result["overall"]["confirmed_examples"] == 4
    assert result["overall"]["correct"] == 3
    assert result["overall"]["errors"] == 1
    assert result["overall"]["accuracy"]["estimate"] == 0.75
    assert result["overall"]["error_rate"]["estimate"] == 0.25

    v2 = result["rule_versions"]["v45.2"]
    assert v2["confirmed_examples"] == 4
    assert v2["accuracy"]["estimate"] == 0.75
    assert v2["sample_status"] == "MEASURED"


def _populate_matched_version_improvement(d, count=6):
    for prospect_id in range(100, 100 + count):
        add_decision(
            d,
            prospect_id,
            "REJECTED",
            0.9,
            rule_version="v45.1",
        )
        ledger.record_correction(
            d,
            prospect_id,
            "v45.1 missed a verified positive",
            "QUALIFIED",
            0.99,
            rule_version="v45.1",
        )
        add_decision(
            d,
            prospect_id,
            "QUALIFIED",
            0.9,
            rule_version="v45.2",
        )
        add_outcome(
            d,
            prospect_id,
            "QUALIFIED",
            "WON",
            rule_version="v45.2",
        )


def test_matched_rule_versions_get_exact_mcnemar_evidence():
    d = fresh_db()
    _populate_matched_version_improvement(d, count=6)

    result = uncertainty.uncertainty_report(
        d,
        min_confirmed=6,
        min_matched=6,
        alpha=0.05,
    )

    assert len(result["matched_rule_versions"]) == 1
    matched = result["matched_rule_versions"][0]
    assert matched["version_a"] == "v45.1"
    assert matched["version_b"] == "v45.2"
    assert matched["matched_prospects"] == 6
    assert matched["version_a_only_correct"] == 0
    assert matched["version_b_only_correct"] == 6
    assert matched["discordant_pairs"] == 6
    assert matched["exact_mcnemar_p"] == 0.03125
    assert matched["direction"] == "VERSION_B_HIGHER_ON_MATCHED"
    assert matched["statistically_distinguishable_at_alpha"] is True
    assert matched["promotion_authorized"] is False


def test_low_matched_sample_suppresses_statistical_distinction_flag():
    d = fresh_db()
    _populate_matched_version_improvement(d, count=6)

    result = uncertainty.uncertainty_report(
        d,
        min_confirmed=6,
        min_matched=10,
        alpha=0.05,
    )

    matched = result["matched_rule_versions"][0]
    assert matched["exact_mcnemar_p"] == 0.03125
    assert matched["sample_status"] == "LOW_SAMPLE"
    assert matched["statistically_distinguishable_at_alpha"] is False


def test_invalid_report_probability_parameters_fail_closed():
    d = fresh_db()

    for kwargs, message in (
        ({"confidence_level": 0.0}, "confidence_level must be between 0 and 1"),
        ({"alpha": 1.0}, "alpha must be between 0 and 1"),
    ):
        try:
            uncertainty.uncertainty_report(d, **kwargs)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError("Expected invalid probability parameter to fail")


def test_statistical_evidence_never_grants_execution_authority():
    d = fresh_db()
    _populate_matched_version_improvement(d, count=6)

    result = uncertainty.uncertainty_report(
        d,
        min_confirmed=6,
        min_matched=6,
    )

    assert result["causal_claim_allowed"] is False
    assert result["automatic_rule_change"] is False
    assert result["promotion_authorized"] is False
    assert result["merge_authority"] is False
    assert result["deployment_authorized"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
    assert "not randomized" in result["method"]
