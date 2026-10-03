"""Tests for sanitized hard-case challenger corpus."""
import json
import sqlite3

import mm_challenger as challenger
import mm_intelligence_hard_cases as hard_cases
import mm_intelligence_ledger as ledger


def fresh_db():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    return d


def decision(
    d,
    prospect_id,
    state,
    confidence=0.9,
    derived=None,
    rule_version="v45.1",
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
            derived_evidence=derived or {},
        ),
    )


def outcome(d, prospect_id, state, observed):
    return ledger.append_decision(
        d,
        ledger.IntelligenceDecision(
            prospect_id=prospect_id,
            business_name=f"Business {prospect_id}",
            domain=f"business{prospect_id}.co.nz",
            decision=state,
            disposition="OUTCOME_OBSERVED",
            confidence=0.5,
            rule_version="v45.1",
            stage="outcome",
            later_outcome=observed,
        ),
    )


def test_empty_database_returns_clean_read_only_corpus():
    d = fresh_db()
    before = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )

    result = hard_cases.hard_cases(d)

    after = list(
        d.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    )
    assert result["count"] == 0
    assert result["cases"] == []
    assert result["read_only"] is True
    assert result["sanitized"] is True
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
    assert after == before


def test_confirmed_false_negative_becomes_positive_golden_case():
    d = fresh_db()
    original_id = decision(
        d,
        1,
        "REJECTED",
        0.9,
        {"technical_score": 85, "commercial_score": 20},
    )
    outcome(d, 1, "REJECTED", "WON")

    result = hard_cases.hard_cases(d)

    assert result["count"] == 1
    case = result["cases"][0]
    assert case["case_id"] == f"intelligence-ledger-{original_id}"
    assert case["case_type"] == "CONFIRMED_FALSE_NEGATIVE"
    assert case["expected"] == "POSITIVE"
    assert case["original_polarity"] == "NEGATIVE"
    assert case["later_outcome"] == "WON"
    assert result["promotion_authorized"] is False


def test_confirmed_false_positive_becomes_negative_golden_case():
    d = fresh_db()
    original_id = decision(
        d,
        2,
        "QUALIFIED",
        0.95,
        {"technical_score": 10, "evidence_confidence": 0.1},
        rule_version="v45.2",
    )
    ledger.record_correction(
        d,
        2,
        "Verified non-prospect",
        "REJECTED",
        0.99,
        rule_version="v45.2",
    )

    result = hard_cases.hard_cases(d)

    assert result["count"] == 1
    case = result["cases"][0]
    assert case["case_id"] == f"intelligence-ledger-{original_id}"
    assert case["case_type"] == "CONFIRMED_FALSE_POSITIVE"
    assert case["expected"] == "NEGATIVE"
    assert case["confirmation"] == "human_correction"
    assert result["by_rule_version"] == {"v45.2": 1}


def test_confirmed_correct_decision_is_not_a_hard_case():
    d = fresh_db()
    decision(d, 3, "QUALIFIED", 0.8)
    outcome(d, 3, "QUALIFIED", "REPLIED")

    result = hard_cases.hard_cases(d)

    assert result["count"] == 0
    assert result["cases"] == []


def test_suspected_only_case_is_not_promoted_to_golden():
    d = fresh_db()
    decision(
        d,
        4,
        "REJECTED",
        0.8,
        {"technical_score": 95, "commercial_score": 25},
    )

    result = hard_cases.hard_cases(d)

    assert result["count"] == 0


def test_private_or_unapproved_derived_evidence_is_not_copied():
    d = fresh_db()
    decision(
        d,
        5,
        "QUALIFIED",
        0.9,
        {
            "technical_score": 10,
            "evidence_confidence": 0.1,
            "email": "private@example.com",
            "api_key": "DO-NOT-COPY",
            "raw_html": "<secret>",
        },
    )
    ledger.record_correction(
        d,
        5,
        "Wrong business",
        "REJECTED",
        0.99,
    )

    result = hard_cases.hard_cases(d)
    serialized = json.dumps(result)

    assert result["cases"][0]["derived_evidence"] == {
        "evidence_confidence": 0.1,
        "technical_score": 10,
    }
    assert "private@example.com" not in serialized
    assert "DO-NOT-COPY" not in serialized
    assert "<secret>" not in serialized
    assert result["cases"][0]["raw_payloads_included"] is False


