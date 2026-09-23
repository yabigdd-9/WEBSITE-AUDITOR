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

    # Component-level comparison
    conflicts = 0
    matches = 0

    # Country — exact
    if a.country and b.country:
        if a.country.lower() == b.country.lower():
            matches += 2
        else:
            conflicts += 3  # Country mismatch is strong
            return "CONTRADICTION"

    # Postal code — strong
    if a.postal_code and b.postal_code:
        if a.postal_code.replace(" ", "").lower() == b.postal_code.replace(" ", "").lower():
            matches += 2
        else:
            conflicts += 2
            return "CONTRADICTION"

    # Street number — very strong
    if a.street_number and b.street_number:
        if a.street_number.lower() == b.street_number.lower():
            matches += 3
        else:
            conflicts += 3
            return "CONTRADICTION"

    # Street name — strong
    if a.street_name and b.street_name:
        from rapidfuzz import fuzz

        score = fuzz.ratio(a.street_name.lower(), b.street_name.lower())
        if score >= 90:
            matches += 2
        elif score >= 70:
            matches += 1  # Probable match
        else:
            conflicts += 2

    # Locality — strong
    if a.locality and b.locality:
        from rapidfuzz import fuzz

        score = fuzz.ratio(a.locality.lower(), b.locality.lower())
        if score >= 90:
            matches += 2
        elif score >= 70:
            matches += 1
        else:
            conflicts += 2

    # Region
    if a.region and b.region:
        from rapidfuzz import fuzz

        score = fuzz.ratio(a.region.lower(), b.region.lower())
        if score >= 85:
            matches += 1
        elif score < 60:
            conflicts += 1

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
