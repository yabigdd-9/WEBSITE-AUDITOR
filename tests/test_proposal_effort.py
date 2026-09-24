"""
Tests for effort estimation.
"""

from proposal_engine.effort import get_indicative_hours, midpoint_hours, hours_to_effort_band, is_unknown_band


def test_get_indicative_hours():
    assert get_indicative_hours("XS") == (0.25, 1.0)
    assert get_indicative_hours("S") == (1.0, 3.0)
    assert get_indicative_hours("M") == (3.0, 8.0)
    assert get_indicative_hours("L") == (8.0, 24.0)
    assert get_indicative_hours("XL") == (24.0, None)
    assert get_indicative_hours("UNKNOWN") == (None, None)


def test_midpoint_hours():
    assert midpoint_hours("XS") == 0.625  # (0.25+1)/2
    assert midpoint_hours("S") == 2.0
    assert midpoint_hours("M") == 5.5
    assert midpoint_hours("L") == 16.0
    assert midpoint_hours("XL") == 24.0  # min since max is None


def test_hours_to_effort_band():
    assert hours_to_effort_band(0.5) == "XS"
    assert hours_to_effort_band(2) == "S"
    assert hours_to_effort_band(5) == "M"
    assert hours_to_effort_band(12) == "L"
    assert hours_to_effort_band(30) == "XL"
    assert hours_to_effort_band(0) == "XS"  # below XS min -> XS
    assert hours_to_effort_band(100) == "XL"  # above XL min -> XL


def test_is_unknown_band():
    assert is_unknown_band("UNKNOWN") == True
    assert is_unknown_band("M") == False
