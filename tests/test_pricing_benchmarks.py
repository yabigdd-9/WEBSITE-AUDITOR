"""
Performance benchmarks for pricing calculator.
"""
import pytest
from proposal_engine.pricing import calculate_quote, get_metrics, reset_metrics


def test_calculate_quote():
    """Test that calculate_quote works correctly (benchmark without fixture)."""
    rates_config = {
        "internal_hourly_rate_nzd": 100,
        "minimum_project_nzd": 500,
        "complexity_multiplier": 1.0,
        "risk_buffer": 0.1,
        "rounding_increment": 5,
        "pricing_version": 1,
    }
    # Test the calculate_quote function
    result = calculate_quote(
        estimated_hours=10,
        rates_config=rates_config,
        complexity_modifier=1.0,
        risk_modifier=1.0,
    )
    # Ensure the result is valid
    assert result["target_estimate"] == 1100


def test_observability_metrics():
    """Test that observability metrics are updated correctly."""
    # Reset metrics to start from a known state
    reset_metrics()
    initial = get_metrics()
    print(f"Initial metrics: {initial}")
    assert initial["call_count"] == 0
    assert initial["total_time"] == 0.0
    assert initial["error_count"] == 0

    rates_config = {
        "internal_hourly_rate_nzd": 100,
        "minimum_project_nzd": 500,
        "complexity_multiplier": 1.0,
        "risk_buffer": 0.1,
        "rounding_increment": 5,
        "pricing_version": 1,
    }

    # Make a successful call
    calculate_quote(estimated_hours=10, rates_config=rates_config)
    metrics = get_metrics()
    print(f"After first call: {metrics}")
    assert metrics["call_count"] == 1
    assert metrics["total_time"] > 0
    assert metrics["error_count"] == 0

    # Make another successful call
    calculate_quote(estimated_hours=5, rates_config=rates_config)
    metrics = get_metrics()
    print(f"After second call: {metrics}")
    assert metrics["call_count"] == 2
    assert metrics["total_time"] > 0  # Should have increased
    assert metrics["error_count"] == 0

    # Test error case: pass invalid estimated_hours to cause a TypeError
    try:
        calculate_quote(estimated_hours=None, rates_config=rates_config)
    except TypeError:
        pass
    except Exception:
        # Any other exception is also fine for this test
        pass

    metrics = get_metrics()
    print(f"After error call: {metrics}")
    assert metrics["call_count"] == 3  # Including the failed call
    assert metrics["error_count"] == 1

    # Test reset_metrics
    reset_metrics()
    metrics = get_metrics()
    print(f"After reset: {metrics}")
    assert metrics["call_count"] == 0
    assert metrics["total_time"] == 0.0
    assert metrics["error_count"] == 0