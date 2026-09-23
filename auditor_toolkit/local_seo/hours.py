"""Opening hours normalization.

Handles human-readable formats (Mon-Fri 9am-5pm) and structured
openingHoursSpecification, mapping them to canonical day/time intervals.
"""

from __future__ import annotations

import re

from .schema import OpeningHour

_BY_APPOINTMENT = "By appointment"

# ---------------------------------------------------------------------------
# Day normalization
# ---------------------------------------------------------------------------

_DAY_MAP: dict[str, str] = {
    "mon": "Monday",
    "monday": "Monday",
    "tue": "Tuesday",
    "tues": "Tuesday",
    "tuesday": "Tuesday",
    "wed": "Wednesday",
    "wednesday": "Wednesday",
    "thu": "Thursday",
    "thurs": "Thursday",
    "thursday": "Thursday",
    "fri": "Friday",
    "friday": "Friday",
    "sat": "Saturday",
    "saturday": "Saturday",
    "sun": "Sunday",
    "sunday": "Sunday",
    "weekdays": "Monday,Tuesday,Wednesday,Thursday,Friday",
    "weekends": "Saturday,Sunday",
}

# ---------------------------------------------------------------------------
# Time parsing
# ---------------------------------------------------------------------------

_TIME_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", re.IGNORECASE
)


def _parse_time(raw: str) -> str | None:
    """Parse a time string to HH:MM (24h)."""
    m = _TIME_RE.match(raw.strip())
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = m.group(3)

    if ampm:
        ampm_lower = ampm.lower().replace(".", "")
        if ampm_lower.startswith("a") and hour == 12:
            hour = 0
        elif ampm_lower.startswith("p") and hour != 12:
            hour += 12

    return f"{hour:02d}:{minute:02d}"


# ---------------------------------------------------------------------------
# Hours normalization
# ---------------------------------------------------------------------------


def normalize_hours(
    raw: str,
    source: str = "",
) -> list[OpeningHour]:
    """Parse human-readable hours into canonical OpeningHour list.

    Handles:
    - "Mon-Fri 9am-5pm"
    - "Monday-Friday 09:00-17:00"
    - "24 hours"
    - "By appointment"
    - "Closed Sundays"
    - Split hours: "9am-12pm, 1pm-5pm"
    """
    if not raw or not raw.strip():
        return []

    cleaned = raw.strip().lower()

    # Special text
    if cleaned in ("24 hours", "24/7", "open 24 hours"):
        days = _expand_day_range("Monday-Sunday")
        return [
            OpeningHour(day=d, opens="00:00", closes="23:59", source=source)
            for d in days
        ]

    if cleaned in (
        "by appointment",
        "appointment only",
        "by appointment only",
    ):
        return [
            OpeningHour(day=d, special_text=_BY_APPOINTMENT, source=source)
            for d in _expand_day_range("Monday-Sunday")
        ]

    if cleaned.startswith("closed"):
        days = _extract_closed_days(cleaned)
        result = []
        all_days = _expand_day_range("Monday-Sunday")
        closed_set = set(days)
        for d in all_days:
            if d in closed_set:
                result.append(OpeningHour(day=d, closed=True, source=source))
            else:
                result.append(OpeningHour(day=d, source=source))
        return result

    # Parse day-range + time patterns
    return _parse_hours_pattern(cleaned, source)


def _extract_closed_days(cleaned: str) -> list[str]:
    """Extract closed days from text like 'closed sundays'."""
    days = []
    for token in cleaned.split():
        day = _DAY_MAP.get(token.rstrip("s,"))
        if day:
            days.append(day)
        elif token.rstrip("s,") in _DAY_MAP:
            days.append(_DAY_MAP[token.rstrip("s,")])
    if not days:
        days = _expand_day_range("Monday-Sunday")
    return days


def _parse_hours_pattern(cleaned: str, source: str) -> list[OpeningHour]:
    """Parse 'Mon-Fri 9am-5pm' style patterns."""
    results: list[OpeningHour] = []

    # Split by common delimiters for multiple schedules
    segments = re.split(r";\s*|\s{2,}", cleaned)

    for segment in segments:
        # Try to find day range and time range
        day_time_match = re.match(
            r"([a-z,\s\-]+?)\s+(\d[^;]+)?", segment
        )
        if not day_time_match:
            continue

        day_part = day_time_match.group(1).strip()
        time_part = day_time_match.group(2)

        days = _expand_day_range(day_part)

        if time_part:
            times = _parse_time_range(time_part)
            for d in days:
                if times:
                    results.append(
                        OpeningHour(
                            day=d,
                            opens=times[0],
                            closes=times[1] if len(times) > 1 else "",
                            overnight=times[0] > times[1] if len(times) > 1 else False,
                            source=source,
                        )
                    )
        else:
            for d in days:
                results.append(OpeningHour(day=d, source=source))

    return results


