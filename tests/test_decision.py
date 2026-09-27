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