def test_golden_rows_are_directly_compatible_with_challenger_evaluator():
    d = fresh_db()
    decision(d, 6, "REJECTED", 0.9)
    outcome(d, 6, "REJECTED", "WON")
    decision(d, 7, "QUALIFIED", 0.9)
    ledger.record_correction(d, 7, "Not a prospect", "REJECTED", 0.99)

    goldens = hard_cases.golden_rows(d)
    predictions = [
        {
            "case_id": row["case_id"],
            "actual": row["expected"],
            "safety": dict(row["safety"]),
        }
        for row in goldens
    ]

    evaluation = challenger.evaluate(goldens, predictions)

    assert evaluation["cases"] == 2
    assert evaluation["accuracy"] == 1.0
    assert evaluation["safety_failures"] == 0


def test_limit_is_bounded_and_deterministic():
    d = fresh_db()
    for prospect_id in range(1, 6):
        decision(d, prospect_id, "REJECTED", 0.8)
        outcome(d, prospect_id, "REJECTED", "REPLIED")

    result = hard_cases.hard_cases(d, limit=2)

    assert result["count"] == 2
    assert len(result["cases"]) == 2


def test_integrated_challenger_can_recommend_but_never_authorize_promotion():
    d = fresh_db()
    decision(d, 8, "REJECTED", 0.9)
    outcome(d, 8, "REJECTED", "WON")
    decision(d, 9, "QUALIFIED", 0.9)
    ledger.record_correction(d, 9, "Not a prospect", "REJECTED", 0.99)

    goldens = hard_cases.golden_rows(d)
    safety = {
        "paid_calls": 0,
        "external_sends": 0,
        "auto_promoted": False,
    }
    wrong_first = (
        "NEGATIVE"
        if goldens[0]["expected"] == "POSITIVE"
        else "POSITIVE"
    )
    baseline = [
        {
            "case_id": goldens[0]["case_id"],
            "actual": wrong_first,
            "safety": safety,
        },
        {
            "case_id": goldens[1]["case_id"],
            "actual": goldens[1]["expected"],
            "safety": safety,
        },
    ]
    challenger_rows = [
        {
            "case_id": row["case_id"],
            "actual": row["expected"],
            "safety": safety,
        }
        for row in goldens
    ]

    result = hard_cases.evaluate_challenger(
        d,
        baseline,
        challenger_rows,
        min_improvement=0.1,
    )

    assert result["baseline"]["accuracy"] == 0.5
    assert result["challenger"]["accuracy"] == 1.0
    assert result["promotion_recommended"] is True
    assert result["promotion_authorized"] is False
    assert result["merge_authority"] is False
    assert result["deployment_authorized"] is False
    assert result["external_sends"] == 0
    assert result["paid_calls"] == 0


def test_integrated_challenger_safety_regression_blocks_recommendation():
    d = fresh_db()
    decision(d, 10, "REJECTED", 0.9)
    outcome(d, 10, "REJECTED", "WON")

    golden = hard_cases.golden_rows(d)[0]
    safe = dict(golden["safety"])
    baseline = [{
        "case_id": golden["case_id"],
        "actual": "NEGATIVE",
        "safety": safe,
    }]
    unsafe = [{
        "case_id": golden["case_id"],
        "actual": golden["expected"],
        "safety": {
            "paid_calls": 1,
            "external_sends": 0,
            "auto_promoted": False,
        },
    }]

    result = hard_cases.evaluate_challenger(
        d,
        baseline,
        unsafe,
        min_improvement=0.0,
    )

    assert result["challenger"]["safety_failures"] == 1
    assert result["promotion_recommended"] is False
    assert result["promotion_authorized"] is False


def test_integrated_challenger_requires_confirmed_hard_cases():
    d = fresh_db()
    decision(d, 11, "REJECTED", 0.9)

    try:
        hard_cases.evaluate_challenger(d, [], [])
    except ValueError as exc:
        assert "No confirmed hard cases" in str(exc)
    else:
        raise AssertionError("Expected missing hard cases to fail closed")


def _flip_label(label):
    return "NEGATIVE" if label == "POSITIVE" else "POSITIVE"


def _populate_holdout_cases(d, count=6):
    for prospect_id in range(100, 100 + count):
        if prospect_id % 2:
            decision(d, prospect_id, "QUALIFIED", 0.9)
            ledger.record_correction(
                d,
                prospect_id,
                "Verified non-prospect",
                "REJECTED",
                0.99,
            )
        else:
            decision(d, prospect_id, "REJECTED", 0.9)
            outcome(d, prospect_id, "REJECTED", "WON")


