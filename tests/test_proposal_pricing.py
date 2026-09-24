"""
Tests for pricing calculator.
"""

from proposal_engine.pricing import calculate_quote, quote_from_effort_band


def test_calculate_quote():
    rates_config = {
        "internal_hourly_rate_nzd": 100,
        "minimum_project_nzd": 500,
        "complexity_multiplier": 1.0,
        "risk_buffer": 0.1,
        "rounding_increment": 5,
        "pricing_version": 1,
    }
    quote = calculate_quote(
        estimated_hours=10,
        rates_config=rates_config,
        complexity_modifier=1.0,
        risk_modifier=1.0,
    )
    # Base cost = 10 * 100 = 1000
    # After complexity (1.0) and risk buffer (1.1) = 1000 * 1.1 = 1100
    # No modifier changes
    # Apply rounding increment of 5: 1100 is already multiple of 5
    # Minimum project is 500, so not applied
    assert quote["target_estimate"] == 1100
    assert quote["low_estimate"] == 880
    assert quote["high_estimate"] == 1320
    assert quote["pricing_version"] == 1


def test_quote_from_effort_band():
    rates_config = {
        "internal_hourly_rate_nzd": 100,
        "minimum_project_nzd": 500,
        "complexity_multiplier": 1.0,
        "risk_buffer": 0.1,
        "rounding_increment": 5,
        "pricing_version": 1,
    }
    # For effort band M, midpoint hours = (3+8)/2 = 5.5
    quote = quote_from_effort_band("M", rates_config)
    # Base cost = 5.5 * 100 = 550
    # After risk buffer = 550 * 1.1 = 605
    # Rounding to 5 (round up): 605 is already multiple of 5
    # Minimum project 500 -> target = max(605,500) = 605
    assert quote["target_estimate"] == 605
    # low_estimate = 605 * 0.8 = 484 -> max with 500 -> 500 -> round up to 5 (already multiple) -> 500
    assert quote["low_estimate"] == 500
    # high_estimate = 605 * 1.2 = 726 -> max with 500 -> 726 -> round up to 5: ceil(726/5)=146 -> 146*5=730
    assert quote["high_estimate"] == 730
