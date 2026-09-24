"""
Effort estimation for the WEBSITE-AUDITOR proposal engine.
"""

from typing import Tuple, Optional


# Effort bands as defined in the plan
EFFORT_BANDS = {
    "XS": {"min": 0.25, "max": 1.0, "label": "Extra Small"},
    "S": {"min": 1.0, "max": 3.0, "label": "Small"},
    "M": {"min": 3.0, "max": 8.0, "label": "Medium"},
    "L": {"min": 8.0, "max": 24.0, "label": "Large"},
    "XL": {"min": 24.0, "max": None, "label": "Extra Large"},
    "UNKNOWN": {"min": None, "max": None, "label": "Unknown", "action": "human estimation required"},
}


def get_indicative_hours(effort_band: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Get the indicative hours range for an effort band.
    Returns (min_hours, max_hours) where max_hours can be None for unbounded.
    """
    if effort_band not in EFFORT_BANDS:
        raise ValueError(f"Unknown effort band: {effort_band}")
    band = EFFORT_BANDS[effort_band]
    return band["min"], band["max"]


def midpoint_hours(effort_band: str) -> float:
    """
    Get the midpoint of the indicative hours range for an effort band.
    For XL, returns the min value (since max is unbounded).
    For UNKNOWN, raises ValueError.
    """
    if effort_band == "UNKNOWN":
        raise ValueError("Cannot calculate midpoint for UNKNOWN effort band")
    min_hours, max_hours = get_indicative_hours(effort_band)
    if max_hours is None:
        return min_hours
    return (min_hours + max_hours) / 2.0


def hours_to_effort_band(hours: float) -> str:
    """
    Convert a number of hours to the closest effort band.
    """
    for band, info in EFFORT_BANDS.items():
        if band == "UNKNOWN":
            continue
        min_hours = info["min"]
        max_hours = info["max"]
        if max_hours is None:
            if hours >= min_hours:
                return band
        else:
            if min_hours <= hours <= max_hours:
                return band
    # If hours are less than XS min, return XS
    if hours < EFFORT_BANDS["XS"]["min"]:
        return "XS"
    # If hours are greater than XL min (and XL has no max), return XL
    if hours >= EFFORT_BANDS["XL"]["min"]:
        return "XL"
    # Fallback (should not happen)
    return "M"


def is_unknown_band(effort_band: str) -> bool:
    """Check if the effort band is UNKNOWN."""
    return effort_band == "UNKNOWN"
