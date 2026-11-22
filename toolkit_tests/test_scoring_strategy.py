"""Tests for the scoring strategy pattern."""

import copy
import pytest

from auditor_toolkit.scoring_opportunity import (
    DefaultOpportunityStrategy,
    get_opportunity_strategy,
    list_opportunity_strategies,
    register_opportunity_strategy,
    OpportunityScoringStrategy,
    OpportunityResult,
)


class CustomStrategy(OpportunityScoringStrategy):
    """Custom strategy for testing."""

    name = "custom"
    version = "1.0.0"

    def validate_entry(self, entry, context, policy):
        # Accept all entries for testing
        return None

    def calculate_dimensions(self, entry, context, policy, now):
        return {
            "test_dim": __import__("auditor_toolkit.scoring_opportunity", fromlist=["OpportunityDimension"]).OpportunityDimension(
                name="test_dim",
                value=50,
                weight=100,
                explanation="Test dimension",
                contribution=50.0,
            ),
        }

    def build_result(self, entry, context, policy, dimensions, now):
        return OpportunityResult(
            status="qualified_for_internal_review",
            reason="custom_test",
            score=50.0,
            breakdown={"test_dim": {"value": 50, "weight": 100, "contribution": 50.0, "explanation": "Test"}},
            missing_context=[],
            evidence=[],
            policy_sha256="test",
            source_run_id=entry.get("run_id"),
        )


def test_default_strategy_registered():
    """Test that default strategy is registered."""
    strategies = list_opportunity_strategies()
    assert any(s["name"] == "default" for s in strategies)


def test_get_default_strategy():
    """Test getting the default strategy."""
    strategy = get_opportunity_strategy("default")
    assert strategy.name == "default"
    assert isinstance(strategy, DefaultOpportunityStrategy)


def test_register_custom_strategy():
    """Test registering a custom strategy."""
    # Use a unique name to avoid conflicts
    from auditor_toolkit.scoring_opportunity import register_opportunity_strategy

    class CustomStrategy2(OpportunityScoringStrategy):
        name = "custom2"
        version = "1.0.0"

        def validate_entry(self, entry, context, policy):
            return None

        def calculate_dimensions(self, entry, context, policy, now):
            return {}

        def build_result(self, entry, context, policy, dimensions, now):
            return OpportunityResult(
                status="qualified_for_internal_review",
                reason="custom_test",
                score=50.0,
                breakdown={},
                missing_context=[],
                evidence=[],
                policy_sha256="test",
                source_run_id=entry.get("run_id"),
            )

    register_opportunity_strategy(CustomStrategy2())

    strategies = list_opportunity_strategies()
    assert any(s["name"] == "custom2" for s in strategies)

    custom = get_opportunity_strategy("custom2")
    assert custom.name == "custom2"

    strategies = list_opportunity_strategies()
    assert any(s["name"] == "custom2" for s in strategies)


def test_duplicate_registration_raises():
    """Test that duplicate registration raises error."""
    from auditor_toolkit.scoring_opportunity import _OPPORTUNITY_STRATEGIES
    _OPPORTUNITY_STRATEGIES.clear()
    from auditor_toolkit.scoring_opportunity import register_opportunity_strategy

    register_opportunity_strategy(DefaultOpportunityStrategy())
    with pytest.raises(ValueError, match="already registered"):
        register_opportunity_strategy(DefaultOpportunityStrategy())


def test_get_nonexistent_strategy_raises():
    """Test that getting nonexistent strategy raises error."""
    from auditor_toolkit.scoring_opportunity import _OPPORTUNITY_STRATEGIES
    _OPPORTUNITY_STRATEGIES.clear()
    from auditor_toolkit.scoring_opportunity import register_opportunity_strategy, get_opportunity_strategy

    register_opportunity_strategy(DefaultOpportunityStrategy())
    with pytest.raises(ValueError, match="not found"):
        get_opportunity_strategy("nonexistent")


def test_custom_strategy_execution():
    """Test executing a custom strategy."""
    entry = {"domain": "example.com", "status": "COMPLETE", "run_id": "test-1", "timestamp": "2024-01-01T00:00:00Z", "findings": []}
    context = {}
    policy = {"weights": {"test_dim": 100}, "supported_defect_keys": []}

    result = CustomStrategy().score(entry, context, policy, now=1234567890)

    assert isinstance(result, OpportunityResult)
    assert result.status == "qualified_for_internal_review"
    assert result.reason == "custom_test"
    assert result.score == 50.0


def test_strategy_integration_with_cloud_opportunities():
    """Test that strategy pattern works with cloud_opportunities.score."""
    import scripts.cloud_opportunities as opportunities
    from pathlib import Path

    entry = {
        "domain": "example.com",
        "status": "COMPLETE",
        "run_id": "canonical-1",
        "timestamp": "2026-01-01T00:00:00Z",
        "findings": [
            {
                "finding_id": "fixture-1",
                "defect_key": "viewport",
                "confidence": "observed",
                "severity": "high",
                "observed": "Viewport declaration absent in the inspected HTML.",
                "evidence_ref": "html",
                "evidence_check": "html",
                "evidence_check_status": "ok",
                "source_url": "https://example.com/",
                "remediation_action": "Review and add viewport metadata.",
                "independently_verified": False,
            }
        ],
    }
    policy = opportunities.load_policy(Path(__file__).resolve().parents[1])

    # Test with default strategy
    result = opportunities.score(entry, {"delivery_feasibility": 80, "business_service_fit": 60}, policy, now=1000000000)
    assert result["status"] == "qualified_for_internal_review"
    assert result["score"] is not None
    assert result["breakdown"] is not None


def test_invalid_policy_still_rejected():
    """Test that invalid policies are still rejected by validate_policy."""
    import scripts.cloud_opportunities as opportunities

    policy = opportunities.load_policy(Path(__file__).resolve().parents[1])
    original = copy.deepcopy(policy)

    # Modify weights to not sum to 100
    policy["weights"]["recency"] = 10

    entry = {
        "domain": "example.com",
        "status": "COMPLETE",
        "run_id": "canonical-1",
        "timestamp": "2026-01-01T00:00:00Z",
        "findings": [
            {
                "finding_id": "fixture-1",
                "defect_key": "viewport",
                "confidence": "observed",
                "severity": "high",
                "observed": "Viewport declaration absent in the inspected HTML.",
                "evidence_ref": "html",
                "evidence_check": "html",
                "evidence_check_status": "ok",
                "source_url": "https://example.com/",
                "remediation_action": "Review and add viewport metadata.",
                "independently_verified": False,
            }
        ],
    }

    with pytest.raises(ValueError):
        opportunities.score(entry, {"delivery_feasibility": 80, "business_service_fit": 60}, policy, now=1000000000)


from pathlib import Path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])