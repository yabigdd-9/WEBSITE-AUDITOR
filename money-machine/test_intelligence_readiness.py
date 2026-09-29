"""Tests for fail-closed v45 promotion-readiness synthesis."""
import sqlite3

import mm_intelligence_ledger as ledger
import mm_intelligence_readiness as readiness


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


def add_correct_positive(d, prospect_id, rule_version="v45.2"):
    add_decision(d, prospect_id, "QUALIFIED", 0.8, rule_version)
    add_outcome(d, prospect_id, "QUALIFIED", "WON", rule_version)


def add_wrong_negative(d, prospect_id, rule_version="v45.2"):
    add_decision(d, prospect_id, "REJECTED", 0.2, rule_version)
    add_outcome(d, prospect_id, "REJECTED", "WON", rule_version)


def stable_evidence_db():
    d = fresh_db()
    # Older window: 3 correct + 1 confirmed false negative.
    for prospect_id in (1, 2, 3):
        add_correct_positive(d, prospect_id)
    add_wrong_negative(d, 4)

    # Recent window: same composition, so no adjacent-window drift.
    for prospect_id in (5, 6, 7):
        add_correct_positive(d, prospect_id)
    add_wrong_negative(d, 8)
    return d


def good_holdout(validation_count=2):
    return {
        "baseline": {
            "accuracy": 0.5,
            "safety_failures": 0,
        },
        "challenger": {
            "accuracy": 1.0,
            "safety_failures": 0,
        },
        "promotion_recommended": True,
        "recommendation_basis": "validation_holdout_only",
        "split": {
            "training_count": 6,
            "validation_count": validation_count,
            "validation_fraction": 0.25,
            "salt": "test",
            "deterministic": True,
        },
        "promotion_authorized": False,
    }


def report(d, **overrides):
    args = {
        "candidate_rule_version": "v45.2",
        "holdout_result": good_holdout(),
        "min_confirmed": 8,
        "min_hard_cases": 2,
        "min_validation_cases": 2,
        "min_rule_samples": 8,
        "max_ece": 0.25,
        "max_brier": 0.10,
        "drift_window": 4,
        "drift_min_samples": 4,
    }
    args.update(overrides)
    return readiness.readiness_report(d, **args)


def test_fully_evidenced_candidate_is_only_ready_for_human_review():
    d = stable_evidence_db()

    result = report(d)

    assert result["status"] == "READY_FOR_HUMAN_REVIEW"
    assert result["blockers"] == []
    assert result["blocker_count"] == 0
    assert all(gate["passed"] for gate in result["gates"])
    assert result["review_only"] is True
    assert result["human_or_integrator_decision_required"] is True
    assert result["promotion_authorized"] is False
    assert result["merge_authority"] is False
    assert result["deployment_authorized"] is False
    assert result["automatic_rule_change"] is False
    assert result["automatic_source_change"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0


def test_missing_holdout_fails_closed():
    d = stable_evidence_db()

    result = report(d, holdout_result=None)

    assert result["status"] == "NOT_READY_FOR_HUMAN_REVIEW"
    assert "holdout_present" in {
        blocker["gate"] for blocker in result["blockers"]
    }
    assert result["promotion_authorized"] is False


def test_unobserved_candidate_rule_fails_closed():
    d = stable_evidence_db()

    result = report(d, candidate_rule_version="v46-unseen")

    blockers = {item["gate"] for item in result["blockers"]}
    assert result["status"] == "NOT_READY_FOR_HUMAN_REVIEW"
    assert "candidate_rule_observed" in blockers
    assert "candidate_rule_sample_size" in blockers


def test_candidate_rule_must_be_named():
    d = stable_evidence_db()

    result = report(d, candidate_rule_version=None)

    assert result["status"] == "NOT_READY_FOR_HUMAN_REVIEW"
    assert "candidate_rule_specified" in {
        blocker["gate"] for blocker in result["blockers"]
    }


def test_insufficient_hard_cases_blocks_review_readiness():
    d = stable_evidence_db()

    result = report(d, min_hard_cases=3)

    assert result["status"] == "NOT_READY_FOR_HUMAN_REVIEW"
    hard_gate = next(
        gate
        for gate in result["gates"]
        if gate["gate"] == "confirmed_hard_case_size"
    )
    assert hard_gate["observed"] == 2
    assert hard_gate["required"] == 3
    assert hard_gate["passed"] is False


def test_holdout_safety_failure_blocks_review_readiness():
    d = stable_evidence_db()
    holdout = good_holdout()
    holdout["challenger"]["safety_failures"] = 1

    result = report(d, holdout_result=holdout)

    assert result["status"] == "NOT_READY_FOR_HUMAN_REVIEW"
    safety = next(
        gate for gate in result["gates"] if gate["gate"] == "holdout_safety"
    )
    assert safety["passed"] is False
    assert safety["observed"] == 1


def test_holdout_must_use_validation_only_recommendation_basis():
    d = stable_evidence_db()
    holdout = good_holdout()
    holdout["recommendation_basis"] = "full_corpus"

    result = report(d, holdout_result=holdout)

    assert result["status"] == "NOT_READY_FOR_HUMAN_REVIEW"
    assert "holdout_recommendation_basis" in {
        blocker["gate"] for blocker in result["blockers"]
    }


def test_drift_blocks_review_even_with_good_holdout():
    d = fresh_db()
    # Older window all correct.
    for prospect_id in range(1, 5):
        add_correct_positive(d, prospect_id)
    # Recent window all wrong.
    for prospect_id in range(5, 9):
        add_wrong_negative(d, prospect_id)

    result = report(
        d,
        min_hard_cases=4,
        max_ece=1.0,
        max_brier=1.0,
    )

    drift_gate = next(
        gate for gate in result["gates"] if gate["gate"] == "drift_clear"
    )
    assert result["status"] == "NOT_READY_FOR_HUMAN_REVIEW"
    assert drift_gate["passed"] is False
    assert drift_gate["observed"]["status"] == "REVIEW_DRIFT"
    assert "ACCURACY_DROP" in drift_gate["observed"]["flags"]


def test_poor_calibration_blocks_review_readiness():
    d = fresh_db()
    # Same stable error mix in both windows, but highly overconfident errors.
    for prospect_id in (1, 2, 3):
        add_decision(d, prospect_id, "QUALIFIED", 0.99)
        add_outcome(d, prospect_id, "QUALIFIED", "WON")
    add_decision(d, 4, "REJECTED", 0.99)
    add_outcome(d, 4, "REJECTED", "WON")

    for prospect_id in (5, 6, 7):
        add_decision(d, prospect_id, "QUALIFIED", 0.99)
        add_outcome(d, prospect_id, "QUALIFIED", "WON")
    add_decision(d, 8, "REJECTED", 0.99)
    add_outcome(d, 8, "REJECTED", "WON")

    result = report(
        d,
        max_ece=0.05,
        max_brier=0.05,
    )

    blockers = {item["gate"] for item in result["blockers"]}
    assert result["status"] == "NOT_READY_FOR_HUMAN_REVIEW"
    assert (
        "expected_calibration_error" in blockers
        or "brier_score" in blockers
    )


def test_report_never_converts_readiness_into_authority():
    d = stable_evidence_db()

    result = report(d)

    assert result["status"] == "READY_FOR_HUMAN_REVIEW"
    for key in (
        "promotion_authorized",
        "merge_authority",
        "deployment_authorized",
        "automatic_rule_change",
        "automatic_source_change",
    ):
        assert result[key] is False
