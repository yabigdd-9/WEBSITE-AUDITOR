"""
Calibration module for the WEBSITE-AUDITOR proposal engine.
"""

from typing import Dict, Any, Optional
from datetime import datetime


# In a real system, this would be stored in a database.
# For now, we'll just define the schema.
CALIBRATION_SCHEMA = {
    "estimate_id": "string",
    "proposal_id": "string",
    "estimated_hours": "float",
    "actual_hours": "Optional[float]",
    "estimated_price": "float",
    "actual_price": "Optional[float]",
    "scope_changes": "list of strings",
    "timestamp": "datetime",
}


def record_calibration_data(
    estimate_id: str,
    proposal_id: str,
    estimated_hours: float,
    estimated_price: float,
    actual_hours: Optional[float] = None,
    actual_price: Optional[float] = None,
    scope_changes: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Record calibration data for future analysis.
    Returns a dictionary representing the calibration record.
    """
    return {
        "estimate_id": estimate_id,
        "proposal_id": proposal_id,
        "estimated_hours": estimated_hours,
        "actual_hours": actual_hours,
        "estimated_price": estimated_price,
        "actual_price": actual_price,
        "scope_changes": scope_changes or [],
        "timestamp": datetime.now().isoformat(),
    }


def calculate_estimate_error(estimated: float, actual: Optional[float]) -> Optional[float]:
    """
    Calculate the estimate error as (actual - estimated) / estimated.
    Returns None if actual is not available.
    """
    if actual is None:
        return None
    if estimated == 0:
        return float('inf') if actual > 0 else float('-inf')
    return (actual - estimated) / estimated
