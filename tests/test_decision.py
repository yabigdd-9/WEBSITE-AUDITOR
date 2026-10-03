from auditor_toolkit.decision import priority_decision, six_component_opportunity


def test_strong_supported_opportunity_builds_demo():
    result = priority_decision(
        technical_opportunity=0.9,
        commercial_opportunity=0.85,
        identity_confidence=0.9,
        evidence_confidence=0.9,
        evidence_freshness=0.9,
        contactability=0.85,
        conversion_path_health=0.8,
        estimated_effort=0.2,
    )
    assert result["priority_score"] >= 65
    assert result["confidence"] >= 0.7
    assert result["next_action"] == "BUILD_DEMO"
    assert result["human_review_required"] is True


def test_missing_contact_does_not_zero_technical_value():
    result = priority_decision(
        technical_opportunity=1.0,
        commercial_opportunity=0.8,
        identity_confidence=0.9,
        evidence_confidence=0.9,
        evidence_freshness=0.9,
        contactability=0.0,
        conversion_path_health=0.8,
        estimated_effort=0.2,
    )
    assert result["priority_score"] > 50
    assert "NO_VERIFIED_CONTACT" in result["blockers"]
    assert result["next_action"] == "VERIFY_CONTACT"


def test_weak_identity_routes_to_verification():
    result = priority_decision(
        technical_opportunity=0.9,
        commercial_opportunity=0.9,
        identity_confidence=0.2,
        evidence_confidence=0.9,
        evidence_freshness=0.9,
        contactability=0.9,
        conversion_path_health=0.9,
        estimated_effort=0.1,
    )
    assert "IDENTITY_NOT_CONFIRMED" in result["blockers"]
    assert result["next_action"] == "VERIFY_IDENTITY"


def test_stale_evidence_routes_to_verification():
    result = priority_decision(
        technical_opportunity=0.9,
        commercial_opportunity=0.9,
        identity_confidence=0.9,
        evidence_confidence=0.9,
        evidence_freshness=0.2,
        contactability=0.9,
        conversion_path_health=0.9,
        estimated_effort=0.1,
    )
    assert "EVIDENCE_STALE" in result["blockers"]
    assert result["next_action"] == "VERIFY_EVIDENCE"


def test_invalid_input_fails_closed():
    try:
        priority_decision(
            technical_opportunity=1.2,
            commercial_opportunity=0.5,
            identity_confidence=0.5,
            evidence_confidence=0.5,
            evidence_freshness=0.5,
            contactability=0.5,
            conversion_path_health=0.5,
            estimated_effort=0.5,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-range score should fail closed")


def test_legacy_six_component_score_is_centralized():
    result = six_component_opportunity(1, 1, 1, 1, 1, 1)
    assert result["score"] == 100
    assert result["is_shortlist"] is True
    assert result["formula_version"] == "legacy-six-component-v1"



def test_decision_routes_flow_review_before_contact():
    result = priority_decision(
        technical_opportunity=0.8,
        commercial_opportunity=0.8,
        identity_confidence=0.9,
        evidence_confidence=0.9,
        evidence_freshness=0.9,
        contactability=0.2,
        conversion_path_health=0.2,
        estimated_effort=0.2,
    )
    assert "CONVERSION_PATH_WEAK" in result["reason_codes"]
    assert "CONVERSION_PATH_NEEDS_REVIEW" in result["blockers"]
    assert result["next_action"] == "INVESTIGATE_FLOW"


def test_decision_can_route_to_human_review():
    result = priority_decision(
        technical_opportunity=0.5,
        commercial_opportunity=0.5,
        identity_confidence=0.7,
        evidence_confidence=0.7,
        evidence_freshness=0.7,
        contactability=0.7,
        conversion_path_health=0.7,
        estimated_effort=0.5,
    )
    assert 40 <= result["priority_score"] < 65
    assert result["next_action"] == "HUMAN_REVIEW"


def test_decision_can_hold_low_value_supported_case():
    result = priority_decision(
        technical_opportunity=0.1,
        commercial_opportunity=0.1,
        identity_confidence=0.6,
        evidence_confidence=0.6,
        evidence_freshness=0.5,
        contactability=0.4,
        conversion_path_health=0.5,
        estimated_effort=1.0,
    )
    assert result["priority_score"] < 40
    assert result["next_action"] == "HOLD"


def test_decision_rejects_boolean_and_non_numeric_inputs():
    common = dict(
        commercial_opportunity=0.5,
        identity_confidence=0.5,
        evidence_confidence=0.5,
        evidence_freshness=0.5,
        contactability=0.5,
        conversion_path_health=0.5,
        estimated_effort=0.5,
    )
    for bad in (True, object()):
        try:
            priority_decision(technical_opportunity=bad, **common)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid score type should fail closed")
