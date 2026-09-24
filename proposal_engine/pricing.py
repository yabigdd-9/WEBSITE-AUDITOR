"""
Pricing calculator for the WEBSITE-AUDITOR proposal engine.
"""

import math
from typing import Dict, Any


def calculate_quote(
    estimated_hours: float,
    rates_config: Dict[str, Any],
    complexity_modifier: float = 1.0,
    risk_modifier: float = 1.0,
) -> Dict[str, Any]:
    """
    Calculate a quote based on estimated hours and rates configuration.

    Returns a dictionary with:
        low_estimate, target_estimate, high_estimate, calculation_components, pricing_version
    """
    # Extract configuration
    internal_hourly_rate = rates_config.get("internal_hourly_rate_nzd", 150)
    minimum_project = rates_config.get("minimum_project_nzd", 500)
    complexity_multiplier = rates_config.get("complexity_multiplier", 1.0)
    risk_buffer = rates_config.get("risk_buffer", 0.1)
    rounding_increment = rates_config.get("rounding_increment", 5)
    # Note: complexity_modifier and risk_modifier are passed as arguments

    # Calculate base cost
    base_cost = estimated_hours * internal_hourly_rate
    # Apply complexity multiplier from config and the passed modifier
    cost_after_complexity = base_cost * complexity_multiplier * complexity_modifier
    # Apply risk buffer and risk modifier
    cost_after_risk = cost_after_complexity * (1 + risk_buffer) * risk_modifier

    # The target estimate is the cost after risk
    target_estimate = cost_after_risk

    # For simplicity, we'll define low and high as +/- 20% of target
    # In a real system, these might come from statistical data or configuration.
    low_estimate = target_estimate * 0.8
    high_estimate = target_estimate * 1.2

    # Apply minimum project fee
    low_estimate = max(low_estimate, minimum_project)
    target_estimate = max(target_estimate, minimum_project)
    high_estimate = max(high_estimate, minimum_project)

    # Round deterministically to the nearest rounding_increment
    def round_to_increment(value: float, increment: int) -> float:
        return math.ceil(value / increment) * increment

    low_estimate = round_to_increment(low_estimate, rounding_increment)
    target_estimate = round_to_increment(target_estimate, rounding_increment)
    high_estimate = round_to_increment(high_estimate, rounding_increment)

    # Calculation components for transparency
    calculation_components = {
        "estimated_hours": estimated_hours,
        "internal_hourly_rate_nzd": internal_hourly_rate,
        "base_cost": round(base_cost, 2),
        "complexity_multiplier": complexity_multiplier,
        "complexity_modifier": complexity_modifier,
        "risk_buffer": risk_buffer,
        "risk_modifier": risk_modifier,
        "cost_after_complexity": round(cost_after_complexity, 2),
        "cost_after_risk": round(cost_after_risk, 2),
        "minimum_project_applied": minimum_project if target_estimate == minimum_project else None,
        "rounding_increment": rounding_increment,
    }

    # Pricing version (we'll get from config, but for now hardcoded or from rates_config)
    pricing_version = rates_config.get("pricing_version", 1)

    return {
        "low_estimate": low_estimate,
        "target_estimate": target_estimate,
        "high_estimate": high_estimate,
        "calculation_components": calculation_components,
        "pricing_version": pricing_version,
    }


def quote_from_effort_band(effort_band: str, rates_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert an effort band (XS, S, M, L, XL) to a quote using mid-point of indicative hours.
    """
    # Map effort band to indicative hours (from plan)
    band_to_hours = {
        "XS": (0.25, 1.0),
        "S": (1.0, 3.0),
        "M": (3.0, 8.0),
        "L": (8.0, 24.0),
        "XL": (24.0, None),  # No upper bound
    }

    if effort_band not in band_to_hours:
        raise ValueError(f"Unknown effort band: {effort_band}")

    low, high = band_to_hours[effort_band]
    if high is None:
        # For XL, we use the low as estimated hours (or could be configured)
        estimated_hours = low
    else:
        # Use midpoint
        estimated_hours = (low + high) / 2.0

    return calculate_quote(estimated_hours, rates_config)
