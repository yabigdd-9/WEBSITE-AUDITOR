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