def test_hard_case_holdout_split_is_deterministic_disjoint_and_complete():
    d = fresh_db()
    _populate_holdout_cases(d, count=8)

    first = hard_cases.split_goldens(
        d,
        validation_fraction=0.25,
        salt="stable-test",
    )
    second = hard_cases.split_goldens(
        d,
        validation_fraction=0.25,
        salt="stable-test",
    )

    first_train = {row["case_id"] for row in first["training"]}
    first_validation = {row["case_id"] for row in first["validation"]}
    second_train = {row["case_id"] for row in second["training"]}
    second_validation = {row["case_id"] for row in second["validation"]}
    all_cases = {
        row["case_id"]
        for row in hard_cases.golden_rows(d)
    }

    assert first["status"] == "READY"
    assert first_train == second_train
    assert first_validation == second_validation
    assert first_train.isdisjoint(first_validation)
    assert first_train | first_validation == all_cases
    assert first["training_count"] + first["validation_count"] == 8
    assert (
        first["training_prospect_count"]
        + first["validation_prospect_count"]
        == 8
    )
    assert first["prospect_disjoint"] is True
    assert first["deterministic"] is True
    assert first["read_only"] is True


def test_holdout_split_preserves_both_labels_when_each_has_multiple_cases():
    d = fresh_db()
    _populate_holdout_cases(d, count=8)

    split = hard_cases.split_goldens(
        d,
        validation_fraction=0.25,
        salt="label-balance",
    )

    train_labels = {row["expected"] for row in split["training"]}
    validation_labels = {row["expected"] for row in split["validation"]}
    assert train_labels == {"POSITIVE", "NEGATIVE"}
    assert validation_labels == {"POSITIVE", "NEGATIVE"}


def test_holdout_split_fails_closed_on_invalid_fraction():
    d = fresh_db()
    _populate_holdout_cases(d, count=4)

    for fraction in (0.0, 1.0, -0.1, 1.1):
        try:
            hard_cases.split_goldens(d, validation_fraction=fraction)
        except ValueError as exc:
            assert "validation_fraction must be between 0 and 1" in str(exc)
        else:
            raise AssertionError("Expected invalid fraction to fail closed")


def test_holdout_evaluation_requires_at_least_two_confirmed_cases():
    d = fresh_db()
    decision(d, 200, "REJECTED", 0.9)
    outcome(d, 200, "REJECTED", "WON")

    split = hard_cases.split_goldens(d)
    assert split["status"] == "INSUFFICIENT_PROSPECTS"
    assert split["validation_count"] == 0

    golden = hard_cases.golden_rows(d)[0]
    prediction = [{
        "case_id": golden["case_id"],
        "actual": golden["expected"],
        "safety": dict(golden["safety"]),
    }]
    try:
        hard_cases.evaluate_challenger_holdout(
            d,
            prediction,
            prediction,
        )
    except ValueError as exc:
        assert "At least two confirmed hard-case prospects" in str(exc)
    else:
        raise AssertionError("Expected insufficient holdout cases to fail")


def test_holdout_recommendation_is_based_on_validation_not_training():
    d = fresh_db()
    _populate_holdout_cases(d, count=8)
    split = hard_cases.split_goldens(
        d,
        validation_fraction=0.25,
        salt="evaluation-test",
    )
    validation_ids = {
        row["case_id"] for row in split["validation"]
    }
    goldens = hard_cases.golden_rows(d)

    baseline = []
    challenger_rows = []
    for row in goldens:
        safe = dict(row["safety"])
        baseline.append({
            "case_id": row["case_id"],
            "actual": (
                _flip_label(row["expected"])
                if row["case_id"] in validation_ids
                else row["expected"]
            ),
            "safety": safe,
        })
        challenger_rows.append({
            "case_id": row["case_id"],
            "actual": row["expected"],
            "safety": safe,
        })

    result = hard_cases.evaluate_challenger_holdout(
        d,
        baseline,
        challenger_rows,
        validation_fraction=0.25,
        salt="evaluation-test",
        min_improvement=0.1,
    )

    assert result["baseline"]["accuracy"] == 0.0
    assert result["challenger"]["accuracy"] == 1.0
    assert result["promotion_recommended"] is True
    assert result["recommendation_basis"] == "validation_holdout_only"
    assert result["training"]["baseline"]["accuracy"] == 1.0
    assert result["training"]["challenger"]["accuracy"] == 1.0
    assert result["promotion_authorized"] is False
    assert result["merge_authority"] is False
    assert result["deployment_authorized"] is False
    assert result["automatic_rule_change"] is False


