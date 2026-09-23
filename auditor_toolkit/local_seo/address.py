"""Address normalization and comparison.

Stores both raw and normalized forms. Component-level comparison prevents
false matches on whole-address fuzzy logic.
"""

from __future__ import annotations

from .schema import ConsistencyStatus, NormalizedAddress

# ---------------------------------------------------------------------------
# Street suffix expansion
# ---------------------------------------------------------------------------

_SUFFIX_MAP: dict[str, str] = {
    "st": "street",
    "rd": "road",
    "ave": "avenue",
    "blvd": "boulevard",
    "hwy": "highway",
    "ln": "lane",
    "dr": "drive",
    "crt": "court",
    "ct": "court",
    "pl": "place",
    "sq": "square",
    "tce": "terrace",
    "pde": "parade",
    "bvd": "boulevard",
    "mwy": "motorway",
    "nth": "north",
    "sth": "south",
    "est": "east",
    "wst": "west",
    "mkt": "market",
    "gdns": "gardens",
    "gdn": "garden",
}

# ---------------------------------------------------------------------------
# Address normalization
# ---------------------------------------------------------------------------


def normalize_address(raw: str) -> NormalizedAddress:
    """Normalize a raw address string into structured components."""
    if not raw or not raw.strip():
        return NormalizedAddress()

    cleaned = _clean(raw)
    parts = _split_address(cleaned)

    norm_str = _rebuild_normalized(parts)

    return NormalizedAddress(
        raw=raw.strip(),
        street_number=parts.get("number", ""),
        street_name=parts.get("street", ""),
        unit=parts.get("unit", ""),
        locality=parts.get("locality", ""),
        region=parts.get("region", ""),
        postal_code=parts.get("postal", ""),
        country=parts.get("country", ""),
        normalized=norm_str,
    )