def _expand_day_range(day_range: str) -> list[str]:
    """Expand 'Mon-Fri' or 'Monday,Friday' to full day names."""
    day_range = day_range.strip().lower()

    # Direct lookup
    expanded = _DAY_MAP.get(day_range)
    if expanded and "," in expanded:
        return expanded.split(",")

    # Range pattern: Mon-Fri
    range_match = re.match(
        r"([a-z]+)\s*[-–—]\s*([a-z]+)", day_range
    )
    if range_match:
        start_day = _DAY_MAP.get(range_match.group(1), range_match.group(1).title())
        end_day = _DAY_MAP.get(range_match.group(2), range_match.group(2).title())
        return _day_range(start_day, end_day)

    # Comma-separated
    if "," in day_range:
        result = []
        for part in day_range.split(","):
            part = part.strip()
            if "-" in part:
                result.extend(_expand_day_range(part))
            else:
                day = _DAY_MAP.get(part, part.title())
                result.append(day)
        return result

    # Single day
    return [_DAY_MAP.get(day_range, day_range.title())]


_WEEK_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def _day_range(start: str, end: str) -> list[str]:
    try:
        si = _WEEK_ORDER.index(start)
        ei = _WEEK_ORDER.index(end)
        if ei >= si:
            return _WEEK_ORDER[si : ei + 1]
        else:
            # Wraps around week (e.g., Fri-Tue)
            return _WEEK_ORDER[si:] + _WEEK_ORDER[: ei + 1]
    except ValueError:
        return [start, end]


def _parse_time_range(time_str: str) -> list[str]:
    """Parse '9am-5pm' or '09:00-17:00' into [opens, closes]."""
    time_str = time_str.strip()

    # Split on dash
    parts = re.split(r"[-–—]", time_str)
    if len(parts) >= 2:
        opens = _parse_time(parts[0])
        closes = _parse_time(parts[1])
        if opens and closes:
            return [opens, closes]
        elif opens:
            return [opens]

    # Try to find two times in the string
    times = re.findall(r"\d[^,;]+", time_str)
    parsed = []
    for t in times[:2]:
        p = _parse_time(t)
        if p:
            parsed.append(p)
    return parsed


# ---------------------------------------------------------------------------
# Hours comparison
# ---------------------------------------------------------------------------


def hours_match(
    a: list[OpeningHour],
    b: list[OpeningHour],
) -> tuple[bool, str]:
    """Compare two opening hour lists.

    Returns (match, reason).
    """
    if not a or not b:
        return False, "INSUFFICIENT_EVIDENCE"

    a_map = {h.day: h for h in a}
    b_map = {h.day: h for h in b}

    conflicts = 0
    matches = 0

    common_days = set(a_map.keys()) & set(b_map.keys())
    if not common_days:
        return False, "INSUFFICIENT_EVIDENCE"

    for day in common_days:
        day_matches, day_conflicts = _compare_day_hours(a_map[day], b_map[day])
        matches += day_matches
        conflicts += day_conflicts

    total = len(common_days)
    if total == 0:
        return False, "INSUFFICIENT_EVIDENCE"

    match_ratio = matches / total
    conflict_ratio = conflicts / total

    if conflict_ratio > 0.3:
        return False, "CONTRADICTION"

    if match_ratio >= 0.8:
        return True, "MATCH"

    if match_ratio >= 0.5:
        return True, "PROBABLE_MATCH"

    return False, "CONTRADICTION"


def _compare_day_hours(a: OpeningHour, b: OpeningHour) -> tuple[float, int]:
    """Return the match and conflict weights for one shared weekday."""
    if a.closed and b.closed:
        return 1, 0

    if a.special_text and b.special_text:
        return (1, 0) if a.special_text == b.special_text else (0, 1)

    if (a.special_text or a.closed) != (b.special_text or b.closed):
        if a.special_text == _BY_APPOINTMENT or b.special_text == _BY_APPOINTMENT:
            return 1, 0
        return 0, 1

    if a.opens and b.opens:
        if a.opens == b.opens and a.closes == b.closes:
            return 1, 0
        if a.opens == b.opens or a.closes == b.closes:
            return 0.5, 0
        return 0, 1

    return 0, 0
