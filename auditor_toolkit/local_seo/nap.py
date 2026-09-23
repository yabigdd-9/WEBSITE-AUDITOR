"""NAP (Name, Address, Phone) normalization and comparison.

All comparisons use normalized forms and record the raw evidence separately.
Formatting-only differences never become contradictions.
"""

from __future__ import annotations

from typing import Any

from .address import compare_addresses, normalize_address
from .phone import compare_phones, normalize_phone
from .schema import (
    ConsistencyStatus,
    NamedValue,
    NormalizedAddress,
    NormalizedPhone,
)

# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

# Common equivalence mappings
_LIMITED = " limited "
_AND = " and "
_NAME_EQUIVALENCES: list[tuple[str, str]] = [
    ("&", _AND),
    (_AND, " & "),
    (" ltd ", _LIMITED),
    (_LIMITED, " ltd "),
    (" ltd.", " limited "),
    (" inc ", " incorporated "),
    (" incorporated ", " inc "),
    (" plc ", " public limited company "),
    (" company ", " co "),
    (" co. ", " company "),
    (" co ", " company "),
]

_STRIP_CHARS = "\"'.,!?;:()[]{}"


def normalize_name(raw: str) -> str:
    """Normalize a business name for comparison while retaining the original."""
    name = raw.strip()
    # Replace ampersand before lowercasing
    name = name.replace("&", _AND)
    # Lowercase
    name = name.lower()
    # Strip punctuation
    name = name.translate(str.maketrans("", "", _STRIP_CHARS))
    # Collapse whitespace
    name = " ".join(name.split())
    return name


def names_equivalent(a: str, b: str) -> tuple[bool, ConsistencyStatus]:
    """Compare two business names.

    Returns (equivalent, status) where status explains the relationship.
    """
    norm_a = normalize_name(a)
    norm_b = normalize_name(b)

    if norm_a == norm_b:
        return True, "MATCH"

    # Check known equivalences — pad with spaces for edge matching
    canon_a = " " + norm_a + " "
    canon_b = " " + norm_b + " "
    for old, new in _NAME_EQUIVALENCES:
        canon_a = canon_a.replace(" " + old.strip() + " ", new)
        canon_b = canon_b.replace(" " + old.strip() + " ", new)
    canon_a = canon_a.strip()
    canon_b = canon_b.strip()

    if canon_a == canon_b:
        return True, "EQUIVALENT_FORMAT"

    # Substring match (trading name vs legal name)
    if norm_a in norm_b or norm_b in norm_a:
        return True, "PROBABLE_MATCH"

    return False, "CONTRADICTION"


# ---------------------------------------------------------------------------
# NAP collection and comparison
# ---------------------------------------------------------------------------


def collect_nap_from_page(
    name: str = "",
    address_raw: str = "",
    phone_raw: str = "",
    source: str = "",
) -> dict[str, Any]:
    """Extract and normalize NAP from page-level evidence."""
    result: dict[str, Any] = {
        "name_raw": name,
        "name_normalized": normalize_name(name) if name else "",
        "address": normalize_address(address_raw) if address_raw else NormalizedAddress(),
        "phone": normalize_phone(phone_raw) if phone_raw else NormalizedPhone(),
        "source": source,
    }
    return result


def compare_nap(
    a: dict[str, Any],
    b: dict[str, Any],
) -> dict[str, Any]:
    """Compare two NAP records.

    Returns a dict with per-field comparison results.
    """
    name_eq, name_status = names_equivalent(
        a.get("name_raw", ""), b.get("name_raw", "")
    )

    addr_status = compare_addresses(
        a.get("address", NormalizedAddress()),
        b.get("address", NormalizedAddress()),
    )

    phone_status = compare_phones(
        a.get("phone", NormalizedPhone()),
        b.get("phone", NormalizedPhone()),
    )

    return {
        "name_equivalent": name_eq,
        "name_status": name_status,
        "address_status": addr_status,
        "phone_status": phone_status,
        "material_contradiction": (
            not name_eq or addr_status == "CONTRADICTION" or phone_status == "CONTRADICTION"
        ),
    }


# ---------------------------------------------------------------------------
# Multi-source NAP aggregator
# ---------------------------------------------------------------------------


def aggregate_names(name_values: list[tuple[str, str]]) -> list[NamedValue]:
    """Aggregate name observations from multiple sources.

    Each tuple is (raw_name, source).
    Returns deduplicated list with confidence scores.
    """
    seen: dict[str, NamedValue] = {}
    for raw, source in name_values:
        norm = normalize_name(raw)
        if norm in seen:
            continue
        seen[norm] = NamedValue(value=raw, source=source)
    return list(seen.values())