def _clean(addr: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return " ".join(addr.lower().split())


def _expand_suffix(token: str) -> str:
    return _SUFFIX_MAP.get(token.lower(), token)


def _split_address(addr: str) -> dict[str, str]:
    """Heuristic address component extraction.

    Works for common NZ/AU/US/UK address formats.
    """
    parts: dict[str, str] = {}

    # Try to extract unit (e.g., "Unit 3", "Apt 4B", "#12")
    import re

    unit_match = re.match(r"(?:unit|apt|suite|#)\s*(\S+?)\s*[,\s]", addr, re.I)
    if unit_match:
        parts["unit"] = unit_match.group(1).rstrip(",")
        addr = addr[unit_match.end():].strip()

    # Try NZ/UK postal code at end (e.g., "6011", "SW1A 1AA")
    # NZ: 4 digits; UK: alphanumeric
    postal_match = re.search(r"(\d{4}|\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})$", addr)
    if postal_match:
        parts["postal"] = postal_match.group(1).strip()
        addr = addr[: postal_match.start()].strip()

    # Try to extract number + street at start
    num_match = re.match(r"(\d+[\w-]?)\s+(.+)", addr)
    if num_match:
        parts["number"] = num_match.group(1)
        rest = num_match.group(2)

        # Split on comma first to separate street from locality
        comma_parts = rest.split(",", 1)
        street_part = comma_parts[0].strip()
        locality_part = comma_parts[1].strip() if len(comma_parts) > 1 else ""

        # Expand suffixes in street name
        tokens = street_part.split()
        expanded = []
        for t in tokens:
            expanded.append(_expand_suffix(t.rstrip(",.")))
        parts["street"] = " ".join(expanded)

        # Parse locality part
        if locality_part:
            loc_tokens = locality_part.split()
            if loc_tokens:
                parts["locality"] = loc_tokens[0]
                if len(loc_tokens) > 1:
                    parts["region"] = " ".join(loc_tokens[1:])
    else:
        parts["street"] = addr

    return parts


def _rebuild_normalized(parts: dict[str, str]) -> str:
    """Rebuild a canonical normalized address string."""
    components = []
    if parts.get("unit"):
        components.append(f"Unit {parts['unit']}")
    if parts.get("number"):
        components.append(parts["number"])
    if parts.get("street"):
        components.append(parts["street"])
    if parts.get("locality"):
        components.append(parts["locality"])
    if parts.get("region"):
        components.append(parts["region"])
    if parts.get("postal"):
        components.append(parts["postal"])
    if parts.get("country"):
        components.append(parts["country"])
    return ", ".join(components)


# ---------------------------------------------------------------------------
# Address comparison
# ---------------------------------------------------------------------------


def compare_addresses(a: NormalizedAddress, b: NormalizedAddress) -> ConsistencyStatus:
    """Compare two normalized addresses component by component."""
    if not a.normalized and not a.raw:
        return "INSUFFICIENT_EVIDENCE"
    if not b.normalized and not b.raw:
        return "INSUFFICIENT_EVIDENCE"

    # Exact match on normalized form
    if a.normalized and b.normalized and a.normalized == b.normalized:
        return "MATCH"

    exact_matches = _score_exact_address_components(a, b)
    if exact_matches is None:
        return "CONTRADICTION"
    fuzzy_matches, conflicts = _score_fuzzy_address_components(a, b)
    matches = exact_matches + fuzzy_matches

    if conflicts >= 2:
        return "CONTRADICTION"

    if matches >= 4:
        return "MATCH"

    if matches >= 2:
        return "PROBABLE_MATCH"

    # If raw forms are close despite normalization difference
    from rapidfuzz import fuzz

    raw_score = fuzz.ratio(a.raw.lower(), b.raw.lower())
    if raw_score >= 85:
        return "EQUIVALENT_FORMAT"

    if conflicts > 0:
        return "CONTRADICTION"

    return "INSUFFICIENT_EVIDENCE"


def _score_exact_address_components(a: NormalizedAddress, b: NormalizedAddress) -> int | None:
    components = (
        (a.country, b.country, 2, lambda value: value.lower()),
        (a.postal_code, b.postal_code, 2, lambda value: value.replace(" ", "").lower()),
        (a.street_number, b.street_number, 3, lambda value: value.lower()),
    )
    matches = 0
    for value_a, value_b, weight, normalize in components:
        result = _compare_exact_component(value_a, value_b, weight, normalize)
        if result is False:
            return None
        if result is not None:
            matches += result
    return matches


def _score_fuzzy_address_components(
    a: NormalizedAddress, b: NormalizedAddress
) -> tuple[int, int]:
    components = (
        (a.street_name, b.street_name, 90, 70, 2, 2, 1),
        (a.locality, b.locality, 90, 70, 2, 2, 1),
        (a.region, b.region, 85, 60, 1, 1, 0),
    )
    matches = conflicts = 0
    for value_a, value_b, match_at, partial_at, weight, conflict_weight, partial_weight in components:
        component_matches, component_conflicts = _compare_fuzzy_component(
            value_a, value_b, match_at, partial_at, weight, conflict_weight, partial_weight
        )
        matches += component_matches
        conflicts += component_conflicts
    return matches, conflicts


def _compare_exact_component(value_a, value_b, weight, normalize):
    """Compare an exact-match component; ``None`` means missing evidence."""
    if not value_a or not value_b:
        return None
    if normalize(value_a) == normalize(value_b):
        return weight
    return False


def _compare_fuzzy_component(
    value_a: str,
    value_b: str,
    match_at: int,
    partial_at: int,
    match_weight: int,
    conflict_weight: int,
    partial_weight: int,
) -> tuple[int, int]:
    if not value_a or not value_b:
        return 0, 0
    from rapidfuzz import fuzz

    score = fuzz.ratio(value_a.lower(), value_b.lower())
    if score >= match_at:
        return match_weight, 0
    if score >= partial_at:
        return partial_weight, 0
    if score < 60 or conflict_weight == 2:
        return 0, conflict_weight
    return 0, 0
