"""Basic tests for the opportunity engine aggregator."""

from . import aggregator, features, bands, confidence, offers, explain, review


def test_feature_functions():
    """Test that each feature function returns a float in [0,1]."""
    # verified_need
    audit_findings = [{"impact": "HIGH"}, {"impact": "MEDIUM"}]
    vn = features.verified_need(audit_findings)
    assert 0.0 <= vn <= 1.0

    # identity_confidence
    idc = features.identity_confidence({"confidence": 0.8})
    assert 0.0 <= idc <= 1.0

    # website_confidence
    wc = features.website_confidence({"score": 0.5})
    assert 0.0 <= wc <= 1.0

    # evidence_quality
    eq = features.evidence_quality(["source1", "source2"], 2, 2)
    assert 0.0 <= eq <= 1.0

    # fixability
    fx = features.fixability("meta/title issue", "wordpress", 5)
    assert 0.0 <= fx <= 1.0

    # delivery_effort
    de = features.delivery_effort("meta/title issue", "wordpress", 1)
    assert 0.0 <= de <= 1.0

    # business_value
    bv = features.business_value({"ecommerce": True})
    assert bv in (0.0, 0.5, 1.0)

    # contactability
    cb = features.contactability({"verified_first_party_business_email": True})
    assert 0.0 <= cb <= 1.0

    # peer_gap
    pg = features.peer_gap(0.6, 0.8, 10)
    assert 0.0 <= pg <= 1.0

    # market_context
    mc = features.market_context("us", "retail")
    assert 0.0 <= mc <= 1.0

    # expected_remediation_value
    erv = features.expected_remediation_value("meta/title issue", 5, 0.5, 0.8)
    assert 0.0 <= erv <= 1.0


def test_aggregator():
    """Test the aggregator with sample data."""
    audit_findings = [{"impact": "HIGH"}]
    identity_data = {"confidence": 0.9}
    website_ownership_data = {"score": 0.8}
    evidence_sources = ["source1", "source2"]
    observed_count = 2
    total_sources = 2
    finding_type = "meta/title issue"
    platform = "wordpress"
    affected_pages = 1
    signals = {"ecommerce": True, "booking_functionality": True}
    technical_health = 0.7
    peer_median = 0.6
    peer_count = 10
    region = "us"
    industry = "retail"

    result = aggregator.compute_opportunity_score(
        audit_findings, identity_data, website_ownership_data, evidence_sources,
        observed_count, total_sources, finding_type, platform, affected_pages,
        signals, technical_health, peer_median, peer_count, region, industry
    )

    # Check that we have the expected keys
    expected_keys = {"score", "confidence", "band", "feature_scores", "group_scores", "numerator", "delivery_effort"}
    assert set(result.keys()) == expected_keys

    # Check that score is a float
    assert isinstance(result["score"], float)
    # Check that band is a string
    assert isinstance(result["band"], str)
    # Check that confidence is a float in [0,1]
    assert 0.0 <= result["confidence"] <= 1.0

    # Check that feature_scores has all features
    expected_features = {
        "verified_need", "identity_confidence", "website_confidence", "evidence_quality",
        "fixability", "delivery_effort", "business_value", "contactability",
        "peer_gap", "market_context", "expected_remediation_value"
    }
    assert set(result["feature_scores"].keys()) == expected_features

    # Check that group_scores has the expected groups
    expected_groups = {"technical_need", "commercial_function", "identity", "market", "meta"}
    assert set(result["group_scores"].keys()) == expected_groups


def test_offers():
    """Test offer mapping."""
    opportunity = {
        "feature_scores": {
            "verified_need": 0.8,
            "fixability": 0.7,
            "peer_gap": 0.6,
            "expected_remediation_value": 0.5,
            "business_value": 0.9,
            "contactability": 0.8,
            "identity_confidence": 0.7,
            "website_confidence": 0.6,
            "market_context": 0.4,
            "evidence_quality": 0.7,
            "delivery_effort": 0.3,
        }
    }
    offer = offers.map_to_offer_family(opportunity)
    assert "primary_offer_family" in offer
    assert "secondary_offer_family" in offer
    assert "evidence" in offer


def test_explain():
    """Test explanation generation."""
    opportunity = {
        "feature_scores": {
            "verified_need": 0.8,
            "fixability": 0.7,
            "peer_gap": 0.6,
            "expected_remediation_value": 0.5,
            "business_value": 0.9,
            "contactability": 0.8,
            "identity_confidence": 0.7,
            "website_confidence": 0.6,
            "market_context": 0.4,
            "evidence_quality": 0.7,
            "delivery_effort": 0.3,
        }
    }
    exp = explain.explain_score(opportunity)
    assert "explanation_text" in exp
    assert isinstance(exp["explanation_text"], str)
    assert "band" in exp


def test_review():
    """Test review packet generation."""
    opportunity = {
        "feature_scores": {
            "verified_need": 0.8,
            "fixability": 0.7,
            "peer_gap": 0.6,
            "expected_remediation_value": 0.5,
            "business_value": 0.9,
            "contactability": 0.8,
            "identity_confidence": 0.7,
            "website_confidence": 0.6,
            "market_context": 0.4,
            "evidence_quality": 0.7,
            "delivery_effort": 0.3,
        },
        "group_scores": {
            "technical_need": 0.65,
            "commercial_function": 0.85,
            "identity": 0.65,
            "market": 0.4,
            "meta": 0.7,
        },
        "score": 0.8,
        "confidence": 0.9,
        "band": "EXECUTE_NOW",
    }
    packet = review.create_review_packet(opportunity)
    assert "identity" in packet
    assert "problem" in packet
    assert "commercial" in packet
    assert "contact" in packet
    assert "offer" in packet
    assert "proof" in packet
    assert "limitations" in packet
    assert "overall_score" in packet
    assert "band" in packet


if __name__ == "__main__":
    test_feature_functions()
    test_aggregator()
    test_offers()
    test_explain()
    test_review()
    print("All tests passed.")