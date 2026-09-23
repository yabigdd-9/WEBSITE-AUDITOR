"""Tests for opening hours normalization."""

from auditor_toolkit.local_seo.hours import _expand_day_range, _parse_time, hours_match, normalize_hours
from auditor_toolkit.local_seo.schema import OpeningHour


# --- Time parsing ---


def test_parse_time_24h():
    assert _parse_time("09:00") == "09:00"
    assert _parse_time("17:00") == "17:00"


def test_parse_time_am():
    assert _parse_time("9am") == "09:00"
    assert _parse_time("9 am") == "09:00"


def test_parse_time_pm():
    assert _parse_time("5pm") == "17:00"
    assert _parse_time("5 pm") == "17:00"


def test_parse_time_noon():
    assert _parse_time("12pm") == "12:00"


def test_parse_time_midnight():
    assert _parse_time("12am") == "00:00"


def test_parse_time_invalid():
    assert _parse_time("abc") is None


# --- Day expansion ---


def test_expand_single_day():
    assert _expand_day_range("Monday") == ["Monday"]


def test_expand_range():
    days = _expand_day_range("Mon-Fri")
    assert days == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def test_expand_weekends():
    days = _expand_day_range("Sat-Sun")
    assert days == ["Saturday", "Sunday"]


def test_expand_comma():
    days = _expand_day_range("Mon,Wed,Fri")
    assert "Monday" in days
    assert "Wednesday" in days


def test_expand_wraparound():
    days = _expand_day_range("Friday-Tuesday")
    assert "Friday" in days
    assert "Saturday" in days
    assert "Monday" in days
    assert "Tuesday" in days


# --- Hours normalization ---


def test_normalize_hours_24h():
    hours = normalize_hours("24 hours")
    assert len(hours) == 7  # All days
    assert hours[0].opens == "00:00"


def test_normalize_hours_by_appointment():
    hours = normalize_hours("By appointment")
    assert hours[0].special_text == "By appointment"


def test_normalize_hours_weekday_range():
    hours = normalize_hours("Mon-Fri 9am-5pm")
    assert len(hours) == 5
    assert hours[0].opens == "09:00"
    assert hours[0].closes == "17:00"


def test_normalize_hours_empty():
    assert normalize_hours("") == []


def test_normalize_hours_closed_sundays():
    hours = normalize_hours("closed Sundays")
    sunday = next((h for h in hours if h.day == "Sunday"), None)
    assert sunday is not None
    assert sunday.closed


# --- Hours comparison ---


def test_hours_match_same():
    a = [OpeningHour(day="Monday", opens="09:00", closes="17:00")]
    b = [OpeningHour(day="Monday", opens="09:00", closes="17:00")]
    match, reason = hours_match(a, b)
    assert match
    assert reason == "MATCH"


def test_hours_match_different():
    a = [OpeningHour(day="Monday", opens="09:00", closes="17:00")]
    b = [OpeningHour(day="Monday", opens="08:00", closes="16:00")]
    match, reason = hours_match(a, b)
    assert not match
    assert reason == "CONTRADICTION"


def test_hours_match_both_closed():
    a = [OpeningHour(day="Sunday", closed=True)]
    b = [OpeningHour(day="Sunday", closed=True)]
    match, reason = hours_match(a, b)
    assert match
    assert reason == "MATCH"


def test_hours_match_by_appointment_not_conflict():
    a = [OpeningHour(day="Monday", special_text="By appointment")]
    b = [OpeningHour(day="Monday", opens="09:00", closes="17:00")]
    match, reason = hours_match(a, b)
    # Should NOT flag as contradiction — by appointment is valid
    assert match


def test_hours_match_empty():
    assert hours_match([], []) == (False, "INSUFFICIENT_EVIDENCE")
