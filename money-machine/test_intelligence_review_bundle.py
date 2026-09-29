"""Tests for deterministic v45 intelligence review bundles."""
import json
import sqlite3

import mm_intelligence_ledger as ledger
import mm_intelligence_review_bundle as review_bundle


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
            derived_evidence={
                "missing_evidence": ["booking_flow"],
                "private_note": "DO-NOT-INCLUDE",
            },
        ),
    )


def add_outcome(
    d,
    prospect_id,
    state,
    observed,
    rule_version="v45.2",
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
            later_outcome=observed,
        ),
    )


def stable_db():
    d = fresh_db()
    for prospect_id in (1, 2, 3):
        add_decision(d, prospect_id, "QUALIFIED", 0.8)
        add_outcome(d, prospect_id, "QUALIFIED", "WON")
    add_decision(d, 4, "REJECTED", 0.2)
    add_outcome(d, 4, "REJECTED", "WON")
    for prospect_id in (5, 6, 7):
        add_decision(d, prospect_id, "QUALIFIED", 0.8)
        add_outcome(d, prospect_id, "QUALIFIED", "WON")
    add_decision(d, 8, "REJECTED", 0.2)
    add_outcome(d, 8, "REJECTED", "WON")
    return d


def holdout():
    return {
        "baseline": {"accuracy": 0.5, "safety_failures": 0},
        "challenger": {"accuracy": 1.0, "safety_failures": 0},
        "promotion_recommended": True,
        "recommendation_basis": "validation_holdout_only",
        "split": {
            "training_count": 6,
            "validation_count": 2,
            "validation_fraction": 0.25,
            "salt": "test",
            "deterministic": True,
        },
        "promotion_authorized": False,
    }


def bundle(d, **overrides):
    args = {
        "candidate_rule_version": "v45.2",
        "holdout_result": holdout(),
        "min_confirmed": 8,
        "min_hard_cases": 2,
        "min_validation_cases": 2,
        "min_rule_samples": 8,
        "max_ece": 0.25,
        "max_brier": 0.10,
        "drift_window": 4,
        "drift_min_samples": 4,
        "limit": 5000,
    }
    args.update(overrides)
    return review_bundle.build_review_bundle(d, **args)


def test_identical_evidence_and_config_produce_identical_fingerprint():
    d = stable_db()

    first = bundle(d)
    second = bundle(d)

    assert first["fingerprint_sha256"] == second["fingerprint_sha256"]
    assert first["manifest"] == second["manifest"]
    assert len(first["fingerprint_sha256"]) == 64
    assert first["canonical_manifest_bytes"] > 0


def test_new_confirmed_evidence_changes_fingerprint():
    d = stable_db()
    before = bundle(d)

    add_decision(d, 9, "QUALIFIED", 0.8)
    add_outcome(d, 9, "QUALIFIED", "WON")

    after = bundle(d, min_confirmed=8, min_rule_samples=8)

    assert before["fingerprint_sha256"] != after["fingerprint_sha256"]
    assert (
        before["manifest"]["evidence"]["confirmed_examples_sha256"]
        != after["manifest"]["evidence"]["confirmed_examples_sha256"]
    )


def test_holdout_change_changes_fingerprint():
    d = stable_db()
    first = bundle(d)

    changed = holdout()
    changed["challenger"]["accuracy"] = 0.75
    second = bundle(d, holdout_result=changed)

    assert first["fingerprint_sha256"] != second["fingerprint_sha256"]
    assert (
        first["manifest"]["evidence"]["holdout_result_sha256"]
        != second["manifest"]["evidence"]["holdout_result_sha256"]
    )


def test_threshold_change_changes_fingerprint_even_when_evidence_same():
    d = stable_db()

    first = bundle(d, max_ece=0.25)
    second = bundle(d, max_ece=0.30)

    assert first["fingerprint_sha256"] != second["fingerprint_sha256"]
    assert (
        first["manifest"]["configuration"]["max_ece"]
        != second["manifest"]["configuration"]["max_ece"]
    )


def test_missing_holdout_has_stable_null_holdout_hash_and_not_ready_status():
    d = stable_db()

    result = bundle(d, holdout_result=None)

    assert result["manifest"]["evidence"]["holdout_result_present"] is False
    assert result["manifest"]["evidence"]["holdout_result_sha256"] is None
    assert result["readiness"]["status"] == "NOT_READY_FOR_HUMAN_REVIEW"


def test_bundle_verification_detects_tampering():
    d = stable_db()
    result = bundle(d)

    valid = review_bundle.verify_review_bundle(result)
    assert valid["valid"] is True
    assert valid["reason"] == "ok"

    tampered = json.loads(json.dumps(result))
    tampered["manifest"]["configuration"]["max_ece"] = 999
    invalid = review_bundle.verify_review_bundle(tampered)

    assert invalid["valid"] is False
    assert invalid["reason"] == "fingerprint_mismatch"
    assert invalid["claimed_sha256"] != invalid["actual_sha256"]


def test_bundle_verification_fails_closed_when_fields_missing():
    assert review_bundle.verify_review_bundle({}) == {
        "valid": False,
        "reason": "missing_manifest_or_fingerprint",
    }


def test_bundle_excludes_raw_private_derived_payloads():
    d = stable_db()

    result = bundle(d)
    serialized = json.dumps(result, sort_keys=True)

    assert "DO-NOT-INCLUDE" not in serialized
    assert result["raw_payloads_included"] is False


def test_bundle_contains_only_review_authority_not_execution_authority():
    d = stable_db()

    result = bundle(d)

    assert result["readiness"]["status"] == "READY_FOR_HUMAN_REVIEW"
    assert result["review_only"] is True
    assert result["promotion_authorized"] is False
    assert result["merge_authority"] is False
    assert result["deployment_authorized"] is False
    assert result["manifest"]["human_or_integrator_decision_required"] is True
    assert result["manifest"]["automatic_rule_change"] is False
    assert result["manifest"]["automatic_source_change"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0


def test_hard_case_and_confirmed_hashes_are_present():
    d = stable_db()

    result = bundle(d)
    evidence = result["manifest"]["evidence"]

    assert evidence["confirmed_examples_count"] == 8
    assert evidence["hard_case_count"] == 2
    assert len(evidence["confirmed_examples_sha256"]) == 64
    assert len(evidence["hard_cases_sha256"]) == 64
    assert len(evidence["holdout_result_sha256"]) == 64