def test_holdout_safety_failure_blocks_recommendation():
    d = fresh_db()
    _populate_holdout_cases(d, count=8)
    split = hard_cases.split_goldens(
        d,
        validation_fraction=0.25,
        salt="safety-test",
    )
    validation_ids = {
        row["case_id"] for row in split["validation"]
    }
    goldens = hard_cases.golden_rows(d)

    baseline = []
    challenger_rows = []
    for row in goldens:
        safe = dict(row["safety"])
        baseline.append({
            "case_id": row["case_id"],
            "actual": _flip_label(row["expected"]),
            "safety": safe,
        })
        challenger_safety = dict(safe)
        if row["case_id"] in validation_ids:
            challenger_safety["paid_calls"] = 1
        challenger_rows.append({
            "case_id": row["case_id"],
            "actual": row["expected"],
            "safety": challenger_safety,
        })

    result = hard_cases.evaluate_challenger_holdout(
        d,
        baseline,
        challenger_rows,
        validation_fraction=0.25,
        salt="safety-test",
        min_improvement=0.0,
    )

    assert result["challenger"]["accuracy"] == 0.0
    assert result["challenger"]["safety_failures"] == len(validation_ids)
    assert result["promotion_recommended"] is False
    assert result["promotion_authorized"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0


def _add_two_hard_cases_for_same_prospect(d, prospect_id):
    decision(
        d,
        prospect_id,
        "REJECTED",
        0.9,
        rule_version="v45.1",
    )
    outcome(d, prospect_id, "REJECTED", "WON")
    decision(
        d,
        prospect_id,
        "QUALIFIED",
        0.95,
        rule_version="v45.2",
    )
    ledger.record_correction(
        d,
        prospect_id,
        "v45.2 false positive",
        "REJECTED",
        0.99,
        rule_version="v45.2",
    )


def test_holdout_split_is_prospect_disjoint_with_multiple_cases_per_prospect():
    d = fresh_db()
    _add_two_hard_cases_for_same_prospect(d, 300)

    decision(d, 301, "REJECTED", 0.9)
    outcome(d, 301, "REJECTED", "WON")

    decision(d, 302, "QUALIFIED", 0.9)
    ledger.record_correction(
        d,
        302,
        "Verified negative",
        "REJECTED",
        0.99,
    )

    split = hard_cases.split_goldens(
        d,
        validation_fraction=0.5,
        salt="prospect-disjoint-test",
    )
    case_rows = hard_cases.hard_cases(d)["cases"]
    prospect_by_case = {
        row["case_id"]: row["prospect_id"]
        for row in case_rows
    }
    train_prospects = {
        prospect_by_case[row["case_id"]]
        for row in split["training"]
    }
    validation_prospects = {
        prospect_by_case[row["case_id"]]
        for row in split["validation"]
    }

    assert split["status"] == "READY"
    assert split["prospect_disjoint"] is True
    assert train_prospects.isdisjoint(validation_prospects)

    prospect_300_cases = {
        row["case_id"]
        for row in case_rows
        if row["prospect_id"] == 300
    }
    train_ids = {row["case_id"] for row in split["training"]}
    validation_ids = {row["case_id"] for row in split["validation"]}
    assert (
        prospect_300_cases <= train_ids
        or prospect_300_cases <= validation_ids
    )
    assert not (
        prospect_300_cases & train_ids
        and prospect_300_cases & validation_ids
    )


def test_multiple_cases_from_one_prospect_are_not_enough_for_holdout():
    d = fresh_db()
    _add_two_hard_cases_for_same_prospect(d, 400)

    split = hard_cases.split_goldens(d)

    assert split["status"] == "INSUFFICIENT_PROSPECTS"
    assert split["training_count"] == 2
    assert split["validation_count"] == 0
    assert split["training_prospect_count"] == 1
    assert split["validation_prospect_count"] == 0
    assert split["prospect_disjoint"] is True

    goldens = hard_cases.golden_rows(d)
    predictions = [
        {
            "case_id": row["case_id"],
            "actual": row["expected"],
            "safety": dict(row["safety"]),
        }
        for row in goldens
    ]
    try:
        hard_cases.evaluate_challenger_holdout(
            d,
            predictions,
            predictions,
        )
    except ValueError as exc:
        assert "At least two confirmed hard-case prospects" in str(exc)
    else:
        raise AssertionError("Expected one-prospect holdout to fail closed")
